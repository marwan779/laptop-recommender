"""Review collection orchestrator.

The **only** class that persists review artifacts and emits
``reviews.ready.event``. Collectors are pure data producers (Pattern B):

    youtube_collector.collect_for_targets(targets)      -> dict[chassis_key, YouTubeReviewData]
    communities_collector.collect_for_targets(targets)  -> dict[chassis_key, CommunitiesData]

The orchestrator merges those mappings with chassis identity into
``LaptopChassisReviewItem`` models, assembles the ``RawChassisReviewsFile``,
uploads it to object storage, and publishes the ready event.

All collaborators are constructor-injected, so the use case is fully testable
without network, S3, or RabbitMQ.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.common.messaging.contract import IMessageBroker
from app.common.storage.base import IObjectStorageService
from app.common.storage.factory import get_storage_service
from app.schemas.events import (
    EventType,
    LaptopReviewTarget,
    ReviewsReadyEvent,
    ReviewsReadyPayload,
    ScrapeReviewsCommand,
)
from app.schemas.reviews_s3 import (
    BatchMetadata,
    BatchMetadataSummary,
    ChassisIdentity,
    CommunitiesData,
    LaptopChassisReviewItem,
    RawChassisReviewsFile,
    YouTubeReviewData,
)
from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.community.collector import CommunitiesReviewsCollector
from app.services.reviews.contracts import (
    ICommunitiesReviewsCollector,
    IYouTubeReviewsCollector,
)
from app.services.reviews.youtube.collector import YouTubeReviewsCollector

logger = logging.getLogger("scraper.services.reviews.collector")

# Object storage prefix for generated review artifacts.
REVIEWS_S3_PREFIX = "reviews"

# Service root: app/services/reviews/collector.py -> app/services/reviews -> app/services -> app -> service root
SERVICE_ROOT = Path(__file__).resolve().parents[3]

# Local inspection copy of every generated artifact, independent of S3.
LOCAL_REVIEWS_DIR = SERVICE_ROOT / "scraping results" / "reviews"


def build_s3_key(job_id: str) -> str:
    """Return the canonical object key for a job's raw reviews artifact."""
    return f"{REVIEWS_S3_PREFIX}/raw_chassis_reviews_{job_id}.json"


def build_local_path(job_id: str, output_dir: Path) -> Path:
    """Return the local inspection path for a job's raw reviews artifact."""
    return output_dir / f"raw_chassis_reviews_{job_id}.json"


