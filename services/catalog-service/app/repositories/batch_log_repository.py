from collections.abc import Sequence
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.scraping import ScrapingBatchLog
from app.repositories.base import BaseRepository


class BatchLogRepository(BaseRepository[ScrapingBatchLog]):
    """Repository handling SQL persistence for scraping batch audit logs."""

    def __init__(self, session: AsyncSession):
        super().__init__(ScrapingBatchLog, session)

    async def record_batch_log(
        self,
        batch_id: uuid.UUID,
        store_key: str,
        trigger_type: str,
        status: str,
        duration_seconds: float | None = None,
        items_scraped: int = 0,
        offers_updated: int = 0,
        error_message: str | None = None,
    ) -> ScrapingBatchLog:
        """Create and persist an audit log entry for a scraping/sync batch."""
        log = ScrapingBatchLog(
            id=batch_id,
            store_key=store_key,
            trigger_type=trigger_type,
            status=status,
            duration_seconds=duration_seconds,
            items_scraped=items_scraped,
            offers_updated=offers_updated,
            error_message=error_message,
        )
        self.session.add(log)
        return log

    async def upsert_checkpoint_completion(
        self,
        batch_id: uuid.UUID,
        *,
        store_key: str,
        trigger_type: str,
        items_scraped: int = 0,
        pointers_received: list[str] | None = None,
        duration_seconds: float | None = None,
        status: str = "CHECKPOINT_OK",
    ) -> ScrapingBatchLog:
        """Record or update a checkpoint batch completion without running DB ingestion."""
        existing = await self.get_by_id(batch_id)
        now = utcnow()
        if existing is None:
            log = ScrapingBatchLog(
                id=batch_id,
                store_key=store_key,
                trigger_type=trigger_type,
                status=status,
                completed_at=now,
                duration_seconds=duration_seconds,
                items_scraped=items_scraped,
                pointers_received=list(pointers_received or []),
            )
            self.session.add(log)
            return log

        existing.status = status
        existing.completed_at = now
        existing.duration_seconds = duration_seconds
        existing.items_scraped = items_scraped
        existing.pointers_received = list(pointers_received or [])
        return existing

    async def list_by_ids(self, batch_ids: Sequence[uuid.UUID]) -> Sequence[ScrapingBatchLog]:
        """Fetch batch logs matching the provided UUIDs."""
        ids = list(batch_ids)
        if not ids:
            return []
        stmt = select(ScrapingBatchLog).where(ScrapingBatchLog.id.in_(ids))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_recent_logs(self, limit: int = 20) -> Sequence[ScrapingBatchLog]:
        """Fetch the most recent scraping audit logs, newest first."""
        stmt = select(ScrapingBatchLog).order_by(desc(ScrapingBatchLog.started_at)).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
