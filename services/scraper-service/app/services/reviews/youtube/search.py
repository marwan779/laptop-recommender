"""YouTube search and metadata collection via yt-dlp.

Uses yt-dlp's *flat* search mode plus metadata extraction — never downloads video
or audio. All blocking yt-dlp work is pushed to a worker thread via
``asyncio.to_thread`` so the event loop stays responsive.

Fail-open philosophy: a failure for one video, or for the comment fetch, yields
an empty list rather than aborting the whole batch.
"""

from __future__ import annotations

import asyncio
import logging
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


def _import_yt_dlp() -> Any:
    """Import yt-dlp lazily so the module stays importable when it is absent."""
    try:
        import yt_dlp  # noqa: PLC0415

        return yt_dlp
    except ImportError:  # pragma: no cover - environment dependent
        logger.warning("yt-dlp is not installed; YouTube search will return no results.")
        return None


class YouTubeSearchService:
    """Search YouTube for review videos and attach top comments.

    Args:
        max_results: Maximum number of valid videos to return per query.
        min_duration_seconds: Videos shorter than this are discarded as Shorts.
        max_comments: Maximum top comments fetched per video.
    """

    def __init__(
        self,
        max_results: int = 3,
        min_duration_seconds: int = 90,
        max_comments: int = 10,
    ) -> None:
        self.max_results = max_results
        self.min_duration_seconds = min_duration_seconds
        self.max_comments = max_comments

    async def search_reviews(self, query: str) -> list[dict[str, Any]]:
        """Search YouTube for ``query`` and return validated video metadata dicts.

        Returns an empty list when yt-dlp is unavailable or the search fails.
        """
        if not query or not str(query).strip():
            return []
        return await asyncio.to_thread(self._search_sync, query)

    # ── Internal synchronous implementation (runs in a worker thread) ──────

    def _search_sync(self, query: str) -> list[dict[str, Any]]:
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
            logger.warning("YouTube search failed for %r: %s", query, exc)
            return []

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
                    "top_comments": self._fetch_top_comments_sync(str(video_url), self.max_comments),
                }
            )

        return videos

    def _fetch_top_comments_sync(self, video_url: str, max_comments: int) -> list[YouTubeComment]:
        """Fetch top comments for one video. Fail-open to an empty list."""
        yt_dlp = _import_yt_dlp()
        if yt_dlp is None:
            return []

        opts = {
            **_BASE_YDL_OPTS,
            "getcomments": True,
            "extract_flat": False,
            "extractor_args": {"youtube": {"comment_sort": ["top"]}},
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except Exception as exc:  # noqa: BLE001 - comments are best-effort
            logger.debug("Comment fetch failed for %s: %s", video_url, exc)
            return []

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
                    published_at=raw.get("timestamp") or raw.get("published_at"),
                )
            )

        return comments

    async def fetch_top_comments(
        self,
        video_url: str,
        max_comments: int | None = None,
    ) -> list[YouTubeComment]:
        """Fetch top comments for a video URL asynchronously."""
        limit = max_comments if max_comments is not None else self.max_comments
        return await asyncio.to_thread(self._fetch_top_comments_sync, video_url, limit)


__all__ = ["YouTubeSearchService"]