class ReviewCollectorService:
    """Orchestrates multi-platform review collection and artifact publication."""

    def __init__(
        self,
        storage_service: IObjectStorageService | None = None,
        broker: IMessageBroker | None = None,
        youtube_collector: IYouTubeReviewsCollector | None = None,
        communities_collector: ICommunitiesReviewsCollector | None = None,
        upload_to_s3: bool = True,
        local_output_dir: Path | None = None,
    ) -> None:
        self.storage_service = storage_service or get_storage_service()
        self.broker = broker
        self.youtube_collector = youtube_collector or YouTubeReviewsCollector()
        self.communities_collector = communities_collector or CommunitiesReviewsCollector()
        self.upload_to_s3 = upload_to_s3
        self.local_output_dir = Path(local_output_dir) if local_output_dir else LOCAL_REVIEWS_DIR

    async def process_reviews_batch(self, command: ScrapeReviewsCommand) -> str:
        """Collect reviews for every chassis target, persist the artifact, and emit the event.

        The artifact is always written to ``local_output_dir`` for manual
        inspection. It is additionally uploaded to object storage unless this
        service was constructed with ``upload_to_s3=False``.

        Args:
            command: The validated ``reviews.scrape.command`` message.

        Returns:
            The object storage key of the uploaded artifact, or the local file
            path when S3 upload is disabled.
        """
        job_id = command.payload.job_id
        targets = command.payload.targets

        logger.info(
            "Processing reviews batch [job_id=%s] with %d chassis targets.",
            job_id,
            len(targets),
        )

        # 1. Run the platform collectors independently, in parallel.
        youtube_map, communities_map = await self._collect_platforms(targets)

        # 2. Merge platform outputs with chassis identity.
        items = [self._assemble_item(target, youtube_map, communities_map) for target in targets]

        # 3. Aggregate batch-level metrics.
        metrics_summary = self._summarize(items)

        # 4. Assemble the root artifact.
        artifact = RawChassisReviewsFile(
            batch_metadata=BatchMetadata(
                job_id=job_id,
                generated_at=datetime.now(UTC),
                total_targets_processed=len(items),
                metrics_summary=metrics_summary,
            ),
            laptops=items,
        )

        # 5. Always persist a local inspection copy, then optionally upload to S3.
        artifact_data = artifact.model_dump(mode="json")
        local_path = build_local_path(job_id, self.local_output_dir)
        self._write_local_artifact(artifact_data, local_path)

        if self.upload_to_s3:
            s3_key = build_s3_key(job_id)
            self.storage_service.upload_json(
                data=artifact_data,
                object_key=s3_key,
            )
        else:
            s3_key = str(local_path)
            logger.info(
                "S3 upload disabled [job_id=%s]; using local artifact path '%s'.",
                job_id,
                s3_key,
            )

        total_laptops = sum(len(item.matched_laptop_ids) for item in items)
        logger.info(
            "Uploaded reviews artifact [job_id=%s] to '%s': %d chassis, %d laptops, %d videos, %d community posts.",
            job_id,
            s3_key,
            len(items),
            total_laptops,
            metrics_summary.total_youtube_videos,
            metrics_summary.total_community_posts,
        )

        # 6. Publish the ready event when a broker is available.
        if self.broker is not None:
            event = ReviewsReadyEvent(
                correlation_id=command.correlation_id,
                payload=ReviewsReadyPayload(
                    job_id=job_id,
                    s3_key=s3_key,
                    total_chassis=len(items),
                    total_laptops=total_laptops,
                    total_snippets=0,
                    results=[],
                ),
            )
            await self.broker.publish(
                routing_key=EventType.REVIEWS_READY_EVENT,
                message=event,
            )
            logger.info("Published ReviewsReadyEvent for job [%s].", job_id)

        return s3_key

    @staticmethod
    def _write_local_artifact(artifact_data: dict, local_path: Path) -> None:
        """Write the artifact JSON to disk, creating parent directories."""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as handle:
            json.dump(artifact_data, handle, indent=2, ensure_ascii=False, default=str)
        logger.info("Saved local reviews artifact to '%s'.", local_path)

    async def _collect_platforms(
        self,
        targets: list[LaptopReviewTarget],
    ) -> tuple[dict[str, YouTubeReviewData], dict[str, CommunitiesData]]:
        """Run both collectors independently and in parallel.

        A failure in one platform must not prevent the other from contributing,
        so each task is wrapped with ``return_exceptions``.
        """
        raw_results = await asyncio.gather(
            self.youtube_collector.collect_for_targets(targets),
            self.communities_collector.collect_for_targets(targets),
            return_exceptions=True,
        )

        youtube_map = self._coerce_result(
            raw_results[0],
            label="youtube",
            empty={},
        )
        communities_map = self._coerce_result(
            raw_results[1],
            label="communities",
            empty={},
        )
        return youtube_map, communities_map

    @staticmethod
    def _coerce_result(
        result: object,
        *,
        label: str,
        empty: dict,
    ) -> dict:
        """Normalize a collector outcome, logging and falling back on failure."""
        if isinstance(result, BaseException):
            logger.warning("%s collector failed: %s", label.capitalize(), result)
            return empty
        if not isinstance(result, dict):
            logger.warning("%s collector returned an unexpected type: %r", label.capitalize(), type(result))
            return empty
        return result

    def _assemble_item(
        self,
        target: LaptopReviewTarget,
        youtube_map: dict[str, YouTubeReviewData],
        communities_map: dict[str, CommunitiesData],
    ) -> LaptopChassisReviewItem:
        """Merge one target's identity with its collected platform data."""
        chassis_key = build_chassis_key(target)

        return LaptopChassisReviewItem(
            chassis_key=chassis_key,
            primary_laptop_id=target.laptop_id,
            primary_canonical_id=target.canonical_id,
            matched_laptop_ids=list(target.matched_laptop_ids) or [target.laptop_id],
            matched_canonical_ids=list(target.matched_canonical_ids) or [target.canonical_id],
            identity=ChassisIdentity(
                brand=target.brand,
                laptop_family=target.laptop_family,
                laptop_model=target.laptop_model,
                aggregated_mpns=list(target.mpns),
                aggregated_skus=list(target.skus),
            ),
            youtube=youtube_map.get(chassis_key, YouTubeReviewData()),
            communities=communities_map.get(chassis_key, CommunitiesData()),
        )

    @staticmethod
    def _summarize(items: list[LaptopChassisReviewItem]) -> BatchMetadataSummary:
        """Count videos, comments, and community posts across all items."""
        total_videos = 0
        total_comments = 0
        total_posts = 0

        for item in items:
            youtube = item.youtube
            total_videos += len(youtube.videos)
            total_comments += sum(len(video.top_comments) for video in youtube.videos)

            communities = item.communities
            total_posts += (
                len(communities.reddit)
                + len(communities.facebook)
                + len(communities.editorial)
                + len(communities.discussions)
            )

        return BatchMetadataSummary(
            total_youtube_videos=total_videos,
            total_youtube_comments=total_comments,
            total_community_posts=total_posts,
        )


__all__ = [
    "LOCAL_REVIEWS_DIR",
    "REVIEWS_S3_PREFIX",
    "ReviewCollectorService",
    "build_local_path",
    "build_s3_key",
]
