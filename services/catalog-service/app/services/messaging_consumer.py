"""Catalog Message Consumer for RabbitMQ Events.

Consumes events emitted by scraper-service and orchestrates database updates:
- `catalog.ready.event` -> Downloads S3 catalog, runs in-memory metrics calculation,
  applies TOPSIS hook, and seeds relational database via CatalogIngestionService.
- `catalog.scrape.failed` -> Updates ScrapingBatchLog status to FAILED.
- `prices.checked.event` -> Applies price and stock verification via PriceSyncService.
- `reviews.ready.event` -> Receives community review analysis (Phase 2).
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.messaging.contract import IMessageBroker
from app.core.database import AsyncSessionLocal
from app.models.base import utcnow
from app.repositories.batch_log_repository import BatchLogRepository
from app.schemas.events import (
    CatalogReadyEvent,
    CatalogScrapeFailedEvent,
    EventType,
    PricesCheckedEvent,
    ReviewsReadyEvent,
)
from app.services.catalog_ingestion_service import CatalogIngestionService
from app.services.price_sync_service import PriceSyncService

logger = logging.getLogger("catalog.messaging.consumer")


class CatalogMessageConsumer:
    """Worker service consuming RabbitMQ events and triggering catalog-service workflows."""

    def __init__(
        self,
        broker: IMessageBroker,
        session_factory: Callable[[], AsyncSession] | None = None,
        ingestion_service: CatalogIngestionService | None = None,
        price_sync_service: PriceSyncService | None = None,
    ) -> None:
        self.broker = broker
        self._session_factory = session_factory or AsyncSessionLocal
        self.ingestion_service = ingestion_service or CatalogIngestionService()
        self.price_sync_service = price_sync_service or PriceSyncService()
        self._is_listening: bool = False

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

        # 4. Reviews Ready Event (Phase 2 -> prefetch 2)
        await self.broker.subscribe(
            queue_name="catalog.reviews.ready.jobs",
            routing_key=EventType.REVIEWS_READY_EVENT,
            handler=self.handle_reviews_ready_event,
            prefetch_count=2,
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

        async with self._session_factory() as session:
            async with session.begin():
                summary = await self.price_sync_service.apply_batch_results(
                    session=session,
                    batch_response=payload.model_dump(),
                )

                logger.info(
                    "PricesCheckedEvent applied for batch [%s]: %d offers updated (%d drops, %d hikes, %d OOS)",
                    payload.batch_id,
                    summary.offers_updated,
                    summary.price_drops_detected,
                    summary.price_hikes_detected,
                    summary.out_of_stock_detected,
                )

    async def handle_reviews_ready_event(self, raw_data: dict[str, Any]) -> None:
        """Process extracted community review snippets (Phase 2)."""
        event = ReviewsReadyEvent.model_validate(raw_data)
        payload = event.payload
        logger.info(
            "Processing ReviewsReadyEvent [job_id=%s, laptops=%d, snippets=%d]",
            payload.job_id,
            payload.total_laptops,
            payload.total_snippets,
        )
        # Phase 2: NLP ingestion hook
