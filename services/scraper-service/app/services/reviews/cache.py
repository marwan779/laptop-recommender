"""Fail-open persistent cache for cross-batch review evidence.

Keys are namespaced under ``reviews:`` so they can never collide with the
``inbox:`` deduplication keys. Every cache operation swallows infrastructure
errors and degrades to a miss/no-op so one flaky Redis node cannot abort a
review collection batch.
"""

from __future__ import annotations

from hashlib import sha256
import json
import logging
from typing import Any

from app.common.cache import ICacheProvider
from app.schemas.reviews_s3 import YouTubeVideo

logger = logging.getLogger("scraper.services.reviews.cache")

DEFAULT_YOUTUBE_TTL_SECONDS = 14 * 86400
DEFAULT_COMMUNITY_TTL_SECONDS = 7 * 86400


def youtube_video_cache_key(video_id: str) -> str:
    """Return the persistent cache key for one YouTube video."""
    return f"reviews:yt:video:{video_id.strip()}"


def normalize_cache_url(url: str) -> str:
    """Normalize a community URL without changing its routing semantics."""
    return str(url or "").strip()


def community_text_cache_key(url: str) -> str:
    """Return the persistent cache key for a community page's text body."""
    digest = sha256(normalize_cache_url(url).encode("utf-8")).hexdigest()
    return f"reviews:http:text:{digest}"


def community_json_cache_key(url: str) -> str:
    """Return the persistent cache key for a community page's JSON body."""
    digest = sha256(normalize_cache_url(url).encode("utf-8")).hexdigest()
    return f"reviews:http:json:{digest}"


