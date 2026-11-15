"""RabbitMQ Message Consumer for ai-recommender-service.

Listens for `reviews.ready.event` emitted by scraper-service, guards idempotency
through the distributed Redis inbox, runs the S3 -> Enrich -> ChromaDB -> S3 pipeline,
and emits `reviews.enriched.event` (or `reviews.enrich.failed` on fatal failure).
"""

from __future__ import annotations

from typing import Any, Optional

from app.common.logger import get_logger
from app.common.messaging.contract import IMessageBroker
from app.common.messaging.inbox import RedisInboxDeduplicator
from app.schemas.events import (
    EventType,
    ReviewsEnrichedEvent,
    ReviewsEnrichFailedEvent,
    ReviewsEnrichFailedPayload,
    ReviewsReadyEvent,
)
from app.services.reviews_pipeline_service import ReviewsPipelineService

logger = get_logger("ai_recommender.messaging.consumer")


class AIRecommenderMessageConsumer:
    """Broker consumer coordinating Stage 2 AI review enrichment jobs."""

    QUEUE_REVIEWS_READY = "ai.reviews.ready.jobs"

    def __init__(
        self,
        broker: IMessageBroker,
        inbox: Optional[RedisInboxDeduplicator] = None,
        pipeline_service: Optional[ReviewsPipelineService] = None,
    ) -> None:
        self.broker = broker
        self.inbox = inbox
        self._pipeline_service = pipeline_service
        self._is_listening: bool = False

    def _resolve_pipeline_service(self) -> ReviewsPipelineService:
        if self._pipeline_service is None:
            self._pipeline_service = ReviewsPipelineService()
        return self._pipeline_service

    async def start_listening(self) -> None:
        """Declare queues and bind event consumers on the RabbitMQ broker."""
        if self._is_listening:
            logger.warning("AIRecommenderMessageConsumer is already listening.")
            return

        logger.info("Registering AIRecommenderMessageConsumer queue bindings...")
        await self.broker.subscribe(
            queue_name=self.QUEUE_REVIEWS_READY,
            routing_key=EventType.REVIEWS_READY_EVENT,
            handler=self.handle_reviews_ready_event,
            prefetch_count=1,
        )
        self._is_listening = True
        logger.info("AIRecommenderMessageConsumer is actively listening for reviews.ready.event.")

    async def _claim(self, event_id: str, event_type: str) -> bool:
        if self.inbox is None:
            return True
        claimed = await self.inbox.claim_message(event_id, event_type)
        if not claimed:
            logger.info(
                "Duplicate event [%s, event_type=%s] already claimed/processed. Skipping.",
                event_id,
                event_type,
            )
        return claimed

    async def _complete(self, event_id: str) -> None:
        if self.inbox is not None:
            await self.inbox.mark_completed(event_id)

    async def _release(self, event_id: str) -> None:
        if self.inbox is not None:
            await self.inbox.release_claim(event_id)

    async def _publish_failure_event(
        self,
        *,
        job_id: str,
        s3_key: Optional[str],
        correlation_id: str,
        exc: Exception,
    ) -> None:
        failure_event = ReviewsEnrichFailedEvent(
            correlation_id=correlation_id,
            payload=ReviewsEnrichFailedPayload(
                job_id=job_id,
                error_message=str(exc) or type(exc).__name__,
                s3_key=s3_key,
                details={"exception_type": type(exc).__name__},
            ),
        )
        try:
            await self.broker.publish(
                routing_key=EventType.REVIEWS_ENRICH_FAILED_EVENT,
                message=failure_event,
            )
        except Exception as pub_exc:
            logger.warning(
                "Failed to publish ReviewsEnrichFailedEvent for job [%s]: %s",
                job_id,
                pub_exc,
            )

    async def handle_reviews_ready_event(self, raw_data: dict[str, Any]) -> None:
        """Consume `reviews.ready.event`, enrich + upsert Chroma, upload S3, and publish result."""
        event = ReviewsReadyEvent.model_validate(raw_data)
        payload = event.payload

        logger.info(
            "Processing ReviewsReadyEvent [job_id=%s, laptops=%d, chassis=%d, s3_key=%s]",
            payload.job_id,
            payload.total_laptops,
            payload.total_chassis,
            payload.s3_key,
        )

        if not payload.s3_key:
            logger.info(
                "ReviewsReadyEvent [%s] has no s3_key; nothing to enrich.",
                payload.job_id,
            )
            return

        if not await self._claim(event.event_id, event.event_type):
            return

        try:
            enriched_payload = await self._resolve_pipeline_service().process_reviews_ready(
                job_id=payload.job_id,
                s3_key=payload.s3_key,
            )
            enriched_event = ReviewsEnrichedEvent(
                correlation_id=event.correlation_id,
                payload=enriched_payload,
            )
            await self.broker.publish(
                routing_key=EventType.REVIEWS_ENRICHED_EVENT,
                message=enriched_event,
            )
            await self._complete(event.event_id)
        except Exception as exc:
            logger.error(
                "ReviewsReadyEvent processing failed [job_id=%s, s3_key=%s]: %s",
                payload.job_id,
                payload.s3_key,
                exc,
                exc_info=True,
            )
            await self._publish_failure_event(
                job_id=payload.job_id,
                s3_key=payload.s3_key,
                correlation_id=event.correlation_id,
                exc=exc,
            )
            await self._release(event.event_id)
            raise


__all__ = ["AIRecommenderMessageConsumer"]
