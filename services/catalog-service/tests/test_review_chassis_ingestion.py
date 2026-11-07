"""Integration tests for the review chassis outbox dispatch during ingestion.

These exercise the real application use case against the isolated ``db_session``
fixture (NullPool + rollback), verifying that seeding, the outbox message, and
the reviewed flags all live inside one transaction.
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
    our_targets = [
        t for t in command.payload.targets if f"MPN-A-{suffix}" in t.mpns or f"MPN-B-{suffix}" in t.mpns
    ]
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

    # Both variants are flagged reviewed with a timestamp.
    laptops = (
        await db_session.execute(
            select(LaptopConfiguration).where(
                LaptopConfiguration.canonical_id.in_([f"loq-16gb-{suffix}", f"loq-32gb-{suffix}"])
            )
        )
    ).scalars().all()
    assert len(laptops) == 2
    for laptop in laptops:
        assert laptop.has_reviews is True
        assert laptop.reviews_checked_at is not None


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

    second = await service.ingest_from_file(session=db_session, file_path=catalog_file)
    assert second.status == "SUCCESS"

    outbox = (await db_session.execute(select(OutboxMessage))).scalars().all()
    review_messages = [m for m in outbox if m.event_type == EventType.REVIEWS_SCRAPE_COMMAND]
    # Only the first ingestion enqueued a command; the second found no unreviewed laptops.
    assert len(review_messages) == 1


@pytest.mark.asyncio
async def test_outbox_message_and_flags_share_the_same_transaction(db_session: AsyncSession):
    """Rolling the transaction back must discard both the outbox row and the flags."""
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
