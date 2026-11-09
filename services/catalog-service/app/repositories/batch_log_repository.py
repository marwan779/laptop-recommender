from collections.abc import Sequence
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def list_recent_logs(self, limit: int = 20) -> Sequence[ScrapingBatchLog]:
        """Fetch the most recent scraping audit logs, newest first."""
        stmt = select(ScrapingBatchLog).order_by(desc(ScrapingBatchLog.started_at)).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
