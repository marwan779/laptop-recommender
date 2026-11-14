"""Unit and integration tests for strongly-typed review intelligence persistence."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.recommender import rank_laptops_topsis
from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.repositories.laptop_repository import LaptopRepository, to_recommender_dict
from app.repositories.seeder import CatalogSeederRepository
from app.schemas.recommendation import RecommendationRequest
from app.services.catalog_metrics_service import CatalogMetricsService
from app.services.catalog_query_service import CatalogQueryService
from app.services.recommendation_service import RecommendationService
from app.services.review_intelligence_service import ReviewIntelligenceService
from tests.test_catalog_seeder import _build_sample_catalog_item


def _community_reviews() -> dict:
    return {
        "community_nlp_score": 82.4,
        "evidence_count": 27,
        "aspect_scores": {
            "thermals_score": 78.9,
            "acoustics_score": 74.2,
            "build_and_hinges_score": 82.7,
            "keyboard_and_trackpad_score": 80.4,
            "real_battery_and_reliability_score": 79.6,
        },
        "pros_en": ["Strong cooling", "Easy upgrades"],
        "pros_ar": ["تبريد قوي", "سهولة الترقية"],
        "cons_en": ["Loud turbo fans"],
        "cons_ar": ["صوت مراوح مرتفع"],
        "synthesized_review_en": "Ignored",
        "synthesized_review_ar": "مُهمل",
    }


def _catalog_item_with_reviews(canonical_id: str, mpn: str) -> dict:
    item = _build_sample_catalog_item(canonical_id, mpn=mpn, min_price=60000.0)
    item["derived_metrics"]["community_reviews"] = _community_reviews()
    item["derived_metrics"]["topsis_inputs"]["community_nlp_score"] = 82.4
    return item


def test_metrics_enrichment_preserves_community_reviews():
    item = _catalog_item_with_reviews(f"preserve-{uuid.uuid4().hex[:8]}", f"MPN-P-{uuid.uuid4().hex[:6]}")

    enriched, _summary = CatalogMetricsService().enrich_catalog_dict({"laptops": [item]})
    enriched_item = enriched["laptops"][0]
    derived = enriched_item["derived_metrics"]

    assert derived is enriched_item["hardware_metrics"]
    assert derived["community_reviews"] == _community_reviews()
    assert derived["topsis_inputs"]["community_nlp_score"] == 82.4


def test_to_recommender_dict_reconstructs_review_intelligence():
    laptop = LaptopConfiguration(
        id=uuid.uuid4(),
        canonical_id="review-map-laptop",
        brand="Lenovo",
        laptop_model="LOQ 15IRX9",
        title="Lenovo LOQ 15IRX9",
        reviews_evidence_count=27,
        pros_en=["Strong cooling"],
        pros_ar=["تبريد قوي"],
        cons_en=["Loud turbo fans"],
        cons_ar=["صوت مراوح مرتفع"],
    )
    laptop.metrics = LaptopMetrics(
        laptop_id=laptop.id,
        community_nlp_score=82.4,
        thermals_score=78.9,
        acoustics_score=74.2,
        build_and_hinges_score=82.7,
        keyboard_and_trackpad_score=80.4,
        real_battery_and_reliability_score=79.6,
    )

    mapped = to_recommender_dict(laptop)
    community_reviews = mapped["derived_metrics"]["community_reviews"]

    assert mapped["derived_metrics"]["topsis_inputs"]["community_nlp_score"] == 82.4
    assert community_reviews["evidence_count"] == 27
    assert community_reviews["pros_en"] == ["Strong cooling"]
    assert community_reviews["pros_ar"] == ["تبريد قوي"]
    assert community_reviews["cons_en"] == ["Loud turbo fans"]
    assert community_reviews["cons_ar"] == ["صوت مراوح مرتفع"]
    assert community_reviews["aspect_scores"] == {
        "thermals_score": 78.9,
        "acoustics_score": 74.2,
        "build_and_hinges_score": 82.7,
        "keyboard_and_trackpad_score": 80.4,
        "real_battery_and_reliability_score": 79.6,
    }


@pytest.mark.asyncio
async def test_seeder_persists_typed_review_intelligence(db_session: AsyncSession):
    cid = f"review-seed-{uuid.uuid4().hex[:8]}"
    item = _catalog_item_with_reviews(cid, f"MPN-R-{uuid.uuid4().hex[:6]}")

    await CatalogSeederRepository(db_session).upsert_catalog({"laptops": [item]})

    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == cid)
        .options(selectinload(LaptopConfiguration.metrics))
    )
    laptop = (await db_session.execute(stmt)).scalar_one()

    assert laptop.has_reviews is True
    assert laptop.reviews_checked_at is not None
    assert laptop.reviews_evidence_count == 27
    assert laptop.pros_en == ["Strong cooling", "Easy upgrades"]
    assert laptop.pros_ar == ["تبريد قوي", "سهولة الترقية"]
    assert laptop.cons_en == ["Loud turbo fans"]
    assert laptop.cons_ar == ["صوت مراوح مرتفع"]
    assert laptop.metrics is not None
    assert float(laptop.metrics.community_nlp_score) == 82.4
    assert float(laptop.metrics.thermals_score) == 78.9
    assert float(laptop.metrics.acoustics_score) == 74.2
    assert float(laptop.metrics.build_and_hinges_score) == 82.7
    assert float(laptop.metrics.keyboard_and_trackpad_score) == 80.4
    assert float(laptop.metrics.real_battery_and_reliability_score) == 79.6


@pytest.mark.asyncio
async def test_repository_updates_review_intelligence_by_canonical_id(db_session: AsyncSession):
    cid = f"review-update-{uuid.uuid4().hex[:8]}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(cid, mpn=f"MPN-U-{uuid.uuid4().hex[:6]}")]}
    )

    updated = await LaptopRepository(db_session).update_review_intelligence_by_canonical_ids(
        {cid: _community_reviews()}
    )

    assert updated == 1

    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == cid)
        .options(selectinload(LaptopConfiguration.metrics))
    )
    laptop = (await db_session.execute(stmt)).scalar_one()

    assert laptop.has_reviews is True
    assert laptop.reviews_checked_at is not None
    assert laptop.reviews_evidence_count == 27
    assert laptop.pros_en == ["Strong cooling", "Easy upgrades"]
    assert laptop.pros_ar == ["تبريد قوي", "سهولة الترقية"]
    assert laptop.metrics is not None
    assert float(laptop.metrics.community_nlp_score) == 82.4
    assert float(laptop.metrics.thermals_score) == 78.9


@pytest.mark.asyncio
async def test_query_service_returns_review_intelligence_from_orm(db_session: AsyncSession):
    cid = f"review-query-{uuid.uuid4().hex[:8]}"
    item = _catalog_item_with_reviews(cid, f"MPN-Q-{uuid.uuid4().hex[:6]}")
    await CatalogSeederRepository(db_session).upsert_catalog({"laptops": [item]})

    detail = await CatalogQueryService(session=db_session).get_laptop_detail(cid)

    assert detail.reviews_evidence_count == 27
    assert detail.pros_en == ["Strong cooling", "Easy upgrades"]
    assert detail.pros_ar == ["تبريد قوي", "سهولة الترقية"]
    assert detail.cons_en == ["Loud turbo fans"]
    assert detail.cons_ar == ["صوت مراوح مرتفع"]
    assert detail.metrics is not None
    assert detail.metrics.community_nlp_score == 82.4
    assert detail.metrics.thermals_score == 78.9
    assert detail.metrics.real_battery_and_reliability_score == 79.6


def test_dict_detail_includes_review_intelligence():
    item = _catalog_item_with_reviews(f"review-dict-{uuid.uuid4().hex[:8]}", f"MPN-D-{uuid.uuid4().hex[:6]}")

    detail = CatalogQueryService(session=None)._dict_to_full_detail(item)

    assert detail.reviews_evidence_count == 27
    assert detail.pros_en == ["Strong cooling", "Easy upgrades"]
    assert detail.pros_ar == ["تبريد قوي", "سهولة الترقية"]
    assert detail.cons_en == ["Loud turbo fans"]
    assert detail.cons_ar == ["صوت مراوح مرتفع"]
    assert detail.metrics is not None
    assert detail.metrics.community_nlp_score == 82.4
    assert detail.metrics.thermals_score == 78.9


@pytest.mark.asyncio
async def test_recommendation_service_surfaces_review_pros_and_cons(db_session: AsyncSession):
    cid = f"review-rec-{uuid.uuid4().hex[:8]}"
    item = _catalog_item_with_reviews(cid, f"MPN-REC-{uuid.uuid4().hex[:6]}")
    await CatalogSeederRepository(db_session).upsert_catalog({"laptops": [item]})

    response = await RecommendationService(session=db_session).get_recommendations(
        RecommendationRequest(
            budget_egp=60001.0,
            min_budget_egp=59999.0,
            persona="gaming",
            top_k=50,
        )
    )

    winner = next(result for result in response.results if result.canonical_id == cid)
    assert winner.pros_en == ["Strong cooling", "Easy upgrades"]
    assert winner.pros_ar == ["تبريد قوي", "سهولة الترقية"]
    assert winner.cons_en == ["Loud turbo fans"]
    assert winner.cons_ar == ["صوت مراوح مرتفع"]
    assert winner.reviews_evidence_count == 27
    assert winner.aspect_scores == {
        "thermals_score": 78.9,
        "acoustics_score": 74.2,
        "build_and_hinges_score": 82.7,
        "keyboard_and_trackpad_score": 80.4,
        "real_battery_and_reliability_score": 79.6,
    }


@pytest.mark.asyncio
async def test_ingest_reviews_dict_with_commit_false_defers_transaction(db_session: AsyncSession):
    cid = f"review-defer-{uuid.uuid4().hex[:8]}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(cid, mpn=f"MPN-DEF-{uuid.uuid4().hex[:6]}")]}
    )

    class _FakeChroma:
        def upsert_chassis_reviews(self, laptops):
            return len(laptops)

    service = ReviewIntelligenceService(chroma_service=_FakeChroma())
    payload = {
        "laptops": [
            {
                "primary_canonical_id": cid,
                "matched_canonical_ids": [cid],
                "nlp_review_profile": _community_reviews(),
            }
        ]
    }

    result = await service.ingest_reviews_dict(db_session, payload, commit=False)
    assert result.status == "SUCCESS"
    assert result.sql_laptops_updated == 1

    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == cid)
        .options(selectinload(LaptopConfiguration.metrics))
    )
    laptop = (await db_session.execute(stmt)).scalar_one()
    assert laptop.has_reviews is True
    assert laptop.reviews_checked_at is not None
    assert laptop.reviews_evidence_count == 27
    assert laptop.pros_en == ["Strong cooling", "Easy upgrades"]
    assert laptop.cons_en == ["Loud turbo fans"]
    assert laptop.metrics is not None
    assert float(laptop.metrics.community_nlp_score) == 82.4
    assert float(laptop.metrics.thermals_score) == 78.9

    # The caller owns the transaction: rolling back must discard the uncommitted
    # review intelligence instead of leaving it persisted behind our back.
    await db_session.rollback()

    remaining = (
        await db_session.execute(
            select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid)
        )
    ).scalar_one_or_none()
    assert remaining is None


def test_topsis_result_carries_review_pros_and_cons():
    item = _catalog_item_with_reviews(f"review-topsis-{uuid.uuid4().hex[:8]}", f"MPN-T-{uuid.uuid4().hex[:6]}")

    result = rank_laptops_topsis(
        laptops=[item],
        max_budget_egp=70000.0,
        persona="gaming",
        top_k=1,
    )

    assert len(result.results) == 1
    winner = result.results[0]
    assert winner.pros_en == ["Strong cooling", "Easy upgrades"]
    assert winner.pros_ar == ["تبريد قوي", "سهولة الترقية"]
    assert winner.cons_en == ["Loud turbo fans"]
    assert winner.cons_ar == ["صوت مراوح مرتفع"]
    assert winner.reviews_evidence_count == 27
    assert winner.aspect_scores["thermals_score"] == 78.9
    assert winner.aspect_scores["real_battery_and_reliability_score"] == 79.6