class ReviewsPersistentCache:
    """Typed, fail-open L2 cache for YouTube and community review evidence."""

    def __init__(
        self,
        provider: ICacheProvider | None,
        *,
        youtube_ttl_seconds: int = DEFAULT_YOUTUBE_TTL_SECONDS,
        community_ttl_seconds: int = DEFAULT_COMMUNITY_TTL_SECONDS,
    ) -> None:
        self.provider = provider
        self.youtube_ttl_seconds = int(youtube_ttl_seconds)
        self.community_ttl_seconds = int(community_ttl_seconds)

        self.yt_hits = 0
        self.yt_misses = 0
        self.yt_stores = 0
        self.http_hits = 0
        self.http_misses = 0
        self.http_stores = 0

    def stats_summary(self) -> dict[str, int]:
        """Return a snapshot of this adapter's hit/miss/store counters."""
        return {
            "yt_hits": self.yt_hits,
            "yt_misses": self.yt_misses,
            "yt_stores": self.yt_stores,
            "http_hits": self.http_hits,
            "http_misses": self.http_misses,
            "http_stores": self.http_stores,
        }

    @property
    def youtube_enabled(self) -> bool:
        return self.provider is not None and self.youtube_ttl_seconds > 0

    @property
    def community_enabled(self) -> bool:
        return self.provider is not None and self.community_ttl_seconds > 0

    async def get_youtube_video(self, video_id: str) -> dict[str, Any] | None:
        """Return cached transcript/comment evidence for a video, or ``None``."""
        if not self.youtube_enabled or not (video_id or "").strip():
            return None

        key = youtube_video_cache_key(video_id)
        try:
            raw = await self.provider.get(key)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - cache failures are fail-open
            logger.warning("Review cache read failed for key '%s': %s", key, exc)
            self.yt_misses += 1
            return None

        if raw is None:
            self.yt_misses += 1
            return None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Discarding corrupted review cache entry '%s': %s", key, exc)
            self.yt_misses += 1
            return None

        if not isinstance(payload, dict) or not str(payload.get("transcript_text") or "").strip():
            # Comments-only entries are intentionally treated as misses so a
            # later batch can retry the expensive transcript fetch.
            self.yt_misses += 1
            return None

        self.yt_hits += 1
        return payload

    async def set_youtube_video(self, video_id: str, video_model: YouTubeVideo) -> None:
        """Cache immutable transcript/comment evidence for a video."""
        if not self.youtube_enabled or not (video_id or "").strip():
            return

        has_transcript = bool((video_model.transcript_text or "").strip())
        if not has_transcript:
            # Negative-cache guard: transient rate limits / missing captions must
            # never poison the 14-day cache with an empty evidence payload.
            return

        payload = {
            "transcript_text": video_model.transcript_text,
            "transcript_segments": [segment.model_dump(mode="json") for segment in video_model.transcript_segments],
            "language": video_model.language,
            "is_auto_generated_captions": video_model.is_auto_generated_captions,
            "top_comments": [comment.model_dump(mode="json") for comment in video_model.top_comments],
        }

        key = youtube_video_cache_key(video_id)
        try:
            encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            await self.provider.set(  # type: ignore[union-attr]
                key,
                encoded,
                ttl_seconds=self.youtube_ttl_seconds,
            )
            self.yt_stores += 1
        except Exception as exc:  # noqa: BLE001 - cache failures are fail-open
            logger.warning("Review cache write failed for key '%s': %s", key, exc)

    async def get_text(self, url: str) -> str | None:
        """Return a cached community page body, or ``None`` on miss/failure."""
        if not self.community_enabled or not normalize_cache_url(url):
            return None

        key = community_text_cache_key(url)
        try:
            raw = await self.provider.get(key)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - cache failures are fail-open
            logger.warning("Community cache read failed for key '%s': %s", key, exc)
            self.http_misses += 1
            return None

        if raw is None:
            self.http_misses += 1
            return None

        try:
            text = raw.decode("utf-8")
        except (AttributeError, UnicodeDecodeError) as exc:
            logger.warning("Discarding corrupted community cache entry '%s': %s", key, exc)
            self.http_misses += 1
            return None

        self.http_hits += 1
        return text

    async def set_text(self, url: str, text: str | None) -> None:
        """Cache a non-empty community page body."""
        if not self.community_enabled or not normalize_cache_url(url):
            return
        if not isinstance(text, str) or not text.strip():
            return

        key = community_text_cache_key(url)
        try:
            await self.provider.set(  # type: ignore[union-attr]
                key,
                text.encode("utf-8"),
                ttl_seconds=self.community_ttl_seconds,
            )
            self.http_stores += 1
        except Exception as exc:  # noqa: BLE001 - cache failures are fail-open
            logger.warning("Community cache write failed for key '%s': %s", key, exc)

    async def get_json(self, url: str) -> Any | None:
        """Return a cached community JSON payload, or ``None`` on miss/failure."""
        if not self.community_enabled or not normalize_cache_url(url):
            return None

        key = community_json_cache_key(url)
        try:
            raw = await self.provider.get(key)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - cache failures are fail-open
            logger.warning("Community cache read failed for key '%s': %s", key, exc)
            self.http_misses += 1
            return None

        if raw is None:
            self.http_misses += 1
            return None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Discarding corrupted community cache entry '%s': %s", key, exc)
            self.http_misses += 1
            return None

        self.http_hits += 1
        return payload

    async def set_json(self, url: str, value: Any) -> None:
        """Cache a non-null, JSON-serializable community payload."""
        if not self.community_enabled or not normalize_cache_url(url):
            return
        if value is None:
            return

        key = community_json_cache_key(url)
        try:
            encoded = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            await self.provider.set(  # type: ignore[union-attr]
                key,
                encoded,
                ttl_seconds=self.community_ttl_seconds,
            )
            self.http_stores += 1
        except Exception as exc:  # noqa: BLE001 - cache failures are fail-open
            logger.warning("Community cache write failed for key '%s': %s", key, exc)


__all__ = [
    "DEFAULT_COMMUNITY_TTL_SECONDS",
    "DEFAULT_YOUTUBE_TTL_SECONDS",
    "ReviewsPersistentCache",
    "community_json_cache_key",
    "community_text_cache_key",
    "normalize_cache_url",
    "youtube_video_cache_key",
]
