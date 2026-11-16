"""Offer Price History Repository.

Encapsulates all SQL persistence for the append-only ``offer_price_history``
event log used to plot multi-store price curves over time.
"""

from collections.abc import Sequence
from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.laptop import LaptopConfiguration
from app.models.offer import LaptopOffer, OfferPriceHistory
from app.repositories.base import BaseRepository


class PriceHistoryRepository(BaseRepository[OfferPriceHistory]):
    """Repository handling chronological price observations per store offer."""

    def __init__(self, session: AsyncSession):
        super().__init__(OfferPriceHistory, session)

    async def get_by_laptop_id(self, laptop_id: uuid.UUID) -> Sequence[OfferPriceHistory]:
        """Fetch every price event for a canonical laptop, oldest first.

        Uses the ``(laptop_configuration_id, recorded_at)`` composite index so all
        store curves are served by a single index range scan.
        """
        stmt = (
            select(OfferPriceHistory)
            .where(OfferPriceHistory.laptop_configuration_id == laptop_id)
            .order_by(OfferPriceHistory.recorded_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_offer_id(self, offer_id: uuid.UUID) -> Sequence[OfferPriceHistory]:
        """Fetch chronological price events for a single store offer."""
        stmt = (
            select(OfferPriceHistory)
            .where(OfferPriceHistory.offer_id == offer_id)
            .order_by(OfferPriceHistory.recorded_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def record_point(
        self,
        offer_id: uuid.UUID,
        laptop_configuration_id: uuid.UUID,
        store_key: str,
        price_egp: float,
        in_stock: bool,
        recorded_at: datetime,
    ) -> OfferPriceHistory:
        """Stage a new price/stock observation and flush it immediately."""
        entry = self.stage_point(
            offer_id=offer_id,
            laptop_configuration_id=laptop_configuration_id,
            store_key=store_key,
            price_egp=price_egp,
            in_stock=in_stock,
            recorded_at=recorded_at,
        )
        await self.session.flush()
        return entry

    def stage_point(
        self,
        offer_id: uuid.UUID,
        laptop_configuration_id: uuid.UUID,
        store_key: str,
        price_egp: float,
        in_stock: bool,
        recorded_at: datetime,
    ) -> OfferPriceHistory:
        """Stage a price observation without flushing (bulk seeding path)."""
        entry = OfferPriceHistory(
            id=uuid.uuid4(),
            offer_id=offer_id,
            laptop_configuration_id=laptop_configuration_id,
            store_key=store_key,
            price_egp=price_egp,
            in_stock=in_stock,
            recorded_at=recorded_at,
        )
        self.session.add(entry)
        return entry

    async def list_changes_since(
        self,
        since: datetime,
        store_key: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        """Fetch recorded price/stock transitions since ``since`` joined with offer and laptop context."""
        stmt = (
            select(OfferPriceHistory, LaptopOffer, LaptopConfiguration.title, LaptopConfiguration.canonical_id)
            .join(LaptopOffer, LaptopOffer.id == OfferPriceHistory.offer_id)
            .join(LaptopConfiguration, LaptopConfiguration.id == OfferPriceHistory.laptop_configuration_id)
            .where(OfferPriceHistory.recorded_at >= since)
            .order_by(OfferPriceHistory.recorded_at.desc())
            .limit(limit)
        )
        if store_key:
            stmt = stmt.where(OfferPriceHistory.store_key == store_key.lower().strip())

        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "store_key": history.store_key,
                "canonical_id": canonical_id,
                "title": title,
                "product_url": offer.product_url,
                "previous_price_egp": float(offer.previous_price_egp) if offer.previous_price_egp is not None else None,
                "price_egp": float(history.price_egp),
                "in_stock": bool(history.in_stock),
                "recorded_at": history.recorded_at,
            }
            for history, offer, title, canonical_id in rows
        ]


__all__ = ["PriceHistoryRepository"]
