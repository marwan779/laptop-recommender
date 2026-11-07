"""Concrete YouTube reviews collector.

Implements ``IYouTubeReviewsCollector`` (Pattern B): accepts the review targets
and returns a pure ``chassis_key -> YouTubeReviewData`` mapping. It performs no
file or object-storage I/O — the orchestrator owns persistence.

Pipeline per target:
    1. Build prioritized queries (English primary, Arabic secondary).
    2. Search YouTube for the primary query.
    3. If too few results, top up with the secondary query (deduplicated).
    4. Fetch transcripts for each video.
    5. Assemble ``YouTubeVideo`` -> ``YouTubeReviewData``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.reviews.queries import YouTubeQueryBuilder
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import YouTubeReviewData, YouTubeVideo
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

    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
    ) -> dict[str, YouTubeReviewData]:
        """Return ``chassis_key -> YouTubeReviewData`` for every target."""
        results: dict[str, YouTubeReviewData] = {}

        for target in targets:
            chassis_key = build_chassis_key(target)
            try:
                results[chassis_key] = await self._collect_for_target(target)
            except Exception as exc:  # noqa: BLE001 - one target must not abort the batch
                logger.warning(
                    "YouTube collection failed for chassis '%s': %s",
                    chassis_key,
                    exc,
                )
                results[chassis_key] = YouTubeReviewData()

        return results

    async def _collect_for_target(self, target: LaptopReviewTarget) -> YouTubeReviewData:
        """Collect and assemble YouTube data for a single target."""
        queries = self.query_builder.build_queries(target)
        primary_query = queries[0] if queries else f"{target.brand} {target.laptop_model} review"

        found_videos = await self.search_service.search_reviews(primary_query)

        # Top up with the secondary query when the primary yield is thin.
        if len(found_videos) < _MIN_RESULTS_BEFORE_FALLBACK and len(queries) > 1:
            found_videos = await self._merge_secondary(
                found_videos,
                queries[1],
            )

        video_models = [await self._to_video_model(video) for video in found_videos]

        return YouTubeReviewData(
            query_used=primary_query,
            total_videos_found=len(video_models),
            videos=video_models,
        )

    async def _merge_secondary(
        self,
        primary_videos: list[dict[str, Any]],
        secondary_query: str,
    ) -> list[dict[str, Any]]:
        """Append de-duplicated secondary-query results to the primary list."""
        try:
            secondary_videos = await self.search_service.search_reviews(secondary_query)
        except Exception as exc:  # noqa: BLE001 - secondary is best-effort
            logger.debug("Secondary YouTube query failed (%r): %s", secondary_query, exc)
            return primary_videos

        merged = list(primary_videos)
        existing_ids = {video.get("video_id") for video in merged}
        for video in secondary_videos:
            video_id = video.get("video_id")
            if video_id and video_id not in existing_ids:
                merged.append(video)
                existing_ids.add(video_id)
        return merged

    async def _to_video_model(self, video: dict[str, Any]) -> YouTubeVideo:
        """Convert a search-result dict into a fully populated ``YouTubeVideo``."""
        video_id = str(video.get("video_id") or "")

        transcript_text, segments, language, is_auto = await self.transcript_service.fetch_transcript(video_id)

        return YouTubeVideo(
            video_id=video_id,
            title=str(video.get("title") or ""),
            channel_name=video.get("channel_name"),
            channel_url=video.get("channel_url"),
            video_url=str(video.get("video_url") or f"https://www.youtube.com/watch?v={video_id}"),
            published_at=video.get("published_at"),
            duration_seconds=video.get("duration_seconds"),
            view_count=video.get("view_count"),
            language=language,
            is_auto_generated_captions=is_auto,
            transcript_text=transcript_text,
            transcript_segments=segments,
            top_comments=list(video.get("top_comments") or []),
        )


__all__ = ["YouTubeReviewsCollector"]
