from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.laptop import LaptopConfiguration
from app.repositories.base import BaseRepository


class LaptopRepository(BaseRepository[LaptopConfiguration]):
    """Repository handling queries for canonical laptop configurations."""

    def __init__(self, session: AsyncSession):
        super().__init__(LaptopConfiguration, session)

    async def get_by_identity_hash(self, identity_hash: str) -> LaptopConfiguration | None:
        stmt = (
            select(LaptopConfiguration)
            .where(LaptopConfiguration.identity_hash == identity_hash)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.category_scores),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_canonical_id(self, canonical_id: str) -> LaptopConfiguration | None:
        stmt = (
            select(LaptopConfiguration)
            .where(LaptopConfiguration.canonical_id == canonical_id)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.category_scores),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_configurations(
        self,
        min_price: float | None = None,
        max_price: float | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[LaptopConfiguration]:
        stmt = select(LaptopConfiguration).options(
            selectinload(LaptopConfiguration.offers),
            selectinload(LaptopConfiguration.category_scores),
        )

        if min_price is not None:
            stmt = stmt.where(LaptopConfiguration.min_price_egp >= min_price)
        if max_price is not None:
            stmt = stmt.where(LaptopConfiguration.min_price_egp <= max_price)

        stmt = stmt.order_by(LaptopConfiguration.min_price_egp.asc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
