"""Persistence tests for canonical laptop review source links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.laptop import LaptopConfiguration
from app.repositories.laptop_repository import LaptopRepository
from app.repositories.seeder import CatalogSeederRepository
from tests.test_catalog_seeder import _build_sample_catalog_item


@dataclass
class _ReviewSourceDTO:
    source_type: str
    platform: str
    title: str
    url: str
    author_or_channel: str | None
    channel_url: str | None
    rating: float | None
    score_or_views: int | None
    published_at: datetime | None


def _community_reviews() -> dict:
    return {
        "community_nlp_score": 82.4,
        "evidence_count": 27,
        "pros_en": ["Strong cooling"],
        "pros_ar": ["تبريد قوي"],
        "cons_en": ["Loud turbo fans"],
        "cons_ar": ["صوت مراوح مرتفع"],
    }


def _review_sources() -> list[object]:
    return [
        {
            "source_type": "youtube",
            "platform": "youtube",
            "title": "Lenovo LOQ 15IRX9 review",
            "url": "https://www.youtube.com/watch?v=abc123",
            "author_or_channel": "Laptop Channel",
            "channel_url": "https://www.youtube.com/@laptopchannel",
            "rating": None,
            "score_or_views": 150000,
            "published_at": datetime(2026, 1, 15, tzinfo=UTC),
        },
        _ReviewSourceDTO(
            source_type="community",
            platform="reddit",
            title="LOQ 15IRX9 owner impressions",
            url="https://www.reddit.com/r/laptops/comments/xyz/",
            author_or_channel="u/owner",
            channel_url=None,
            rating=None,
            score_or_views=42,
            published_at=None,
        ),
        {
            "source_type": "editorial",
            "platform": "laptopmag",
            "title": "Duplicate URL should collapse",
            "url": "  https://www.reddit.com/r/laptops/comments/xyz/  ",
            "author_or_channel": None,
            "channel_url": None,
            "rating": 4.5,
            "score_or_views": None,
            "published_at": None,
        },
    ]


async def _load_with_sources(session: AsyncSession, canonical_id: str) -> LaptopConfiguration:
    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == canonical_id)
        .options(selectinload(LaptopConfiguration.review_sources))
    )
    return (await session.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_repository_replaces_review_sources_idempotently(db_session: AsyncSession):
    cid = f"review-sources-{uuid.uuid4().hex[:8]}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(cid, mpn=f"MPN-S-{uuid.uuid4().hex[:6]}")]}
    )

    payload = _community_reviews()
    payload["review_sources"] = _review_sources()
    repo = LaptopRepository(db_session)

    first = await repo.update_review_intelligence_by_canonical_ids({cid: payload})
    second = await repo.update_review_intelligence_by_canonical_ids({cid: payload})

    assert first == 1
    assert second == 1

    laptop = await _load_with_sources(db_session, cid)
    sources = sorted(laptop.review_sources, key=lambda row: row.url)

    assert len(sources) == 2
    assert sources[0].source_type == "community"
    assert sources[0].platform == "reddit"
    assert sources[0].url == "https://www.reddit.com/r/laptops/comments/xyz/"
    assert sources[0].score_or_views == 42
    assert sources[1].source_type == "youtube"
    assert sources[1].author_or_channel == "Laptop Channel"
    assert sources[1].channel_url == "https://www.youtube.com/@laptopchannel"
    assert sources[1].score_or_views == 150000
    assert sources[1].published_at is not None

    # A follow-up run with a reduced source set replaces the previous rows.
    payload["review_sources"] = [_review_sources()[0]]
    await repo.update_review_intelligence_by_canonical_ids({cid: payload})

    refreshed = await _load_with_sources(db_session, cid)
    assert [row.url for row in refreshed.review_sources] == ["https://www.youtube.com/watch?v=abc123"]


@pytest.mark.asyncio
async def test_seeder_persists_review_sources_from_community_reviews(db_session: AsyncSession):
    cid = f"review-seeder-sources-{uuid.uuid4().hex[:8]}"
    item = _build_sample_catalog_item(cid, mpn=f"MPN-SS-{uuid.uuid4().hex[:6]}")
    community_reviews = _community_reviews()
    community_reviews["review_sources"] = _review_sources()[:2]
    item["derived_metrics"]["community_reviews"] = community_reviews

    seeder = CatalogSeederRepository(db_session)
    await seeder.upsert_catalog({"laptops": [item]})
    await seeder.upsert_catalog({"laptops": [item]})

    laptop = await _load_with_sources(db_session, cid)

    assert len(laptop.review_sources) == 2
    assert {row.url for row in laptop.review_sources} == {
        "https://www.youtube.com/watch?v=abc123",
        "https://www.reddit.com/r/laptops/comments/xyz/",
    }
