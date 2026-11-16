"""Unit and integration tests for strongly-typed review intelligence persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
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

    service = ReviewIntelligenceService()
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
        await db_session.execute(select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid))
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


@pytest.mark.asyncio
async def test_ingest_reviews_dict_supports_format_b2_chassis_reviews(db_session: AsyncSession):
    cid = f"review-b2-{uuid.uuid4().hex[:8]}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(cid, mpn=f"MPN-B2-{uuid.uuid4().hex[:6]}")]}
    )

    service = ReviewIntelligenceService()
    payload = {
        "chassis_reviews": [
            {
                "chassis_key": "asus:vivobook:15",
                "primary_canonical_id": cid,
                "matched_canonical_ids": [cid],
                "community_nlp_score": 84.5,
                "aspect_scores": {
                    "thermals_score": 81.0,
                    "acoustics_score": 83.0,
                    "build_and_hinges_score": 80.0,
                    "keyboard_and_trackpad_score": 85.0,
                    "real_battery_and_reliability_score": 86.0,
                },
                "clean_profile_lists": {
                    "pros_en": ["Quiet fans", "Crisp keyboard"],
                    "pros_ar": ["مراوح هادئة", "لوحة مفاتيح مريحة"],
                    "cons_en": ["Plastic lid"],
                    "cons_ar": ["غطاء بلاستيكي"],
                },
                "deduplicated_chunks": [
                    {"text": "Great thermals"},
                    {"text": "Solid keyboard feel"},
                    {"text": "Mild flex on plastic lid"},
                ],
            }
        ]
    }

    result = await service.ingest_reviews_dict(db_session, payload, commit=True)
    assert result.status == "SUCCESS"
    assert result.chassis_processed == 1
    assert result.chroma_documents_upserted == 0
    assert result.sql_laptops_updated == 1

    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == cid)
        .options(selectinload(LaptopConfiguration.metrics))
    )
    laptop = (await db_session.execute(stmt)).scalar_one()
    assert laptop.has_reviews is True
    assert laptop.reviews_evidence_count == 3
    assert laptop.pros_en == ["Quiet fans", "Crisp keyboard"]
    assert laptop.cons_ar == ["غطاء بلاستيكي"]
    assert laptop.metrics is not None
    assert float(laptop.metrics.community_nlp_score) == 84.5
    assert float(laptop.metrics.acoustics_score) == 83.0


def test_collect_review_profiles_uses_canonical_id_fallback():
    profiles = ReviewIntelligenceService._collect_review_profiles(
        [
            {
                "canonical_id": "laptop-fallback-id",
                "community_nlp_score": 80.0,
                "aspect_scores": {"thermals_score": 79.0},
                "clean_profile_lists": {"pros_en": ["Cool"], "pros_ar": ["بارد"]},
            }
        ]
    )
    assert "laptop-fallback-id" in profiles
    assert profiles["laptop-fallback-id"]["pros_en"] == ["Cool"]
    assert profiles["laptop-fallback-id"]["community_nlp_score"] == 80.0


@pytest.mark.asyncio
async def test_update_review_intelligence_creates_metrics_when_missing(db_session: AsyncSession):
    from sqlalchemy import delete

    cid = f"review-no-metrics-{uuid.uuid4().hex[:8]}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(cid, mpn=f"MPN-NOM-{uuid.uuid4().hex[:6]}")]}
    )
    stmt = select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid)
    laptop = (await db_session.execute(stmt)).scalar_one()
    await db_session.execute(delete(LaptopMetrics).where(LaptopMetrics.laptop_id == laptop.id))
    db_session.expire_all()

    updated = await LaptopRepository(db_session).update_review_intelligence_by_canonical_ids(
        {cid: _community_reviews()}
    )
    assert updated == 1

    db_session.expire_all()
    refreshed = (
        await db_session.execute(
            select(LaptopConfiguration)
            .where(LaptopConfiguration.canonical_id == cid)
            .options(selectinload(LaptopConfiguration.metrics))
        )
    ).scalar_one()
    assert refreshed.metrics is not None
    assert float(refreshed.metrics.community_nlp_score) == 82.4
    assert float(refreshed.metrics.thermals_score) == 78.9
    assert float(refreshed.metrics.real_battery_and_reliability_score) == 79.6


def test_collect_review_profiles_extracts_review_sources_from_v6_and_b2():
    profiles = ReviewIntelligenceService._collect_review_profiles(
        [
            {
                "primary_canonical_id": "cid-v6",
                "youtube": {
                    "videos": [
                        {
                            "title": "V6 YouTube Review",
                            "channel_name": "Dave2D",
                            "channel_url": "https://www.youtube.com/@Dave2D",
                            "video_url": "https://www.youtube.com/watch?v=d2d1",
                            "view_count": 90000,
                        }
                    ]
                },
                "communities": {
                    "discussions": [
                        {
                            "platform": "reddit",
                            "author": "user1",
                            "post_title": "Owner Impressions",
                            "post_url": "https://www.reddit.com/r/GamingLaptops/comments/abc",
                            "score": 32,
                        }
                    ]
                },
                "nlp_review_profile": {
                    "community_nlp_score": 84.0,
                    "pros_en": ["Fast screen"],
                    "pros_ar": ["شاشة سريعة"],
                },
            },
            {
                "canonical_id": "cid-b2",
                "community_nlp_score": 80.5,
                "clean_profile_lists": {"pros_en": ["Quiet fans"], "pros_ar": ["مراوح هادئة"]},
                "review_sources": [
                    {
                        "source_type": "editorial",
                        "platform": "notebookcheck",
                        "title": "Notebookcheck Review",
                        "url": "https://www.notebookcheck.net/nb1.html",
                        "rating": 87.0,
                    }
                ],
            },
        ]
    )

    assert len(profiles["cid-v6"]["review_sources"]) == 2
    assert [s["source_type"] for s in profiles["cid-v6"]["review_sources"]] == ["youtube", "community"]
    assert profiles["cid-v6"]["review_sources"][0]["url"] == "https://www.youtube.com/watch?v=d2d1"
    assert len(profiles["cid-b2"]["review_sources"]) == 1
    assert profiles["cid-b2"]["review_sources"][0]["platform"] == "notebookcheck"


def test_query_service_detail_exposes_review_sources_from_dict_and_orm_mocks():
    from types import SimpleNamespace

    item = _catalog_item_with_reviews("review-dict-src", "MPN-SRC-1")
    item["derived_metrics"]["community_reviews"]["review_sources"] = [
        {
            "source_type": "youtube",
            "platform": "youtube",
            "title": "Review Video",
            "url": "https://www.youtube.com/watch?v=dict1",
            "author_or_channel": "Reviewer",
            "score_or_views": 4000,
        }
    ]
    dict_detail = CatalogQueryService(session=None)._dict_to_full_detail(item)
    assert len(dict_detail.review_sources) == 1
    assert dict_detail.review_sources[0].url == "https://www.youtube.com/watch?v=dict1"

    mock_orm = SimpleNamespace(
        review_sources=[
            SimpleNamespace(
                source_type="community",
                platform="reddit",
                title="Reddit Thread",
                url="https://www.reddit.com/r/laptops/comments/r1",
                author_or_channel="op",
                channel_url=None,
                rating=None,
                score_or_views=12,
                published_at=None,
            )
        ]
    )
    serialized = CatalogQueryService._serialize_orm_review_sources(mock_orm)
    assert len(serialized) == 1
    assert serialized[0].platform == "reddit"
    assert serialized[0].url == "https://www.reddit.com/r/laptops/comments/r1"


@pytest.mark.asyncio
async def test_ingest_from_file_persists_review_sources_and_exposes_detail_idempotently(
    db_session: AsyncSession,
    tmp_path: Path,
):
    cid = f"review-e2e-src-{uuid.uuid4().hex[:8]}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(cid, mpn=f"MPN-E2E-{uuid.uuid4().hex[:6]}")]}
    )

    reviews_file = tmp_path / "enriched_reviews.json"
    reviews_file.write_text(
        json.dumps(
            {
                "laptops": [
                    {
                        "primary_canonical_id": cid,
                        "matched_canonical_ids": [cid],
                        "youtube": {
                            "videos": [
                                {
                                    "title": "E2E Video Review",
                                    "channel_name": "Hardware Lab",
                                    "channel_url": "https://www.youtube.com/@HardwareLab",
                                    "video_url": "https://www.youtube.com/watch?v=e2evid1",
                                    "view_count": 75000,
                                }
                            ]
                        },
                        "communities": {
                            "discussions": [
                                {
                                    "platform": "level1techs",
                                    "author": "dev",
                                    "post_title": "Thermal paste impressions",
                                    "post_url": "https://forum.level1techs.com/t/e2e/999",
                                    "score": 11,
                                }
                            ]
                        },
                        "nlp_review_profile": {
                            "community_nlp_score": 85.0,
                            "evidence_count": 12,
                            "aspect_scores": {"thermals_score": 84.0},
                            "pros_en": ["Great sustained cooling"],
                            "pros_ar": ["تبريد مستقر ممتاز"],
                            "cons_en": ["Loud fans under load"],
                            "cons_ar": ["مراوح مسموعة تحت الضغط"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    svc = ReviewIntelligenceService()
    first = await svc.ingest_from_file(db_session, source_path=reviews_file, commit=False)
    second = await svc.ingest_from_file(db_session, source_path=reviews_file, commit=False)

    assert first.status == "SUCCESS"
    assert first.sql_laptops_updated == 1
    assert second.sql_laptops_updated == 1

    detail = await CatalogQueryService(session=db_session).get_laptop_detail(cid)
    assert [s.url for s in detail.review_sources] == [
        "https://www.youtube.com/watch?v=e2evid1",
        "https://forum.level1techs.com/t/e2e/999",
    ]
    assert detail.review_sources[0].author_or_channel == "Hardware Lab"
    assert detail.review_sources[0].score_or_views == 75000
    assert detail.review_sources[1].platform == "level1techs"


@pytest.mark.asyncio
async def test_seeder_sets_chassis_key_and_pre_dispatch_clones_reviewed_siblings(
    db_session: AsyncSession,
):
    from app.models.outbox import OutboxMessage
    from app.repositories.review_source_persistence import build_review_sources

    unique = uuid.uuid4().hex[:6].upper()
    shared_model = f"LOQ 15CLN{unique[:2]}"
    donor_cid = f"donor-twin-{unique.lower()}"
    twin_cid = f"new-twin-{unique.lower()}"
    brand_new_cid = f"brand-new-{unique.lower()}"

    await CatalogSeederRepository(db_session).upsert_catalog(
        {
            "laptops": [
                _build_sample_catalog_item(donor_cid, mpn=f"83ZZ001{unique[:3]}"),
                _build_sample_catalog_item(twin_cid, mpn=f"83ZZ002{unique[:3]}"),
                _build_sample_catalog_item(brand_new_cid, mpn=f"90XX001{unique[:3]}"),
            ]
        }
    )

    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id.in_([donor_cid, twin_cid, brand_new_cid]))
        .options(selectinload(LaptopConfiguration.metrics), selectinload(LaptopConfiguration.review_sources))
    )
    by_cid = {row.canonical_id: row for row in (await db_session.execute(stmt)).scalars().unique().all()}
    assert by_cid[donor_cid].chassis_key is not None
    assert by_cid[twin_cid].chassis_key is not None

    # Force identical clonable chassis_key on donor & twin, distinct on brand_new
    shared_key = f"lenovo:loq:15T{unique}"
    by_cid[donor_cid].chassis_key = shared_key
    by_cid[twin_cid].chassis_key = shared_key
    by_cid[brand_new_cid].chassis_key = f"asus:zephyrus:G16{unique}"
    await db_session.flush()

    await LaptopRepository(db_session).update_review_intelligence_by_canonical_ids(
        {
            donor_cid: {
                **_community_reviews(),
                "review_sources": [
                    {
                        "source_type": "youtube",
                        "platform": "youtube",
                        "title": "Donor Chassis Review",
                        "url": f"https://www.youtube.com/watch?v={unique.lower()}",
                        "author_or_channel": "Jarrod",
                        "score_or_views": 50000,
                    }
                ],
            }
        }
    )
    assert len(build_review_sources(by_cid[donor_cid].id, by_cid[donor_cid].review_sources)) == 1

    response = await ReviewIntelligenceService().dispatch_review_scraping(
        session=db_session,
        force_all=False,
        commit=False,
    )

    assert response.laptops_cloned >= 1
    assert response.status == "QUEUED"

    db_session.expire_all()
    refreshed = {
        row.canonical_id: row
        for row in (
            await db_session.execute(
                select(LaptopConfiguration)
                .where(LaptopConfiguration.canonical_id.in_([twin_cid, brand_new_cid]))
                .options(selectinload(LaptopConfiguration.metrics), selectinload(LaptopConfiguration.review_sources))
            )
        )
        .scalars()
        .unique()
        .all()
    }
    twin = refreshed[twin_cid]
    assert twin.has_reviews is True
    assert twin.pros_en == ["Strong cooling", "Easy upgrades"]
    assert twin.reviews_evidence_count == 27
    assert twin.metrics is not None
    assert float(twin.metrics.thermals_score) == 78.9
    assert [s.url for s in twin.review_sources] == [f"https://www.youtube.com/watch?v={unique.lower()}"]

    outbox = (
        await db_session.execute(select(OutboxMessage).where(OutboxMessage.correlation_id == response.job_id))
    ).scalar_one()
    payload_targets = json.loads(outbox.payload_json)["payload"]["targets"]
    queued_cids = {
        cid for t in payload_targets for cid in ([t["canonical_id"]] + (t.get("matched_canonical_ids") or []))
    }
    assert brand_new_cid in queued_cids
    assert twin_cid not in queued_cids

    # Add another unreviewed twin of the same donor and stub unreviewed list -> CLONED_EXISTING with 0 outbox rows
    twin2_cid = f"only-twin-{unique.lower()}"
    await CatalogSeederRepository(db_session).upsert_catalog(
        {"laptops": [_build_sample_catalog_item(twin2_cid, mpn=f"83ZZ003{unique[:3]}")]}
    )
    twin2 = (
        await db_session.execute(
            select(LaptopConfiguration)
            .where(LaptopConfiguration.canonical_id == twin2_cid)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.metrics),
                selectinload(LaptopConfiguration.review_sources),
            )
        )
    ).scalar_one()
    twin2.chassis_key = shared_key
    await db_session.flush()

    orig_get_unreviewed = LaptopRepository.get_unreviewed_laptops

    async def _only_twin2(self):
        return [twin2]

    try:
        LaptopRepository.get_unreviewed_laptops = _only_twin2  # type: ignore[method-assign]
        cloned_only_resp = await ReviewIntelligenceService().dispatch_review_scraping(
            session=db_session,
            force_all=False,
            commit=False,
        )
    finally:
        LaptopRepository.get_unreviewed_laptops = orig_get_unreviewed  # type: ignore[method-assign]

    assert cloned_only_resp.status == "CLONED_EXISTING"
    assert cloned_only_resp.chassis_targets_queued == 0
    assert cloned_only_resp.laptops_cloned == 1
    assert twin2.has_reviews is True
    assert (
        await db_session.execute(select(OutboxMessage).where(OutboxMessage.correlation_id == cloned_only_resp.job_id))
    ).scalar_one_or_none() is None
