import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.price_sync_cron import PriceSyncCronJob
from app.models.laptop import LaptopConfiguration
from app.models.offer import LaptopOffer
from app.models.outbox import OutboxMessage
from app.schemas.events import EventType


@pytest.mark.asyncio
async def test_price_sync_cron_dispatch_once_stages_outbox_commands(db_session: AsyncSession):
    store_key = f"cron-price-{uuid.uuid4().hex[:8]}"
    laptop_id = uuid.uuid4()
    offer_id = uuid.uuid4()

    laptop = LaptopConfiguration(
        id=laptop_id,
        canonical_id=f"test-cron-laptop-{uuid.uuid4().hex[:6]}",
        brand="Lenovo",
        laptop_model="Legion 5",
        title="Lenovo Legion 5",
        cpu_manufacturer="AMD",
        cpu_model="Ryzen 7",
        cpu_cores=8,
        cpu_threads=16,
        gpu_manufacturer="NVIDIA",
        gpu_model="RTX 4060",
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=1024,
        display_size_inches=15.6,
        display_resolution="1920x1080",
        display_width=1920,
        display_height=1080,
        min_price_egp=55000.0,
        cheapest_store=store_key,
    )
    await db_session.merge(laptop)

    offer = LaptopOffer(
        id=offer_id,
        laptop_configuration_id=laptop_id,
        store_key=store_key,
        store_name="Cron Test Store",
        product_url=f"https://{store_key}.example/legion5",
        price_egp=55000.0,
        in_stock=True,
        is_valid_price=True,
    )
    await db_session.merge(offer)
    await db_session.commit()

    job = PriceSyncCronJob()
    message_ids = await job.dispatch_once(store_key=store_key, limit=10, session=db_session)
    await db_session.commit()

    assert len(message_ids) == 1

    outbox_row = (
        await db_session.execute(
            select(OutboxMessage).where(OutboxMessage.id == uuid.UUID(message_ids[0]))
        )
    ).scalar_one()
    assert outbox_row.event_type == EventType.PRICES_CHECK_COMMAND
    assert outbox_row.routing_key == EventType.PRICES_CHECK_COMMAND
    assert outbox_row.status == "PENDING"
    assert store_key in outbox_row.payload_json


@pytest.mark.asyncio
async def test_price_sync_cron_dispatch_once_no_stale_offers_returns_empty(
    db_session: AsyncSession,
):
    job = PriceSyncCronJob()
    message_ids = await job.dispatch_once(
        store_key=f"empty-store-{uuid.uuid4().hex[:8]}",
        limit=10,
        session=db_session,
    )
    assert message_ids == []

