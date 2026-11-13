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
    """Stateless one-shot orchestrator for price and stock monitoring runs.

    Queries stale store offers from PostgreSQL, stages price-check commands in
    the transactional outbox (default) or dispatches them directly over HTTP,
    and ingests detected price changes when running synchronously.
    """

    def __init__(
        self,
        price_sync_service: PriceSyncService | None = None,
        scraper_url: str | None = None,
    ) -> None:
        self.service = price_sync_service or PriceSyncService()
        self.scraper_url = (scraper_url or settings.scraper_service_url).rstrip("/")

    async def dispatch_batches_via_outbox(
        self,
        session: AsyncSession,
        batches: list[PriceCheckBatchRequest],
    ) -> list[str]:
        """Stage price verification batches in the Transactional Outbox."""
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
            "Staged %d price check batches in the transactional outbox table.",
            len(message_ids),
        )
        return message_ids

    async def dispatch_once(
        self,
        store_key: str | None = None,
        limit: int | None = None,
        session: AsyncSession | None = None,
        commit: bool = True,
        dry_run: bool = False,
    ) -> list[str]:
        """Generate batches and stage them in the Transactional Outbox.

        When a session is supplied the caller owns the transaction lifecycle.
        When this method opens its own session it commits or rolls back based
        on ``commit`` (``commit=False``/``dry_run=True`` produce a validated
        preview).
        """
        if dry_run:
            commit = False
        if limit is not None and limit <= 0:
            batch_limit = None
        elif limit is not None:
            batch_limit = limit
        else:
            batch_limit = settings.price_sync_batch_limit

        opens_session = session is None

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
            if opens_session:
                if commit:
                    await sess.commit()
                else:
                    await sess.rollback()
            return msg_ids

        if session is not None:
            return await _dispatch(session)

        async with AsyncSessionLocal() as sess:
            return await _dispatch(sess)

    async def run_once(
        self,
        store_key: str | None = None,
        limit: int | None = None,
        session: AsyncSession | None = None,
        http_client: Any | None = None,
        commit: bool = True,
        dry_run: bool = False,
    ) -> list[PriceSyncSummary]:
        """Execute a single direct HTTP price monitoring cycle across stale offers."""
        if dry_run:
            commit = False
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

        opens_session = session is None

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
                            commit=commit,
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

            if opens_session and not commit:
                await sess.rollback()

            return summaries

        if session is not None:
            return await _execute_with_session(session)

        async with AsyncSessionLocal() as sess:
            return await _execute_with_session(sess)


# Backwards-compatible module-level instance for callers/tests that import it.
price_sync_cron = PriceSyncCronJob()
