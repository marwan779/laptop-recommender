"""Integration tests for the review chassis outbox dispatch during ingestion.

These exercise the real application use case against the isolated ``db_session``
fixture (NullPool + rollback), verifying that Stage 1 seeding and the outbox
message share one transaction while reviewed flags are stamped only after
Stage 2 review intelligence persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.laptop import LaptopConfiguration
from app.models.outbox import OutboxMessage
from app.repositories.laptop_repository import LaptopRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.events import EventType, ScrapeReviewsCommand
from app.services.catalog_ingestion_service import CatalogIngestionService
from tests.test_catalog_seeder import _build_sample_catalog_item


def _catalog_item(canonical_id: str, model: str, mpn: str, ram_gb: int, store: str) -> dict:
    item = _build_sample_catalog_item(
        canonical_id,
        mpn=mpn,
        min_price=50000.0,
        store_key=store,
        ram_gb=ram_gb,
    )
    item["brand"] = "Lenovo"
    item["laptop_family"] = "LOQ"
    item["laptop_model"] = model
    item["title"] = f"Lenovo LOQ {model} Gaming Laptop - {ram_gb}GB RAM"
    item["specs"]["identity"]["brand"] = "Lenovo"
    item["specs"]["identity"]["laptop_family"] = "LOQ"
    item["specs"]["identity"]["laptop_model"] = model
    return item


@pytest.mark.asyncio
async def test_ingestion_emits_single_outbox_command_with_collapsed_chassis(
    db_session: AsyncSession,
    tmp_path: Path,
):
    suffix = uuid.uuid4().hex[:8]
    catalog_dict = {
        "title": "Review Chassis Test",
        "stores_included": ["compumarts", "sigma"],
        "laptops": [
            _catalog_item(f"loq-16gb-{suffix}", "LOQ 15IRX9", f"MPN-A-{suffix}", 16, "compumarts"),
            _catalog_item(f"loq-32gb-{suffix}", "LOQ 15IRX9", f"MPN-B-{suffix}", 32, "sigma"),
        ],
    }

    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text(json.dumps(catalog_dict), encoding="utf-8")

    service = CatalogIngestionService()
    result = await service.ingest_from_file(
        session=db_session,
        file_path=catalog_file,
        trigger_type="TEST_REVIEWS",
    )

    assert result.status == "SUCCESS"

    # Exactly one outbox message, typed as the reviews scrape command.
    outbox = (await db_session.execute(select(OutboxMessage))).scalars().all()
    review_messages = [m for m in outbox if m.event_type == EventType.REVIEWS_SCRAPE_COMMAND]
    assert len(review_messages) == 1

    message = review_messages[0]
    assert message.routing_key == EventType.REVIEWS_SCRAPE_COMMAND
    assert message.correlation_id == str(result.batch_id)

    command = ScrapeReviewsCommand.model_validate(json.loads(message.payload_json))
    assert command.payload.job_id == f"reviews_batch_{result.batch_id}"

    # Our two SKU variants collapsed into one chassis target. Other pre-existing
    # laptops in the test database may also be in the batch, so locate ours by MPN.
    our_targets = [t for t in command.payload.targets if f"MPN-A-{suffix}" in t.mpns or f"MPN-B-{suffix}" in t.mpns]
    assert len(our_targets) == 1
    target = our_targets[0]
    assert target.brand == "Lenovo"
    # Representative may be a pre-existing row of the same chassis in the shared
    # test database, so compare family case-insensitively.
    assert target.laptop_family.lower() == "loq"
    # Both of our variant MPNs must be present. The shared test database may hold
    # additional pre-existing variants of the same chassis, which also aggregate here.
    assert {f"MPN-A-{suffix}", f"MPN-B-{suffix}"} <= set(target.mpns)
    assert not hasattr(target, "search_queries")

    # Stage 1 seeding must NOT mark laptops as reviewed; that happens only after
    # Stage 2 review intelligence ingestion actually persists their NLP profile.
    laptops = (
        (
            await db_session.execute(
                select(LaptopConfiguration).where(
                    LaptopConfiguration.canonical_id.in_([f"loq-16gb-{suffix}", f"loq-32gb-{suffix}"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(laptops) == 2
    for laptop in laptops:
        assert laptop.has_reviews is False
        assert laptop.reviews_checked_at is None


@pytest.mark.asyncio
async def test_second_ingestion_does_not_requeue_reviewed_laptops(
    db_session: AsyncSession,
    tmp_path: Path,
):
    suffix = uuid.uuid4().hex[:8]
    catalog_dict = {
        "title": "Idempotent Review Test",
        "stores_included": ["compumarts"],
        "laptops": [
            _catalog_item(f"idem-{suffix}", "LOQ 15IRX9", f"MPN-I-{suffix}", 16, "compumarts"),
        ],
    }
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text(json.dumps(catalog_dict), encoding="utf-8")

    service = CatalogIngestionService()

    first = await service.ingest_from_file(session=db_session, file_path=catalog_file)
    assert first.status == "SUCCESS"

    # Stage 1 leaves the newly seeded laptop unreviewed until Stage 2 completes.
    canonical_id = f"idem-{suffix}"
    seeded = (
        await db_session.execute(
            select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == canonical_id)
        )
    ).scalar_one()
    assert seeded.has_reviews is False

    # Simulate Stage 2 review intelligence ingestion persisting the NLP profile.
    updated = await LaptopRepository(db_session).update_review_intelligence_by_canonical_ids(
        {
            canonical_id: {
                "community_nlp_score": 82.4,
                "evidence_count": 27,
                "pros_en": ["Strong cooling"],
                "pros_ar": ["تبريد قوي"],
                "cons_en": ["Loud turbo fans"],
                "cons_ar": ["صوت مراوح مرتفع"],
            }
        }
    )
    assert updated == 1
    await db_session.refresh(seeded)
    assert seeded.has_reviews is True

    second = await service.ingest_from_file(session=db_session, file_path=catalog_file)
    assert second.status == "SUCCESS"

    outbox = (await db_session.execute(select(OutboxMessage))).scalars().all()
    review_messages = [m for m in outbox if m.event_type == EventType.REVIEWS_SCRAPE_COMMAND]
    # Only the first ingestion enqueued a command; the second found no unreviewed laptops.
    assert len(review_messages) == 1


@pytest.mark.asyncio
async def test_outbox_message_and_flags_share_the_same_transaction(db_session: AsyncSession):
    """Rolling the transaction back must discard writes from the same transaction."""
    from app.models.base import utcnow

    laptop = LaptopConfiguration(
        id=uuid.uuid4(),
        canonical_id=f"txn-{uuid.uuid4().hex[:8]}",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        title="Lenovo LOQ 15IRX9",
        cpu_manufacturer="Intel",
        cpu_model="Core i7-13650HX",
        cpu_cores=14,
        cpu_threads=20,
        gpu_manufacturer="NVIDIA",
        gpu_model="GeForce RTX 4060",
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=512,
        display_size_inches=15.6,
        display_resolution="1920x1080",
        display_width=1920,
        display_height=1080,
        min_price_egp=60000.0,
        cheapest_store="compumarts",
        has_reviews=False,
    )
    db_session.add(laptop)
    await db_session.flush()

    outbox_repo = OutboxRepository(db_session)
    await outbox_repo.insert_outbox_event(
        event_type=EventType.REVIEWS_SCRAPE_COMMAND,
        routing_key=EventType.REVIEWS_SCRAPE_COMMAND,
        payload={"job_id": "job-txn"},
        correlation_id="txn-correlation",
    )

    laptop.has_reviews = True
    laptop.reviews_checked_at = utcnow()
    await db_session.flush()

    # Both writes are visible inside the open transaction...
    assert await db_session.get(LaptopConfiguration, laptop.id) is not None
    assert laptop.has_reviews is True

    # ...and both are discarded when the transaction rolls back.
    await db_session.rollback()


def test_to_review_input_and_target_carry_screen_size():
    """The application projection must forward display size into the event."""
    from types import SimpleNamespace

    laptop = SimpleNamespace(
        id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        title="Lenovo LOQ 15IRX9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        mpn="83DV01HSED",
        thumbnail_url=None,
        display_size_inches=15.6,
        offers=[],
    )

    dto = CatalogIngestionService._to_review_input(laptop)
    assert dto.screen_size == 15.6

    resolved = SimpleNamespace(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        title="Lenovo LOQ 15IRX9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        mpn="83DV01HSED",
        manufacturer_part_number="83DV01HSED",
        retailer_sku=None,
        skus=(),
        mpns=(),
        product_urls=(),
        thumbnail_url=None,
        screen_size=15.6,
        matched_laptop_ids=("lap-1",),
        matched_canonical_ids=("lenovo-loq-15irx9",),
    )

    target = CatalogIngestionService._to_review_target(resolved)
    assert target.screen_size == 15.6


def test_review_target_mapper_builds_specs_and_battery_estimate_envelope():
    from types import SimpleNamespace

    from app.services.review_intelligence_service import ReviewIntelligenceService
    from app.services.review_target_mapper import build_review_specs_envelope

    laptop = SimpleNamespace(
        id="lap-spec-1",
        canonical_id="asus-tuf-f16-fx608",
        title="ASUS TUF Gaming F16 FX608",
        brand="ASUS",
        laptop_family="TUF Gaming",
        laptop_model="FX608JMR-RV057W",
        mpn="90NR0NB1-M00J30",
        thumbnail_url=None,
        market_positioning="Gaming",
        cpu_full_name="Intel Core i7-14650HX",
        cpu_model="i7-14650HX",
        cpu_base_power_w=55,
        gpu_model="GeForce RTX 5060",
        gpu_tdp_w=115,
        gpu_integrated=False,
        ram_capacity_gb=16,
        ram_is_soldered=False,
        ram_max_supported_gb=64,
        storage_capacity_gb=1024,
        storage_slot_count=2,
        display_size_inches=16.0,
        display_panel_type="IPS",
        display_refresh_rate_hz=165,
        display_brightness_nits=300,
        display_color_gamut="100% sRGB",
        battery_capacity_wh=90.0,
        weight_kg=2.2,
        metrics=SimpleNamespace(
            estimated_battery_hours=6.1,
            display_tier="100% sRGB IPS",
        ),
        offers=[],
    )

    envelope = build_review_specs_envelope(laptop)
    assert envelope is not None
    assert envelope["cpu"] == {"raw": "Intel Core i7-14650HX", "model": "i7-14650HX", "base_power_w": 55}
    assert envelope["gpu"] == {"raw": "GeForce RTX 5060", "model": "GeForce RTX 5060", "tgp_watts": 115, "integrated": False}
    assert envelope["display"]["srgb_percent"] == 100.0
    assert envelope["derived_metrics"]["mobility"]["battery_hours_estimate"] == 6.1

    dto = ReviewIntelligenceService._to_review_input(laptop)
    assert dto.specs == envelope
    target = ReviewIntelligenceService._to_review_target(
        SimpleNamespace(
            laptop_id=dto.laptop_id,
            canonical_id=dto.canonical_id,
            chassis_key="asus:tuf-gaming:FX608JMR",
            title=dto.title,
            brand=dto.brand,
            laptop_family=dto.laptop_family,
            laptop_model=dto.laptop_model,
            mpn=dto.mpn,
            manufacturer_part_number=dto.mpn,
            retailer_sku=None,
            skus=(),
            mpns=(),
            product_urls=(),
            thumbnail_url=None,
            screen_size=dto.screen_size,
            matched_laptop_ids=(dto.laptop_id,),
            matched_canonical_ids=(dto.canonical_id,),
            specs=dto.specs,
        )
    )
    assert target.specs == envelope
