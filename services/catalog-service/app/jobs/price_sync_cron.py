import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.events import CheckPricesCommand, CheckPricesPayload, EventType
from app.schemas.price_sync import PriceCheckBatchRequest
from app.services.price_sync_service import PriceSyncService

logger = logging.getLogger("catalog.jobs.price_sync_cron")


class PriceSyncCronJob:
    """Stateless one-shot orchestrator for price and stock monitoring runs.

    Queries stale store offers from PostgreSQL and stages ``prices.check.command``
    batches in the transactional outbox for the relay to dispatch to RabbitMQ.
    """

    def __init__(
        self,
        price_sync_service: PriceSyncService | None = None,
    ) -> None:
        self.service = price_sync_service or PriceSyncService()

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


# Backwards-compatible module-level instance for callers/tests that import it.
price_sync_cron = PriceSyncCronJob()
