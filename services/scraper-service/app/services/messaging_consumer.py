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
    ReviewsReadyEvent,
    ReviewsReadyPayload,
    ScrapeCatalogCommand,
    ScrapeReviewsCommand,
)
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse
from app.services.orchestrator import ScrapeOrchestrator

logger = logging.getLogger("scraper.messaging.consumer")


class ScraperMessageConsumer:
    """Worker service that registers and dispatches RabbitMQ command messages."""

    def __init__(
        self,
        broker: IMessageBroker,
        orchestrator: ScrapeOrchestrator | None = None,
        price_monitor: PriceMonitorService | None = None,
    ) -> None:
        self.broker = broker
        self.orchestrator = orchestrator or ScrapeOrchestrator()
        self.price_monitor = price_monitor or PriceMonitorService()

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
            prefetch_count=2,
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
            target_type="store",
            targets=payload.targets,
            level=payload.level,
            until_model=None if payload.force_full_crawl else payload.until_models,
            upload_to_bucket=payload.upload_to_bucket,
            send_email=payload.send_email,
        )

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

            s3_bucket = getattr(self.orchestrator.storage_service, "bucket_name", "laptop-recommender-raw-catalog")
            s3_key = "catalogs/unified_catalog_latest.json"

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
        logger.info(
            "Published PricesCheckedEvent for store '%s' (batch=%s): %d checked, %d changed in %.2fs",
            payload.store_key,
            payload.batch_id,
            batch_response.total_items,
            batch_response.changed_items_count,
            batch_response.duration_seconds,
        )

    async def handle_reviews_scrape_command(self, raw_data: dict[str, Any]) -> None:
        """Process a community reviews scraping command (Phase 2)."""
        command = ScrapeReviewsCommand.model_validate(raw_data)
        payload = command.payload
        logger.info(
            "Received ScrapeReviewsCommand [job_id=%s, laptops=%d]",
            payload.job_id,
            len(payload.targets),
        )

        # Phase 2 stub implementation returning clean empty results until Phase 2 scrapers are active
        reviews_event = ReviewsReadyEvent(
            correlation_id=command.correlation_id,
            payload=ReviewsReadyPayload(
                job_id=payload.job_id,
                total_laptops=len(payload.targets),
                total_snippets=0,
                results=[],
            ),
        )
        await self.broker.publish(
            routing_key=EventType.REVIEWS_READY_EVENT,
            message=reviews_event,
        )
        logger.info("Published ReviewsReadyEvent for job [%s]", payload.job_id)
