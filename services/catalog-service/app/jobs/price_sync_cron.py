import asyncio
import logging
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.price_sync import (
    PriceCheckBatchResponse,
    PriceSyncSummary,
)
from app.services.price_sync_service import PriceSyncService

logger = logging.getLogger("catalog.jobs.price_sync_cron")


class PriceSyncCronJob:
    """Manages scheduled periodic price and stock monitoring runs.

    Queries stale store offers from PostgreSQL, dispatches batches to scraper-service,
    and ingests detected price changes, discount watermarks, and metric updates.
    """

    def __init__(
        self,
        price_sync_service: PriceSyncService | None = None,
        scraper_url: str | None = None,
    ) -> None:
        self.service = price_sync_service or PriceSyncService()
        self.scraper_url = (scraper_url or settings.scraper_service_url).rstrip("/")
        self._task: asyncio.Task | None = None
        self._is_running: bool = False

    async def run_once(
        self,
        store_key: str | None = None,
        limit: int | None = None,
        session: AsyncSession | None = None,
        http_client: Any | None = None,
    ) -> list[PriceSyncSummary]:
        """Execute a single price monitoring cycle across stale store offers."""
        batch_limit = limit or settings.price_sync_batch_limit
        logger.info(
            "Executing price sync cron cycle: store_key=%s, batch_limit=%d",
            store_key,
            batch_limit,
        )

        async def _execute_with_session(sess: AsyncSession) -> list[PriceSyncSummary]:
            batches = await self.service.build_price_check_batches(
                session=sess,
                store_key=store_key,
                limit=batch_limit,
            )
            if not batches:
                logger.info("No stale offers requiring price synchronization at this time.")
                return []

            logger.info("Generated %d store-partitioned price check batches.", len(batches))
            summaries: list[PriceSyncSummary] = []
            endpoint = f"{self.scraper_url}/api/v1/price-monitor/check"

            for batch in batches:
                try:
                    payload = batch.model_dump(mode="json")
                    if http_client:
                        resp = await http_client.post(endpoint, json=payload, timeout=30.0)
                    else:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.post(endpoint, json=payload)

                    if resp.status_code == 200:
                        batch_resp = PriceCheckBatchResponse(**resp.json())
                        summary = await self.service.apply_batch_results(
                            session=sess,
                            batch_response=batch_resp,
                        )
                        summaries.append(summary)
                        logger.info(
                            "Batch [%s] synced: %d offers updated, %d drops, %d hikes, %d OOS",
                            batch.batch_id,
                            summary.offers_updated,
                            summary.price_drops_detected,
                            summary.price_hikes_detected,
                            summary.out_of_stock_detected,
                        )
                    else:
                        logger.warning(
                            "Scraper-service price monitor returned HTTP %d for batch [%s]: %s",
                            resp.status_code,
                            batch.batch_id,
                            resp.text,
                        )
                except Exception as exc:
                    logger.error(
                        "Failed to process price check batch [%s]: %s",
                        batch.batch_id,
                        exc,
                        exc_info=True,
                    )

            return summaries

        if session is not None:
            return await _execute_with_session(session)
        else:
            async with AsyncSessionLocal() as sess:
                return await _execute_with_session(sess)

    async def _scheduler_loop(self) -> None:
        """Periodic background execution loop."""
        interval_seconds = max(60, settings.price_sync_cron_interval_hours * 3600)
        logger.info(
            "Starting price sync cron scheduler loop (interval: %d hours / %d seconds)",
            settings.price_sync_cron_interval_hours,
            interval_seconds,
        )

        self._is_running = True
        try:
            while self._is_running:
                await asyncio.sleep(interval_seconds)
                try:
                    await self.run_once()
                except Exception as exc:
                    logger.error("Error occurred in price sync cron loop: %s", exc, exc_info=True)
        except asyncio.CancelledError:
            logger.info("Price sync cron scheduler loop received cancellation signal. Stopping.")
        finally:
            self._is_running = False

    def start(self) -> asyncio.Task | None:
        """Start the background scheduler task if enabled in configuration."""
        if not settings.enable_price_sync_cron:
            logger.info("Price sync cron job is disabled (enable_price_sync_cron=False).")
            return None

        if self._task and not self._task.done():
            logger.warning("Price sync cron task is already running.")
            return self._task

        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._scheduler_loop(), name="price-sync-cron-scheduler")
        return self._task

    async def stop(self) -> None:
        """Cancel and await the background scheduler task."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Price sync cron scheduler stopped.")


# Singleton instance
price_sync_cron = PriceSyncCronJob()
