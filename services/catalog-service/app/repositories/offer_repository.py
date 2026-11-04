from collections.abc import Sequence
from datetime import datetime
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.offer import LaptopOffer
from app.repositories.base import BaseRepository


class OfferRepository(BaseRepository[LaptopOffer]):
    """Repository handling SQL persistence for store laptop offers."""

    def __init__(self, session: AsyncSession):
        super().__init__(LaptopOffer, session)

    async def get_stale_offers(
        self,
        store_key: str | None = None,
        limit: int = 50,
    ) -> Sequence[LaptopOffer]:
        """Fetch oldest checked offers, optionally partitioned by store."""
        stmt = (
            select(LaptopOffer)
            .where(LaptopOffer.is_valid_price.is_(True))
            .order_by(LaptopOffer.last_checked_at.asc().nullsfirst())
        )
        if store_key:
            stmt = stmt.where(LaptopOffer.store_key == store_key.lower().strip())
        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_offers_by_laptop_id(self, laptop_id: uuid.UUID) -> Sequence[LaptopOffer]:
        """Fetch all store offers associated with a canonical laptop."""
        stmt = select(LaptopOffer).where(LaptopOffer.laptop_configuration_id == laptop_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def bulk_touch_watermarks(
        self,
        offer_ids: Sequence[uuid.UUID],
        timestamp: datetime | None = None,
    ) -> None:
        """Fast-path bulk update of last_checked_at watermark for unchanged offers."""
        if not offer_ids:
            return
        ts = timestamp or utcnow()
        stmt = update(LaptopOffer).where(LaptopOffer.id.in_(offer_ids)).values(last_checked_at=ts)
        await self.session.execute(stmt)
