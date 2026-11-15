"""Catalog Message Consumer for RabbitMQ Events.

Consumes events emitted by scraper-service and ai-recommender-service and
orchestrates database updates and post-commit cache invalidation:
- `catalog.ready.event` -> Downloads S3 catalog, runs in-memory metrics calculation,
  applies TOPSIS hook, and seeds relational database via CatalogIngestionService.
- `catalog.scrape.failed` -> Updates ScrapingBatchLog status to FAILED.
- `prices.checked.event` -> Applies price and stock verification via PriceSyncService.
- `reviews.enriched.event` -> Downloads enriched S3 reviews and persists SQL NLP profiles.
- `reviews.enrich.failed` -> Records failed enrichment audit entry in ScrapingBatchLog.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import ICacheProvider
from app.common.messaging.contract import IMessageBroker
from app.core.database import AsyncSessionLocal
from app.models.base import utcnow
from app.repositories.batch_log_repository import BatchLogRepository
from app.repositories.inbox_repository import InboxRepository
from app.schemas.events import (
    CatalogReadyEvent,
    CatalogScrapeFailedEvent,
    EventType,
    PricesCheckedEvent,
    ReviewsEnrichedEvent,
    ReviewsEnrichFailedEvent,
)
from app.services.catalog_ingestion_service import CatalogIngestionService
from app.services.price_sync_service import PriceSyncService
from app.services.review_intelligence_service import ReviewIntelligenceService

logger = logging.getLogger("catalog.messaging.consumer")


class CatalogMessageConsumer:
    """Worker service consuming RabbitMQ events and triggering catalog-service workflows."""

    def __init__(
        self,
        broker: IMessageBroker,
        session_factory: Callable[[], AsyncSession] | None = None,
        ingestion_service: CatalogIngestionService | None = None,
        price_sync_service: PriceSyncService | None = None,
        review_intelligence_service: ReviewIntelligenceService | None = None,
        cache: ICacheProvider | None = None,
    ) -> None:
        self.broker = broker
        self._session_factory = session_factory or AsyncSessionLocal
        self.ingestion_service = ingestion_service or CatalogIngestionService()
        self.price_sync_service = price_sync_service or PriceSyncService(cache=cache)
        self.review_intelligence_service = review_intelligence_service
        self.cache = cache
        self._is_listening: bool = False

    async def _invalidate_catalog_caches(self, *, include_price_history: bool = False) -> None:
        """Evict read-side catalog and recommendation cache namespaces after DB commit."""
        if not self.cache:
            return

        prefixes = ["catalog:browse", "catalog:laptop", "catalog:recommendation"]
        if include_price_history:
            prefixes.append("catalog:price_history")

        for prefix in prefixes:
            try:
                await self.cache.clear_prefix(prefix)
            except Exception as exc:
                logger.warning("Failed to invalidate cache prefix '%s': %s", prefix, exc)

    def _resolve_review_intelligence_service(self) -> ReviewIntelligenceService:
        if self.review_intelligence_service is None:
            self.review_intelligence_service = ReviewIntelligenceService()
        return self.review_intelligence_service

    async def _claim_inbox(self, session: AsyncSession, event: Any, handler_name: str) -> bool:
        """Claim an event inside the active transaction; False means duplicate."""
        claimed = await InboxRepository(session).claim_message(
            message_id=event.event_id,
            event_type=event.event_type,
            handler_name=handler_name,
        )
        if not claimed:
            logger.info(
                "Duplicate event [%s, event_type=%s] already processed by %s. Skipping.",
                event.event_id,
                event.event_type,
                handler_name,
            )
        return claimed

    async def start_listening(self) -> None:
        """Declare queues and register event consumer handlers on RabbitMQ."""
        if self._is_listening:
            logger.warning("CatalogMessageConsumer is already listening.")
            return

        logger.info("Registering CatalogMessageConsumer queue bindings...")

        # 1. Catalog Ready Event (Heavy ingestion -> prefetch 1)
        await self.broker.subscribe(
            queue_name="catalog.ready.jobs",
            routing_key=EventType.CATALOG_READY_EVENT,
            handler=self.handle_catalog_ready_event,
            prefetch_count=1,
        )

        # 2. Catalog Scrape Failed Event (Fast audit update -> prefetch 5)
        await self.broker.subscribe(
            queue_name="catalog.scrape.failed.jobs",
            routing_key=EventType.CATALOG_SCRAPE_FAILED_EVENT,
            handler=self.handle_catalog_scrape_failed,
            prefetch_count=5,
        )

        # 3. Prices Checked Event (Batch updates -> prefetch 5)
        await self.broker.subscribe(
            queue_name="catalog.prices.checked.jobs",
            routing_key=EventType.PRICES_CHECKED_EVENT,
            handler=self.handle_prices_checked_event,
            prefetch_count=5,
        )

        # 4. Reviews Enriched Event (Phase 2 -> prefetch 2)
        await self.broker.subscribe(
            queue_name="catalog.reviews.enriched.jobs",
            routing_key=EventType.REVIEWS_ENRICHED_EVENT,
            handler=self.handle_reviews_enriched_event,
            prefetch_count=2,
        )

        # 5. Reviews Enrich Failed Event (Fast audit update -> prefetch 5)
        await self.broker.subscribe(
            queue_name="catalog.reviews.enrich.failed.jobs",
            routing_key=EventType.REVIEWS_ENRICH_FAILED_EVENT,
            handler=self.handle_reviews_enrich_failed,
            prefetch_count=5,
        )

        self._is_listening = True
        logger.info("CatalogMessageConsumer is actively listening for domain events.")

    async def handle_catalog_ready_event(self, raw_data: dict[str, Any]) -> None:
        """Download catalog from S3, compute metrics, seed relational tables, and update batch log."""
        event = CatalogReadyEvent.model_validate(raw_data)
        payload = event.payload
        logger.info(
            "Processing CatalogReadyEvent [batch_id=%s, s3_key=%s, total=%d]",
            payload.batch_id,
            payload.s3_key,
            payload.total_laptops,
        )

        batch_uuid = uuid.UUID(payload.batch_id)

        async with self._session_factory() as session:
            async with session.begin():
                if not await self._claim_inbox(session, event, "handle_catalog_ready_event"):
                    return

                result = await self.ingestion_service.ingest_from_s3(
                    session=session,
                    s3_key=payload.s3_key,
                    trigger_type="CATALOG_READY_EVENT",
                    batch_id=batch_uuid,
                )

                if result.status != "SUCCESS":
                    logger.error(
                        "Catalog ingestion failed for batch [%s]: %s",
                        payload.batch_id,
                        result.error_message,
                    )
                    raise RuntimeError(f"Catalog ingestion failed: {result.error_message}")

                logger.info(
                    "CatalogReadyEvent successfully processed for batch [%s]: %d laptops ingested in %.2fs",
                    payload.batch_id,
                    result.total_laptops,
                    result.duration_seconds,
                )

        await self._invalidate_catalog_caches(include_price_history=True)

    async def handle_catalog_scrape_failed(self, raw_data: dict[str, Any]) -> None:
        """Mark ScrapingBatchLog as FAILED when scraper encounters fatal error."""
        event = CatalogScrapeFailedEvent.model_validate(raw_data)
        payload = event.payload
        logger.warning(
            "Processing CatalogScrapeFailedEvent [batch_id=%s]: %s",
            payload.batch_id,
            payload.error_message,
        )

        batch_uuid = uuid.UUID(payload.batch_id)

        async with self._session_factory() as session:
            async with session.begin():
                if not await self._claim_inbox(session, event, "handle_catalog_scrape_failed"):
                    return

                batch_repo = BatchLogRepository(session)
                existing = await batch_repo.get_by_id(batch_uuid)

                if existing:
                    existing.status = "FAILED"
                    existing.error_message = payload.error_message
                    existing.completed_at = utcnow()
                else:
                    await batch_repo.record_batch_log(
                        batch_id=batch_uuid,
                        store_key="multi-store",
                        trigger_type="SCRAPE_FAILED",
                        status="FAILED",
                        error_message=payload.error_message,
                    )

                logger.info("ScrapingBatchLog [%s] marked as FAILED in catalog database.", payload.batch_id)

    async def handle_prices_checked_event(self, raw_data: dict[str, Any]) -> None:
        """Apply verified price/stock batch results and update offer & metrics state."""
        event = PricesCheckedEvent.model_validate(raw_data)
        payload = event.payload
        logger.info(
            "Processing PricesCheckedEvent [batch_id=%s, store=%s, total=%d, changed=%d]",
            payload.batch_id,
            payload.store_key,
            payload.total_items,
            payload.changed_items_count,
        )

        summary = None
        async with self._session_factory() as session:
            async with session.begin():
                if not await self._claim_inbox(session, event, "handle_prices_checked_event"):
                    return

                summary = await self.price_sync_service.apply_batch_results(
                    session=session,
                    batch_response=payload.model_dump(),
                    commit=False,
                )

                logger.info(
                    "PricesCheckedEvent applied for batch [%s]: %d offers updated (%d drops, %d hikes, %d OOS)",
                    payload.batch_id,
                    summary.offers_updated,
                    summary.price_drops_detected,
                    summary.price_hikes_detected,
                    summary.out_of_stock_detected,
                )

            if summary and summary.affected_laptop_ids:
                await self.price_sync_service.invalidate_caches(
                    session,
                    summary.affected_laptop_ids,
                )

    async def handle_reviews_enriched_event(self, raw_data: dict[str, Any]) -> None:
        """Persist enriched community review intelligence into PostgreSQL."""
        event = ReviewsEnrichedEvent.model_validate(raw_data)
        payload = event.payload
        logger.info(
            "Processing ReviewsEnrichedEvent [job_id=%s, chassis=%d, laptops=%d, s3_key=%s]",
            payload.job_id,
            payload.total_chassis,
            payload.total_laptops,
            payload.s3_key,
        )

        if not payload.s3_key:
            logger.info(
                "ReviewsEnrichedEvent [%s] has no s3_key; nothing to ingest into PostgreSQL.",
                payload.job_id,
            )
            return

        async with self._session_factory() as session:
            async with session.begin():
                if not await self._claim_inbox(session, event, "handle_reviews_enriched_event"):
                    return

                result = await self._resolve_review_intelligence_service().ingest_from_s3(
                    session=session,
                    s3_key=payload.s3_key,
                    commit=False,
                )

        if isinstance(result.sql_laptops_updated, int) and result.sql_laptops_updated > 0:
            await self._invalidate_catalog_caches()

        logger.info(
            "ReviewsEnrichedEvent [%s] ingested: status=%s, chassis=%d, sql_laptops=%d",
            payload.job_id,
            result.status,
            result.chassis_processed,
            result.sql_laptops_updated,
        )

    async def handle_reviews_enrich_failed(self, raw_data: dict[str, Any]) -> None:
        """Record a failed ScrapingBatchLog entry when AI review enrichment fails."""
        event = ReviewsEnrichFailedEvent.model_validate(raw_data)
        payload = event.payload
        logger.warning(
            "Processing ReviewsEnrichFailedEvent [job_id=%s, s3_key=%s]: %s",
            payload.job_id,
            payload.s3_key,
            payload.error_message,
        )

        audit_uuid = uuid.uuid5(uuid.NAMESPACE_OID, f"reviews-enrich-failed:{payload.job_id}")
        formatted_error = f"[{payload.job_id}] {payload.error_message}"

        async with self._session_factory() as session:
            async with session.begin():
                if not await self._claim_inbox(session, event, "handle_reviews_enrich_failed"):
                    return

                batch_repo = BatchLogRepository(session)
                existing = await batch_repo.get_by_id(audit_uuid)
                if existing:
                    existing.status = "FAILED"
                    existing.error_message = formatted_error
                    existing.completed_at = utcnow()
                else:
                    await batch_repo.record_batch_log(
                        batch_id=audit_uuid,
                        store_key="reviews_enrichment",
                        trigger_type="REVIEWS_ENRICH_FAILED",
                        status="FAILED",
                        error_message=formatted_error,
                    )

                logger.info(
                    "ScrapingBatchLog [%s] marked as FAILED for review enrichment job [%s].",
                    audit_uuid,
                    payload.job_id,
                )
