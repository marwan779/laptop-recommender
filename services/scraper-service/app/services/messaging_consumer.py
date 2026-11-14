"""Event consumer and worker dispatcher for RabbitMQ incoming commands.

Coordinates between incoming message queues and domain pipelines:
- Listens for `catalog.scrape.command` -> executes ScrapeOrchestrator -> publishes `catalog.ready.event`
- Listens for `prices.check.command` -> executes PriceMonitorService -> publishes `prices.checked.event`
- Listens for `reviews.scrape.command` -> extracts community reviews -> publishes `reviews.ready.event`
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.common.messaging.contract import IMessageBroker
from app.common.messaging.inbox import RedisInboxDeduplicator
from app.price_monitor.models import PriceCheckBatchRequest
from app.price_monitor.service import PriceMonitorService
from app.schemas.events import (
    CatalogReadyEvent,
    CatalogReadyPayload,
    CatalogScrapeFailedEvent,
    CatalogScrapeFailedPayload,
    CheckPricesCommand,
    EventType,
    PricesCheckedEvent,
    PricesCheckedPayload,
    ScrapeCatalogCommand,
    ScrapeReviewsCommand,
)
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse
from app.services.orchestrator import ScrapeOrchestrator
from app.services.reviews.collector import ReviewCollectorService

logger = logging.getLogger("scraper.messaging.consumer")


class ScraperMessageConsumer:
    """Worker service that registers and dispatches RabbitMQ command messages."""

    def __init__(
        self,
        broker: IMessageBroker,
        orchestrator: ScrapeOrchestrator | None = None,
        price_monitor: PriceMonitorService | None = None,
        review_collector: ReviewCollectorService | None = None,
        inbox: RedisInboxDeduplicator | None = None,
    ) -> None:
        self.broker = broker
        self.orchestrator = orchestrator or ScrapeOrchestrator()
        self.price_monitor = price_monitor or PriceMonitorService()
        self.review_collector = review_collector or ReviewCollectorService(broker=self.broker)
        self.inbox = inbox

    async def _claim(self, event_id: str, event_type: str) -> bool:
        """Claim an incoming command; True when it is safe to execute."""
        if self.inbox is None:
            return True

        claimed = await self.inbox.claim_message(event_id, event_type)
        if not claimed:
            logger.warning(
                "Command [%s, event_type=%s] is already being processed or completed. "
                "Skipping duplicate and acknowledging message.",
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

    async def start_listening(self) -> None:
        """Subscribe message handlers to designated RabbitMQ queues."""
        logger.info("Registering RabbitMQ consumer queue bindings...")

        # 1. Full catalog scraping queue (Heavy job -> prefetch 1)
        await self.broker.subscribe(
            queue_name="scraper.catalog.jobs",
            routing_key=EventType.CATALOG_SCRAPE_COMMAND,
            handler=self.handle_catalog_scrape_command,
            prefetch_count=1,
        )

        # 2. Fast price monitor queue (I/O bound -> prefetch 5)
        await self.broker.subscribe(
            queue_name="scraper.price.jobs",
            routing_key=EventType.PRICES_CHECK_COMMAND,
            handler=self.handle_check_prices_command,
            prefetch_count=5,
        )

        # 3. Community reviews queue (Phase 2)
        await self.broker.subscribe(
            queue_name="scraper.reviews.jobs",
            routing_key=EventType.REVIEWS_SCRAPE_COMMAND,
            handler=self.handle_reviews_scrape_command,
            prefetch_count=1,
        )

        logger.info("RabbitMQ consumers are actively listening for commands.")

    async def handle_catalog_scrape_command(self, raw_data: dict[str, Any]) -> None:
        """Process a catalog scraping command from catalog-service."""
        command = ScrapeCatalogCommand.model_validate(raw_data)
        payload = command.payload
        logger.info(
            "Received ScrapeCatalogCommand [batch_id=%s, correlation=%s] for targets=%s",
            payload.batch_id,
            command.correlation_id,
            payload.targets,
        )

        scrape_request = ScrapeRequest(
            batch_id=payload.batch_id,
            target_type="store",
            targets=payload.targets,
            level=payload.level,
            until_model=None if payload.force_full_crawl else payload.until_models,
            upload_to_bucket=payload.upload_to_bucket,
            send_email=payload.send_email,
        )

        if not await self._claim(command.event_id, command.event_type):
            return

        start_time = time.time()
        try:
            # Run blocking crawler pipeline in background thread pool to keep asyncio event loop responsive
            response: ScrapeResponse = await asyncio.to_thread(self.orchestrator.execute, scrape_request)
            duration = round(time.time() - start_time, 2)

            # Discover latest pointers per store from scrape results
            pointers: dict[str, list[str]] = {}
            for target_res in response.results:
                if target_res.store_result:
                    if target_res.store_result.latest_pointers:
                        pointers[target_res.target_key] = target_res.store_result.latest_pointers
                    elif target_res.store_result.products:
                        sample_models = [
                            getattr(p, "title", None) or getattr(p, "model", None)
                            for p in target_res.store_result.products[:5]
                            if getattr(p, "title", None) or getattr(p, "model", None)
                        ]
                        if sample_models:
                            pointers[target_res.target_key] = [str(m) for m in sample_models]

            s3_key = response.unified_storage_key or f"catalogs/catalog_{payload.batch_id}.json"
            s3_bucket = response.unified_storage_bucket or getattr(
                self.orchestrator.storage_service, "bucket_name", "laptop-recommender-raw-catalog"
            )

            ready_event = CatalogReadyEvent(
                correlation_id=command.correlation_id,
                payload=CatalogReadyPayload(
                    batch_id=payload.batch_id,
                    s3_bucket=s3_bucket,
                    s3_key=s3_key,
                    total_laptops=response.total_items_scraped,
                    pointers_found=pointers,
                    duration_seconds=duration,
                ),
            )

            await self.broker.publish(
                routing_key=EventType.CATALOG_READY_EVENT,
                message=ready_event,
            )
            logger.info(
                "Published CatalogReadyEvent for batch [%s]: %d laptops at s3://%s/%s (took %ss)",
                payload.batch_id,
                response.total_items_scraped,
                s3_bucket,
                s3_key,
                duration,
            )
            await self._complete(command.event_id)

        except Exception as exc:
            logger.error(
                "Catalog scraping failed for batch [%s]: %s. Emitting CatalogScrapeFailedEvent.",
                payload.batch_id,
                exc,
                exc_info=True,
            )
            failed_event = CatalogScrapeFailedEvent(
                correlation_id=command.correlation_id,
                payload=CatalogScrapeFailedPayload(
                    batch_id=payload.batch_id,
                    error_message=str(exc),
                ),
            )
            try:
                await self.broker.publish(
                    routing_key=EventType.CATALOG_SCRAPE_FAILED_EVENT,
                    message=failed_event,
                )
            except Exception as pub_exc:
                logger.error("Failed to publish CatalogScrapeFailedEvent: %s", pub_exc)
            await self._release(command.event_id)
            # Re-raise so the broker wrapper rejects the original message to DLQ
            raise

    async def handle_check_prices_command(self, raw_data: dict[str, Any]) -> None:
        """Process a price verification command from catalog-service."""
        command = CheckPricesCommand.model_validate(raw_data)
        payload = command.payload
        logger.info(
            "Received CheckPricesCommand [batch_id=%s, store=%s, count=%d]",
            payload.batch_id,
            payload.store_key,
            len(payload.items),
        )

        batch_request = PriceCheckBatchRequest(
            batch_id=payload.batch_id,
            store_key=payload.store_key,
            store_name=payload.store_name,
            items=payload.items,
        )

        if not await self._claim(command.event_id, command.event_type):
            return

        try:
            batch_response = await self.price_monitor.check_batch_async(batch_request)

            result_event = PricesCheckedEvent(
                correlation_id=command.correlation_id,
                payload=PricesCheckedPayload(
                    batch_id=batch_response.batch_id,
                    store_key=batch_response.store_key,
                    total_items=batch_response.total_items,
                    changed_items_count=batch_response.changed_items_count,
                    price_drops_count=batch_response.price_drops_count,
                    price_hikes_count=batch_response.price_hikes_count,
                    out_of_stock_count=batch_response.out_of_stock_count,
                    errors_count=batch_response.errors_count,
                    duration_seconds=batch_response.duration_seconds,
                    results=batch_response.results,
                ),
            )

            await self.broker.publish(
                routing_key=EventType.PRICES_CHECKED_EVENT,
                message=result_event,
            )
            await self._complete(command.event_id)
        except Exception:
            await self._release(command.event_id)
            raise

        logger.info(
            "Published PricesCheckedEvent for store '%s' (batch=%s): %d checked, %d changed in %.2fs",
            payload.store_key,
            payload.batch_id,
            batch_response.total_items,
            batch_response.changed_items_count,
            batch_response.duration_seconds,
        )

    async def handle_reviews_scrape_command(self, raw_data: dict[str, Any]) -> None:
        """Process a community reviews scraping command (Phase 2).

        Delegates to ``ReviewCollectorService``, which runs the YouTube and
        communities collectors, uploads the raw reviews artifact, and publishes
        the ``reviews.ready.event`` carrying the object storage key.
        """
        command = ScrapeReviewsCommand.model_validate(raw_data)
        payload = command.payload
        logger.info(
            "Received ScrapeReviewsCommand [job_id=%s, chassis=%d]",
            payload.job_id,
            len(payload.targets),
        )

        if not await self._claim(command.event_id, command.event_type):
            return

        try:
            s3_key = await self.review_collector.process_reviews_batch(command)
            await self._complete(command.event_id)
        except Exception:
            await self._release(command.event_id)
            raise

        logger.info("Reviews batch completed [job_id=%s, s3_key=%s]", payload.job_id, s3_key)
