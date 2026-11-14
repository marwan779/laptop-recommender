"""YouTube search and metadata collection via yt-dlp.

Uses yt-dlp's *flat* search mode plus metadata extraction — never downloads video
or audio. All blocking yt-dlp work is pushed to a worker thread via
``asyncio.to_thread`` so the event loop stays responsive.

Fail-open philosophy: a failure for one video, or for the comment fetch, yields
an empty list rather than aborting the whole batch.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import random
import threading
import time
from typing import Any

from app.schemas.reviews_s3 import YouTubeComment

logger = logging.getLogger("scraper.services.reviews.youtube.search")

# Base options shared by every yt-dlp call: never download, never block on errors.
_BASE_YDL_OPTS: dict[str, Any] = {
    "skip_download": True,
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "noprogress": True,
    "no_color": True,
}

_MAX_COOLDOWN_SECONDS = 300.0
_DEFAULT_JITTER_RANGE: tuple[float, float] = (0.15, 0.45)


def _import_yt_dlp() -> Any:
    """Import yt-dlp lazily so the module stays importable when it is absent."""
    try:
        import yt_dlp  # noqa: PLC0415

        return yt_dlp
    except ImportError:  # pragma: no cover - environment dependent
        logger.warning("yt-dlp is not installed; YouTube search will return no results.")
        return None


def _is_rate_limit_message(text: str) -> bool:
    lower = (text or "").lower()
    return any(
        marker in lower
        for marker in (
            "403",
            "429",
            "forbidden",
            "too many requests",
            "blocking requests from your ip",
            "sign in to confirm",
        )
    )


def _normalize_comment_timestamp(raw: dict[str, Any]) -> str | None:
    """Convert raw yt-dlp comment epoch/string timestamps to UTC ISO-8601."""
    ts = raw.get("timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(float(ts), tz=UTC).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            pass
    published = raw.get("published_at")
    if published is not None and str(published).strip():
        return str(published).strip()
    time_text = raw.get("_time_text")
    if time_text is not None and str(time_text).strip():
        return str(time_text).strip()
    return None


class _YtDlpCommentLogger:
    """Intercepts yt-dlp internal logging to trip a timed cooldown on rate limits."""

    def __init__(self, service: YouTubeSearchService) -> None:
        self.service = service

    def debug(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        if _is_rate_limit_message(msg):
            self.service._trip_comments_cooldown(msg)

    def error(self, msg: str) -> None:
        if _is_rate_limit_message(msg):
            self.service._trip_comments_cooldown(msg)


class YouTubeSearchService:
    """Search YouTube for review videos and fetch top comments on demand.

    Runs strictly cookieless with bounded jitter and time-bounded cooldowns on
    transient rate limits instead of permanent session latches.
    """

    def __init__(
        self,
        max_results: int = 3,
        min_duration_seconds: int = 90,
        max_comments: int = 10,
        base_cooldown_seconds: float = 30.0,
        jitter_range: tuple[float, float] = _DEFAULT_JITTER_RANGE,
    ) -> None:
        self.max_results = max_results
        self.min_duration_seconds = min_duration_seconds
        self.max_comments = max_comments
        self.base_cooldown_seconds = base_cooldown_seconds
        self.jitter_range = jitter_range

        self._lock = threading.Lock()
        self._comments_cooldown_until: float = 0.0
        self._comments_failure_streak: int = 0
        self._search_cooldown_until: float = 0.0
        self._search_failure_streak: int = 0

    @property
    def _comments_blocked(self) -> bool:
        """Backward-compatible cooldown inspection property."""
        return self._is_comments_in_cooldown()

    def _is_comments_in_cooldown(self) -> bool:
        with self._lock:
            return time.monotonic() < self._comments_cooldown_until

    def _is_search_in_cooldown(self) -> bool:
        with self._lock:
            return time.monotonic() < self._search_cooldown_until

    def _trip_comments_cooldown(self, reason: str = "") -> None:
        with self._lock:
            self._comments_failure_streak += 1
            delay = min(
                self.base_cooldown_seconds * (2 ** (self._comments_failure_streak - 1)),
                _MAX_COOLDOWN_SECONDS,
            )
            now = time.monotonic()
            was_cooling = now < self._comments_cooldown_until
            self._comments_cooldown_until = now + delay
            if not was_cooling:
                logger.warning(
                    "YouTube comments rate-limited (%s). Entering %.1fs cooldown.",
                    reason or "403/429",
                    delay,
                )

    def _reset_comments_cooldown(self) -> None:
        with self._lock:
            self._comments_failure_streak = 0
            self._comments_cooldown_until = 0.0

    def _trip_search_cooldown(self, reason: str = "") -> None:
        with self._lock:
            self._search_failure_streak += 1
            delay = min(
                self.base_cooldown_seconds * (2 ** (self._search_failure_streak - 1)),
                _MAX_COOLDOWN_SECONDS,
            )
            now = time.monotonic()
            was_cooling = now < self._search_cooldown_until
            self._search_cooldown_until = now + delay
            if not was_cooling:
                logger.warning(
                    "YouTube search rate-limited (%s). Entering %.1fs cooldown.",
                    reason or "429",
                    delay,
                )

    def _reset_search_cooldown(self) -> None:
        with self._lock:
            self._search_failure_streak = 0
            self._search_cooldown_until = 0.0

    async def _pace(self) -> None:
        low, high = self.jitter_range
        if high > 0 and high >= low:
            await asyncio.sleep(random.uniform(max(0.0, low), high))

    async def search_reviews(self, query: str) -> list[dict[str, Any]]:
        """Search YouTube for ``query`` and return validated video metadata dicts.

        Returns an empty list when yt-dlp is unavailable, in cooldown, or fails.
        """
        if not query or not str(query).strip() or self._is_search_in_cooldown():
            return []
        await self._pace()
        return await asyncio.to_thread(self._search_sync, query)

    # ── Internal synchronous implementation (runs in a worker thread) ──────

    def _search_sync(self, query: str) -> list[dict[str, Any]]:
        if self._is_search_in_cooldown():
            return []
        yt_dlp = _import_yt_dlp()
        if yt_dlp is None:
            return []

        opts = {**_BASE_YDL_OPTS, "extract_flat": True}
        # Over-fetch so Shorts filtering still yields max_results.
        search_target = f"ytsearch{self.max_results * 2}:{query}"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(search_target, download=False)
        except Exception as exc:  # noqa: BLE001 - yt-dlp raises many types
            if _is_rate_limit_message(str(exc)):
                self._trip_search_cooldown(str(exc))
            logger.warning("YouTube search failed for %r: %s", query, exc)
            return []

        if info is not None:
            self._reset_search_cooldown()

        entries = (info or {}).get("entries") or []
        videos: list[dict[str, Any]] = []

        for entry in entries:
            if len(videos) >= self.max_results:
                break
            if not isinstance(entry, dict):
                continue

            duration = entry.get("duration")
            # Missing duration is treated as unknown => discard (cannot rule out a Short).
            if duration is None or duration < self.min_duration_seconds:
                continue

            video_id = entry.get("id")
            if not video_id:
                continue

            video_url = entry.get("url") or entry.get("webpage_url")
            if not video_url or not str(video_url).startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={video_id}"

            videos.append(
                {
                    "video_id": str(video_id),
                    "title": entry.get("title") or "",
                    "channel_name": entry.get("uploader") or entry.get("channel"),
                    "channel_url": entry.get("uploader_url") or entry.get("channel_url"),
                    "video_url": str(video_url),
                    "published_at": entry.get("upload_date"),
                    "duration_seconds": int(duration),
                    "view_count": entry.get("view_count"),
                    "query_used": query,
                    "top_comments": [],
                    "comments_deferred": True,
                }
            )

        return videos

    def _fetch_top_comments_sync(self, video_url: str, max_comments: int) -> list[YouTubeComment]:
        """Fetch top comments for one video. Fail-open to an empty list."""
        if self._is_comments_in_cooldown():
            return []

        yt_dlp = _import_yt_dlp()
        if yt_dlp is None:
            return []

        opts = {
            **_BASE_YDL_OPTS,
            "getcomments": True,
            "extract_flat": False,
            "format": "all",
            "extractor_args": {"youtube": {"comment_sort": ["top"]}},
            "logger": _YtDlpCommentLogger(self),
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except Exception as exc:  # noqa: BLE001 - comments are best-effort
            exc_str = str(exc)
            if _is_rate_limit_message(exc_str):
                self._trip_comments_cooldown(exc_str)
            logger.debug("Comment fetch failed for %s: %s", video_url, exc)
            return []

        if info is not None and not self._is_comments_in_cooldown():
            self._reset_comments_cooldown()

        raw_comments = (info or {}).get("comments") or []
        comments: list[YouTubeComment] = []

        for raw in raw_comments:
            if len(comments) >= max_comments:
                break
            if not isinstance(raw, dict):
                continue
            text = raw.get("text")
            if not text:
                continue
            comments.append(
                YouTubeComment(
                    comment_id=str(raw.get("id") or ""),
                    author=raw.get("author"),
                    comment_text=str(text),
                    like_count=raw.get("like_count"),
                    published_at=_normalize_comment_timestamp(raw),
                )
            )

        return comments

    async def fetch_top_comments(
        self,
        video_url: str,
        max_comments: int | None = None,
    ) -> list[YouTubeComment]:
        """Fetch top comments for a video URL asynchronously."""
        if self._is_comments_in_cooldown():
            return []
        await self._pace()
        limit = max_comments if max_comments is not None else self.max_comments
        return await asyncio.to_thread(self._fetch_top_comments_sync, video_url, limit)


__all__ = ["YouTubeSearchService"]
