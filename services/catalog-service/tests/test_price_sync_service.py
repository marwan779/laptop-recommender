import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.models.scraping import ScrapingBatchLog
from app.schemas.price_sync import (
    PriceChangeType,
    PriceCheckBatchResponse,
    PriceCheckItemResult,
)
from app.services.price_sync_service import PriceSyncService


@pytest.mark.asyncio
async def test_build_price_check_batches(db_session: AsyncSession):
    service = PriceSyncService()

    laptop_id = uuid.uuid4()
    laptop = LaptopConfiguration(
        id=laptop_id,
        canonical_id="test-laptop-1",
        brand="ASUS",
        laptop_model="ASUS TUF 15",
        title="ASUS TUF 15 Test",
        cpu_manufacturer="AMD",
        cpu_model="Ryzen 7",
        cpu_cores=8,
        cpu_threads=16,
        gpu_manufacturer="NVIDIA",
        gpu_model="RTX 4060",
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=512,
        display_size_inches=15.6,
        display_resolution="1920x1080",
        display_width=1920,
        display_height=1080,
        min_price_egp=50000.0,
        cheapest_store="compumarts",
    )
    db_session.add(laptop)

    offer1 = LaptopOffer(
        id=uuid.uuid4(),
        laptop_configuration_id=laptop_id,
        store_key="compumarts",
        store_name="Compumarts",
        product_url="https://compumarts.com/p1",
        price_egp=50000.0,
        in_stock=True,
    )
    offer2 = LaptopOffer(
        id=uuid.uuid4(),
        laptop_configuration_id=laptop_id,
        store_key="elbadr",
        store_name="El Badr",
        product_url="https://elbadr.store/p1",
        price_egp=52000.0,
        in_stock=True,
    )
    db_session.add_all([offer1, offer2])
    await db_session.commit()

    batches = await service.build_price_check_batches(db_session, limit=10)
    assert len(batches) == 2

    stores = {b.store_key for b in batches}
    assert "compumarts" in stores
    assert "elbadr" in stores


@pytest.mark.asyncio
async def test_apply_batch_results_price_drop_and_metrics_recalibration(db_session: AsyncSession):
    service = PriceSyncService()

    laptop_id = uuid.uuid4()
    offer_id = uuid.uuid4()

    laptop = LaptopConfiguration(
        id=laptop_id,
        canonical_id="test-laptop-drop",
        brand="Lenovo",
        laptop_model="Legion Pro 5",
        title="Lenovo Legion Pro 5",
        cpu_manufacturer="Intel",
        cpu_model="Core i7",
        cpu_cores=14,
        cpu_threads=20,
        gpu_manufacturer="NVIDIA",
        gpu_model="RTX 4070",
        ram_capacity_gb=32,
        ram_type="DDR5",
        storage_capacity_gb=1024,
        display_size_inches=16.0,
        display_resolution="2560x1600",
        display_width=2560,
        display_height=1600,
        min_price_egp=80000.0,
        cheapest_store="compumarts",
    )
    db_session.add(laptop)

    offer = LaptopOffer(
        id=offer_id,
        laptop_configuration_id=laptop_id,
        store_key="compumarts",
        store_name="Compumarts",
        product_url="https://compumarts.com/legion",
        price_egp=80000.0,
        in_stock=True,
    )
    db_session.add(offer)

    metrics = LaptopMetrics(
        laptop_id=laptop_id,
        cpu_score=85.0,
        gpu_score=82.0,
        silicon_index=83.5,
        power_therm_score=80.0,
        display_score=85.0,
        mobility_score=60.0,
        longevity_score=85.0,
        ergonomics_score=80.0,
        connectivity_score=80.0,
        community_nlp_score=75.0,
        value_score=65.0,
        effective_price_egp=80000.0,
        is_recommendable_price=True,
        in_stock_active=True,
        delta_p_watts=100.0,
        simultaneous_load_w=200.0,
        electrical_status="BALANCED",
        estimated_battery_hours=5.0,
        silicon_tier="High",
        display_tier="High",
        portability_tier="Medium",
        upgradeability_tier="High",
        pricing_status="FAIR_VALUE",
    )
    db_session.add(metrics)
    await db_session.commit()

    # Simulate price drop response: 80,000 -> 72,000 EGP (-8,000 drop)
    batch_resp = PriceCheckBatchResponse(
        batch_id=str(uuid.uuid4()),
        store_key="compumarts",
        total_items=1,
        changed_items_count=1,
        price_drops_count=1,
        duration_seconds=0.5,
        results=[
            PriceCheckItemResult(
                offer_id=str(offer_id),
                laptop_id=str(laptop_id),
                product_url="https://compumarts.com/legion",
                old_price_egp=80000.0,
                new_price_egp=72000.0,
                old_in_stock=True,
                new_in_stock=True,
                has_changed=True,
                change_type=PriceChangeType.PRICE_DROP,
                price_delta_egp=-8000.0,
                http_status=200,
            )
        ],
    )

    summary = await service.apply_batch_results(db_session, batch_resp)
    assert summary.offers_updated == 1
    assert summary.price_drops_detected == 1
    assert summary.parent_laptops_recalculated == 1
    assert summary.metrics_recalibrated == 1

    # Verify Database state
    updated_offer = await db_session.get(LaptopOffer, offer_id)
    assert float(updated_offer.price_egp) == 72000.0
    assert float(updated_offer.previous_price_egp) == 80000.0

    updated_laptop = await db_session.get(LaptopConfiguration, laptop_id)
    assert float(updated_laptop.min_price_egp) == 72000.0
    assert float(updated_laptop.previous_min_price_egp) == 80000.0

    updated_metrics = await db_session.get(LaptopMetrics, laptop_id)
    assert float(updated_metrics.effective_price_egp) == 72000.0
    # Because price dropped from 80k to 72k, value_score must increase
    assert float(updated_metrics.value_score) > 65.0

    # Verify audit log in scraping_batch_log
    log = await db_session.get(ScrapingBatchLog, uuid.UUID(batch_resp.batch_id))
    assert log is not None
    assert log.trigger_type == "PRICE_MONITOR"
    assert log.status == "SUCCESS"


