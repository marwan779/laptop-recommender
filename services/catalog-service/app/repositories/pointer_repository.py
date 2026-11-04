from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.scraping import StoreScrapingPointer
from app.repositories.base import BaseRepository


class StoreScrapingPointerRepository(BaseRepository[StoreScrapingPointer]):
    """Repository handling SQL persistence for store scraping watermark pointers."""

    def __init__(self, session: AsyncSession):
        super().__init__(StoreScrapingPointer, session)

    async def get_by_store_key(self, store_key: str) -> StoreScrapingPointer | None:
        """Fetch watermark pointer by unique store key."""
        stmt = select(StoreScrapingPointer).where(StoreScrapingPointer.store_key == store_key.lower().strip())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self, store_key: str | None = None) -> Sequence[StoreScrapingPointer]:
        """Fetch active scraping pointers for one or all stores."""
        stmt = select(StoreScrapingPointer).where(StoreScrapingPointer.is_active.is_(True))
        if store_key and store_key != "all":
            stmt = stmt.where(StoreScrapingPointer.store_key == store_key.lower().strip())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert_pointer(
        self,
        store_key: str,
        store_name: str,
        store_domain: str | None = None,
        total_active_offers: int = 0,
        latest_pointers: list[str] | None = None,
        last_scraped_at: datetime | None = None,
    ) -> StoreScrapingPointer:
        """Insert or update a store scraping watermark pointer."""
        key = store_key.lower().strip()
        pointer = await self.get_by_store_key(key)
        now = last_scraped_at or utcnow()

        if pointer is None:
            pointer = StoreScrapingPointer(
                store_key=key,
                store_name=store_name,
                store_domain=store_domain,
                total_active_offers=total_active_offers,
                latest_pointers=latest_pointers or [],
                last_scraped_at=now,
            )
            self.session.add(pointer)
        else:
            if store_name:
                pointer.store_name = store_name
            if store_domain:
                pointer.store_domain = store_domain
            pointer.total_active_offers = total_active_offers
            if latest_pointers is not None:
                pointer.latest_pointers = latest_pointers
            pointer.last_scraped_at = now
            pointer.updated_at = utcnow()

        await self.session.flush()
        return pointer
