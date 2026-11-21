"""Reset ghost-reviewed laptops that have 0 rows in laptop_review_source.

Sets has_reviews=False, reviews_evidence_count=0, community_nlp_score=56.0,
and neutral 75.0 aspect scores while preserving pros_en/pros_ar/cons_en/cons_ar.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.domain.pricing import DEFAULT_COMMUNITY_NLP_SCORE
from app.models.laptop import LaptopConfiguration


async def main() -> None:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(LaptopConfiguration)
            .options(
                selectinload(LaptopConfiguration.metrics),
                selectinload(LaptopConfiguration.review_sources),
            )
            .where(
                (LaptopConfiguration.has_reviews.is_(True))
                | (LaptopConfiguration.reviews_evidence_count > 0)
            )
        )
        laptops = (await session.execute(stmt)).scalars().unique().all()

        cleaned = 0
        for lap in laptops:
            if lap.review_sources:
                continue
            lap.has_reviews = False
            lap.reviews_evidence_count = 0
            if lap.metrics:
                lap.metrics.community_nlp_score = DEFAULT_COMMUNITY_NLP_SCORE
                lap.metrics.thermals_score = 75.0
                lap.metrics.acoustics_score = 75.0
                lap.metrics.build_and_hinges_score = 75.0
                lap.metrics.keyboard_and_trackpad_score = 75.0
                lap.metrics.real_battery_and_reliability_score = 75.0
            cleaned += 1

        await session.commit()
        print(f"Cleaned {cleaned} ghost-reviewed laptop(s) (pros/cons preserved).")


if __name__ == "__main__":
    asyncio.run(main())
