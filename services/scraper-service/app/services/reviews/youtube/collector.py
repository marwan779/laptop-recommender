"""Concrete YouTube reviews collector.

Implements ``IYouTubeReviewsCollector`` (Pattern B): accepts the review targets
and returns a pure ``chassis_key -> YouTubeReviewData`` mapping. It performs no
file or object-storage I/O — the orchestrator owns persistence.

Pipeline per target:
    1. Build prioritized queries (English primary, Arabic secondary).
    2. Search YouTube for the primary query.
    3. If too few results, top up with the secondary query (deduplicated).
    4. Fetch transcripts for each unique video (cached across targets).
    5. Assemble ``YouTubeVideo`` -> ``YouTubeReviewData``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.domain.reviews.queries import YouTubeQueryBuilder
from app.domain.reviews.relevance import matches_target_text
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import YouTubeComment, YouTubeReviewData, YouTubeVideo
from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.contracts import IYouTubeReviewsCollector
from app.services.reviews.youtube.search import YouTubeSearchService
from app.services.reviews.youtube.transcript import YouTubeTranscriptService

logger = logging.getLogger("scraper.services.reviews.youtube.collector")

# Minimum videos before trying the secondary (Arabic) query.
_MIN_RESULTS_BEFORE_FALLBACK = 2


class YouTubeReviewsCollector(IYouTubeReviewsCollector):
    """Collect YouTube review evidence for every chassis target."""

    def __init__(
        self,
        query_builder: YouTubeQueryBuilder | None = None,
        search_service: YouTubeSearchService | None = None,
        transcript_service: YouTubeTranscriptService | None = None,
    ) -> None:
        self.query_builder = query_builder or YouTubeQueryBuilder()
        self.search_service = search_service or YouTubeSearchService()
        self.transcript_service = transcript_service or YouTubeTranscriptService()

        # Batch-level single-flight caches & per-key locks so neither identical
        # search queries nor shared video IDs are scraped twice in one batch.
        self._search_cache: dict[str, list[dict[str, Any]]] = {}
        self._search_locks: dict[str, asyncio.Lock] = {}
        self._video_cache: dict[str, YouTubeVideo] = {}
        self._video_locks: dict[str, asyncio.Lock] = {}

    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
        concurrency: int = 2,
    ) -> dict[str, YouTubeReviewData]:
        """Return ``chassis_key -> YouTubeReviewData`` for every target."""
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _collect(target: LaptopReviewTarget) -> tuple[str, YouTubeReviewData]:
            chassis_key = build_chassis_key(target)
            async with semaphore:
                try:
                    data = await self._collect_for_target(target)
                    return chassis_key, data
                except Exception as exc:  # noqa: BLE001 - one target must not abort the batch
                    logger.warning(
                        "YouTube collection failed for chassis '%s': %s",
                        chassis_key,
                        exc,
                    )
                    return chassis_key, YouTubeReviewData()

        collected = await asyncio.gather(*[_collect(target) for target in targets])
        return dict(collected)

    async def _search_cached(self, query: str) -> list[dict[str, Any]]:
        """Single-flight search cache keyed by normalized query string."""
        norm_key = " ".join((query or "").lower().split())
        if not norm_key:
            return []

        cached = self._search_cache.get(norm_key)
        if cached is not None:
            return cached

        lock = self._search_locks.setdefault(norm_key, asyncio.Lock())
        async with lock:
            cached = self._search_cache.get(norm_key)
            if cached is not None:
                return cached
            results = await self.search_service.search_reviews(query)
            self._search_cache[norm_key] = results
            return results

    @staticmethod
    def _filter_for_target(
        target: LaptopReviewTarget,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply strict Fix 2 domain relevance & device/accessory vetoing."""
        accepted: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw in candidates:
            vid = str(raw.get("video_id") or "")
            if vid and vid in seen_ids:
                continue
            title = str(raw.get("title") or "")
            channel = str(raw.get("channel_name") or "")
            url = str(raw.get("video_url") or "")
            if not matches_target_text(target, title, channel, url, require_brand=True):
                continue
            if vid:
                seen_ids.add(vid)
            accepted.append(raw)
        return accepted

    async def _collect_for_target(self, target: LaptopReviewTarget) -> YouTubeReviewData:
        """Collect and assemble YouTube data for a single target."""
        queries = self.query_builder.build_queries(target)
        primary_query = queries[0] if queries else f"{target.brand} {target.laptop_model} review"
        queries_used: list[str] = [primary_query]

        primary_raw = await self._search_cached(primary_query)
        found_videos = self._filter_for_target(target, primary_raw)

        # Top up with the secondary query when relevant yield is thin.
        if len(found_videos) < _MIN_RESULTS_BEFORE_FALLBACK and len(queries) > 1:
            queries_used.append(queries[1])
            found_videos = await self._merge_secondary(
                target,
                found_videos,
                queries[1],
            )

        video_models = list(await asyncio.gather(*[self._to_video_model(video) for video in found_videos]))

        return YouTubeReviewData(
            query_used=" | ".join(dict.fromkeys(q for q in queries_used if q)),
            total_videos_found=len(video_models),
            videos=video_models,
        )

    async def _merge_secondary(
        self,
        target: LaptopReviewTarget,
        primary_videos: list[dict[str, Any]],
        secondary_query: str,
    ) -> list[dict[str, Any]]:
        """Append relevant, deduplicated secondary-query results to the primary list."""
        try:
            secondary_raw = await self._search_cached(secondary_query)
        except Exception as exc:  # noqa: BLE001 - secondary is best-effort
            logger.debug("Secondary YouTube query failed (%r): %s", secondary_query, exc)
            return primary_videos

        filtered_secondary = self._filter_for_target(target, secondary_raw)
        merged = list(primary_videos)
        existing_ids = {video.get("video_id") for video in merged}
        for video in filtered_secondary:
            video_id = video.get("video_id")
            if video_id and video_id not in existing_ids:
                merged.append(video)
                existing_ids.add(video_id)
        return merged

    async def _to_video_model(self, video: dict[str, Any]) -> YouTubeVideo:
        """Convert a search-result dict into a fully populated ``YouTubeVideo``.

        Results are cached per ``video_id`` for the lifetime of the collector so
        transcripts and top comments for a video shared by multiple targets are
        only fetched once.
        """
        video_id = str(video.get("video_id") or "")

        if not video_id:
            return await self._build_video_model(video_id, video)

        cached = self._video_cache.get(video_id)
        if cached is not None:
            return cached

        lock = self._video_locks.setdefault(video_id, asyncio.Lock())
        async with lock:
            cached = self._video_cache.get(video_id)
            if cached is not None:
                return cached

            model = await self._build_video_model(video_id, video)
            self._video_cache[video_id] = model
            return model

    async def _build_video_model(self, video_id: str, video: dict[str, Any]) -> YouTubeVideo:
        """Fetch transcript (and deferred top comments) once per unique video."""
        video_url = str(video.get("video_url") or f"https://www.youtube.com/watch?v={video_id}")

        needs_comments = bool(video.get("comments_deferred")) or ("top_comments" not in video)
        can_fetch_comments = needs_comments and callable(getattr(self.search_service, "fetch_top_comments", None))

        if can_fetch_comments:
            transcript_res, fetched_comments = await asyncio.gather(
                self.transcript_service.fetch_transcript(video_id),
                self.search_service.fetch_top_comments(video_url),
            )
            top_comments = [
                c
                for c in (fetched_comments if isinstance(fetched_comments, list) else [])
                if isinstance(c, YouTubeComment)
            ]
        else:
            transcript_res = await self.transcript_service.fetch_transcript(video_id)
            top_comments = list(video.get("top_comments") or [])

        transcript_text, segments, language, is_auto = transcript_res

        return YouTubeVideo(
            video_id=video_id,
            title=str(video.get("title") or ""),
            channel_name=video.get("channel_name"),
            channel_url=video.get("channel_url"),
            video_url=video_url,
            published_at=video.get("published_at"),
            duration_seconds=video.get("duration_seconds"),
            view_count=video.get("view_count"),
            language=language,
            is_auto_generated_captions=is_auto,
            transcript_text=transcript_text,
            transcript_segments=segments,
            top_comments=top_comments,
        )


__all__ = ["YouTubeReviewsCollector"]