@pytest.mark.asyncio
async def test_apply_batch_results_out_of_stock_flips_stock(db_session: AsyncSession):
    service = PriceSyncService()

    laptop_id = uuid.uuid4()
    offer_id = uuid.uuid4()

    laptop = LaptopConfiguration(
        id=laptop_id,
        canonical_id="test-laptop-oos",
        brand="HP",
        laptop_model="Omen 16",
        title="HP Omen 16 Test",
        cpu_manufacturer="Intel",
        cpu_model="Core i7",
        cpu_cores=16,
        cpu_threads=24,
        gpu_manufacturer="NVIDIA",
        gpu_model="RTX 4060",
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=1024,
        display_size_inches=16.1,
        display_resolution="1920x1080",
        display_width=1920,
        display_height=1080,
        min_price_egp=60000.0,
        in_stock=True,
    )
    db_session.add(laptop)

    offer = LaptopOffer(
        id=offer_id,
        laptop_configuration_id=laptop_id,
        store_key="compumarts",
        store_name="Compumarts",
        product_url="https://compumarts.com/omen",
        price_egp=60000.0,
        in_stock=True,
    )
    db_session.add(offer)
    await db_session.commit()

    batch_resp = PriceCheckBatchResponse(
        batch_id=str(uuid.uuid4()),
        store_key="compumarts",
        total_items=1,
        changed_items_count=1,
        out_of_stock_count=1,
        results=[
            PriceCheckItemResult(
                offer_id=str(offer_id),
                laptop_id=str(laptop_id),
                product_url="https://compumarts.com/omen",
                old_price_egp=60000.0,
                new_price_egp=60000.0,
                old_in_stock=True,
                new_in_stock=False,
                has_changed=True,
                change_type=PriceChangeType.OUT_OF_STOCK,
                http_status=200,
            )
        ],
    )

    summary = await service.apply_batch_results(db_session, batch_resp)
    assert summary.offers_updated == 1
    assert summary.out_of_stock_detected == 1

    updated_offer = await db_session.get(LaptopOffer, offer_id)
    assert updated_offer.in_stock is False

    updated_laptop = await db_session.get(LaptopConfiguration, laptop_id)
    assert updated_laptop.in_stock is False


@pytest.mark.asyncio
async def test_apply_batch_results_unchanged_fast_watermark(db_session: AsyncSession):
    service = PriceSyncService()

    laptop_id = uuid.uuid4()
    offer_id = uuid.uuid4()

    laptop = LaptopConfiguration(
        id=laptop_id,
        canonical_id="test-laptop-unchanged",
        brand="Dell",
        laptop_model="G15",
        title="Dell G15 Test",
        cpu_manufacturer="Intel",
        cpu_model="Core i5",
        cpu_cores=10,
        cpu_threads=16,
        gpu_manufacturer="NVIDIA",
        gpu_model="RTX 3050",
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=512,
        display_size_inches=15.6,
        display_resolution="1920x1080",
        display_width=1920,
        display_height=1080,
        min_price_egp=35000.0,
        in_stock=True,
    )
    db_session.add(laptop)

    offer = LaptopOffer(
        id=offer_id,
        laptop_configuration_id=laptop_id,
        store_key="compumarts",
        store_name="Compumarts",
        product_url="https://compumarts.com/g15",
        price_egp=35000.0,
        in_stock=True,
    )
    db_session.add(offer)
    await db_session.commit()

    initial_price_updated = offer.price_updated_at

    batch_resp = PriceCheckBatchResponse(
        batch_id=str(uuid.uuid4()),
        store_key="compumarts",
        total_items=1,
        changed_items_count=0,
        results=[
            PriceCheckItemResult(
                offer_id=str(offer_id),
                laptop_id=str(laptop_id),
                product_url="https://compumarts.com/g15",
                old_price_egp=35000.0,
                new_price_egp=35000.0,
                old_in_stock=True,
                new_in_stock=True,
                has_changed=False,
                change_type=PriceChangeType.UNCHANGED,
                http_status=200,
            )
        ],
    )

    summary = await service.apply_batch_results(db_session, batch_resp)
    assert summary.offers_unchanged == 1
    assert summary.offers_updated == 0

    await db_session.refresh(offer)
    # price_updated_at did not change, but last_checked_at is refreshed
    assert offer.price_updated_at == initial_price_updated
    assert offer.last_checked_at is not None
