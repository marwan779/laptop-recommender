import asyncio
import logging
from typing import Any
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.events import CheckPricesCommand, CheckPricesPayload, EventType
from app.schemas.price_sync import (
    PriceCheckBatchRequest,
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

    async def dispatch_batches_via_outbox(
        self,
        session: AsyncSession,
        batches: list[PriceCheckBatchRequest],
    ) -> list[str]:
        """Dispatch price verification batches asynchronously via Transactional Outbox."""
        outbox_repo = OutboxRepository(session)
        message_ids: list[str] = []

        for batch in batches:
            cmd = CheckPricesCommand(
                correlation_id=batch.batch_id,
                payload=CheckPricesPayload(
                    batch_id=batch.batch_id,
                    store_key=batch.store_key,
                    store_name=batch.store_name,
                    items=batch.items,
                ),
            )
            msg = await outbox_repo.insert_outbox_event(
                event_type=EventType.PRICES_CHECK_COMMAND,
                routing_key=EventType.PRICES_CHECK_COMMAND,
                payload=cmd,
                correlation_id=batch.batch_id,
                message_id=uuid.UUID(batch.batch_id),
            )
            message_ids.append(str(msg.id))

        await session.flush()
        logger.info(
            "Dispatched %d price check batches to transactional outbox table.",
            len(message_ids),
        )
        return message_ids

    async def dispatch_once(
        self,
        store_key: str | None = None,
        limit: int | None = None,
        session: AsyncSession | None = None,
    ) -> list[str]:
        """Generate batches and dispatch them asynchronously via the Transactional Outbox."""
        if limit is not None and limit <= 0:
            batch_limit = None
        elif limit is not None:
            batch_limit = limit
        else:
            batch_limit = settings.price_sync_batch_limit

        async def _dispatch(sess: AsyncSession) -> list[str]:
            batches = await self.service.build_price_check_batches(
                session=sess,
                store_key=store_key,
                limit=batch_limit,
            )
            if not batches:
                logger.info("No stale offers requiring price synchronization at this time.")
                return []
            msg_ids = await self.dispatch_batches_via_outbox(session=sess, batches=batches)
            await sess.commit()
            return msg_ids

        if session is not None:
            return await _dispatch(session)
        else:
            async with AsyncSessionLocal() as sess:
                return await _dispatch(sess)

    async def run_once(
        self,
        store_key: str | None = None,
        limit: int | None = None,
        session: AsyncSession | None = None,
        http_client: Any | None = None,
    ) -> list[PriceSyncSummary]:
        """Execute a single price monitoring cycle across stale store offers."""
        if limit is not None and limit <= 0:
            batch_limit = None
        elif limit is not None:
            batch_limit = limit
        else:
            batch_limit = settings.price_sync_batch_limit

        logger.info(
            "Executing price sync cron cycle: store_key=%s, batch_limit=%s",
            store_key,
            batch_limit if batch_limit is not None else "UNLIMITED",
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
                    timeout_val = max(180.0, len(batch.items) * 3.0)
                    if http_client:
                        resp = await http_client.post(endpoint, json=payload)
                    else:
                        async with httpx.AsyncClient(timeout=timeout_val) as client:
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

    async def _trigger_cycle(self, mode: str) -> None:
        """Execute a single scheduler loop cycle using configured transport mode."""
        try:
            if mode in ("rabbitmq", "outbox"):
                await self.dispatch_once()
            else:
                await self.run_once()
        except Exception as exc:
            logger.error("Error occurred in price sync cron cycle: %s", exc, exc_info=True)

    async def _scheduler_loop(self) -> None:
        """Periodic background execution loop."""
        interval_seconds = max(60, settings.price_sync_cron_interval_hours * 3600)
        mode = getattr(settings, "price_sync_cron_mode", "rabbitmq").lower()
        run_on_startup = getattr(settings, "price_sync_run_on_startup", False)

        logger.info(
            "Starting price sync cron scheduler loop (mode: %s, interval: %d hours / %d seconds)",
            mode,
            settings.price_sync_cron_interval_hours,
            interval_seconds,
        )

        self._is_running = True
        try:
            if run_on_startup:
                # Grace period allowing messaging broker and pools to settle
                await asyncio.sleep(5)
                logger.info("Executing startup price sync cron pass...")
                await self._trigger_cycle(mode)

            while self._is_running:
                await asyncio.sleep(interval_seconds)
                await self._trigger_cycle(mode)
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
