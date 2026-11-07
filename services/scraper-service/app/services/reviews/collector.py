"""Review collection orchestrator.

Application-layer use case that turns a ``ScrapeReviewsCommand`` into a single
S3 artifact and a ``reviews.ready.event``:

1. Map each ``LaptopReviewTarget`` into a ``LaptopChassisReviewItem``.
2. Run the YouTube collector, then the communities collector (sequential fold).
3. Aggregate batch metrics.
4. Upload ``raw_chassis_reviews_{job_id}.json`` to object storage.
5. Publish ``ReviewsReadyEvent`` carrying the S3 key.

All collaborators are constructor-injected so the use case is fully testable
without network, S3, or RabbitMQ.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

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
from app.services.reviews.contracts import (
    ICommunitiesReviewsCollector,
    IYouTubeReviewsCollector,
    StubCommunitiesReviewsCollector,
    StubYouTubeReviewsCollector,
)

logger = logging.getLogger("scraper.services.reviews.collector")

# Object storage prefix for generated review artifacts.
REVIEWS_S3_PREFIX = "reviews"


def build_s3_key(job_id: str) -> str:
    """Return the canonical object key for a job's raw reviews artifact."""
    return f"{REVIEWS_S3_PREFIX}/raw_chassis_reviews_{job_id}.json"


class ReviewCollectorService:
    """Orchestrates multi-platform review collection and artifact publication."""

    def __init__(
        self,
        storage_service: IObjectStorageService | None = None,
        broker: IMessageBroker | None = None,
        youtube_collector: IYouTubeReviewsCollector | None = None,
        communities_collector: ICommunitiesReviewsCollector | None = None,
    ) -> None:
        self.storage_service = storage_service or get_storage_service()
        self.broker = broker
        self.youtube_collector = youtube_collector or StubYouTubeReviewsCollector()
        self.communities_collector = communities_collector or StubCommunitiesReviewsCollector()

    async def process_reviews_batch(self, command: ScrapeReviewsCommand) -> str:
        """Collect reviews for every chassis target, upload the artifact, and emit the event.

        Args:
            command: The validated ``reviews.scrape.command`` message.

        Returns:
            The object storage key of the uploaded reviews artifact.
        """
        job_id = command.payload.job_id
        targets = command.payload.targets

        logger.info(
            "Processing reviews batch [job_id=%s] with %d chassis targets.",
            job_id,
            len(targets),
        )

        # 1. Map transport targets into domain review items.
        items = [self._to_review_item(target) for target in targets]

        # 2. Sequential enrichment: YouTube first, then communities.
        items = await self.youtube_collector.collect(items)
        items = await self.communities_collector.collect(items)

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

        # 5. Upload to object storage. ``upload_json`` is synchronous by contract.
        s3_key = build_s3_key(job_id)
        self.storage_service.upload_json(
            data=artifact.model_dump(mode="json"),
            object_key=s3_key,
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
    def _to_review_item(target: LaptopReviewTarget) -> LaptopChassisReviewItem:
        """Map one ``LaptopReviewTarget`` into a ``LaptopChassisReviewItem``."""
        matched_laptop_ids = list(target.matched_laptop_ids) or [target.laptop_id]
        matched_canonical_ids = list(target.matched_canonical_ids) or [target.canonical_id]

        return LaptopChassisReviewItem(
            chassis_key=ReviewCollectorService._chassis_key(target),
            primary_laptop_id=target.laptop_id,
            primary_canonical_id=target.canonical_id,
            matched_laptop_ids=matched_laptop_ids,
            matched_canonical_ids=matched_canonical_ids,
            identity=ChassisIdentity(
                brand=target.brand,
                laptop_family=target.laptop_family,
                laptop_model=target.laptop_model,
                aggregated_mpns=list(target.mpns),
                aggregated_skus=list(target.skus),
            ),
            youtube=YouTubeReviewData(),
            communities=CommunitiesData(),
        )

    @staticmethod
    def _chassis_key(target: LaptopReviewTarget) -> str:
        """Derive a stable chassis key from the target identity fields.

        Produces the same ``brand:family:sub_model`` shape the catalog-service
        resolver uses, so both services agree on chassis identity. The family
        prefix is stripped from the model to avoid ``lenovo:loq:loq-15irx9``.

        Falls back to the canonical id when identity fields are absent so the
        key is never blank.
        """
        brand = ReviewCollectorService._normalize_key_part(target.brand)
        family = ReviewCollectorService._normalize_key_part(target.laptop_family)
        model = ReviewCollectorService._normalize_key_part(target.laptop_model)

        if model and family:
            family_prefix = f"{family}-"
            if model.startswith(family_prefix):
                model = model[len(family_prefix) :]

        parts = [part for part in (brand, family, model) if part]
        if parts:
            return ":".join(parts)
        return str(target.canonical_id).strip().lower()

    @staticmethod
    def _normalize_key_part(value: str | None) -> str | None:
        """Lowercase and collapse non-alphanumerics to single hyphens."""
        if not value:
            return None
        cleaned = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
        return cleaned or None

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
            total_posts += len(communities.reddit) + len(communities.facebook)

        return BatchMetadataSummary(
            total_youtube_videos=total_videos,
            total_youtube_comments=total_comments,
            total_community_posts=total_posts,
        )


__all__ = ["REVIEWS_S3_PREFIX", "ReviewCollectorService", "build_s3_key"]
