"""Application-service tests for multi-store price history telemetry.

Covers:
* Seeder writes history only for new offers and real price/stock changes.
* PriceSyncService appends a history row per real change and evicts cache.
* CatalogQueryService serves and caches price-history responses.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache.memory import InMemoryCacheProvider
from app.models.laptop import LaptopConfiguration
from app.models.offer import LaptopOffer, OfferPriceHistory
from app.repositories.seeder import CatalogSeederRepository
from app.schemas.price_sync import (
    PriceChangeType,
    PriceCheckBatchResponse,
    PriceCheckItemResult,
)
from app.services.catalog_query_service import CatalogQueryService
from app.services.price_sync_service import PriceSyncService


def _catalog_item(canonical_id: str, mpn: str, price: float, in_stock: bool = True) -> dict:
    return {
        "canonical_id": canonical_id,
        "mpn": mpn,
        "brand": "Lenovo",
        "laptop_family": "LOQ",
        "laptop_model": "15IRX9",
        "title": "Lenovo LOQ 15IRX9",
        "min_price_egp": price,
        "max_price_egp": price + 5000.0,
        "cheapest_store": "compumarts",
        "offers": [
            {
                "store_key": "compumarts",
                "store_name": "Compumarts",
                "product_url": f"https://compumarts.com/{mpn}",
                "price_egp": price,
                "in_stock": in_stock,
                "is_valid_price": True,
            },
            {
                "store_key": "elbadr",
                "store_name": "El Badr Group",
                "product_url": f"https://elbadr.store/{mpn}",
                "price_egp": price + 3000.0,
                "in_stock": True,
                "is_valid_price": True,
            },
        ],
        "specs": {
            "cpu": {"manufacturer": "Intel", "model": "Core i7-13650HX", "cores": 14, "threads": 20},
            "gpu": {"manufacturer": "NVIDIA", "model": "RTX 4060", "vram_gb": 8},
            "memory": {"capacity_gb": 16, "memory_type": "DDR5"},
            "storage": {"capacity_gb": 512, "storage_type": "SSD"},
            "display": {"size_inches": 15.6, "resolution": "1920x1080"},
        },
        "derived_metrics": {
            "topsis_inputs": {"cpu_score": 85.0, "gpu_score": 82.0, "value_score": 70.0},
        },
    }


@pytest.mark.asyncio
async def test_seeder_writes_history_only_for_new_or_changed_offers(db_session: AsyncSession):
    cid = f"test_hist_{uuid.uuid4().hex[:8]}"
    mpn = f"MPN-HIST-{uuid.uuid4().hex[:6]}"
    seeder = CatalogSeederRepository(db_session)

    # Initial seed: one history point per newly discovered offer.
    await seeder.upsert_catalog({"laptops": [_catalog_item(cid, mpn, 60000.0)]})
    await db_session.flush()

    laptop = (
        await db_session.execute(
            select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid)
        )
    ).scalar_one()
    initial_rows = (
        await db_session.execute(
            select(OfferPriceHistory).where(
                OfferPriceHistory.laptop_configuration_id == laptop.id
            )
        )
    ).scalars().all()
    assert len(initial_rows) == 2

    # Re-seed with an unchanged payload: no new history rows.
    await seeder.upsert_catalog({"laptops": [_catalog_item(cid, mpn, 60000.0)]})
    await db_session.flush()
    unchanged_rows = (
        await db_session.execute(
            select(OfferPriceHistory).where(
                OfferPriceHistory.laptop_configuration_id == laptop.id
            )
        )
    ).scalars().all()
    assert len(unchanged_rows) == 2

    # Re-seed with a real price change: two more history rows.
    await seeder.upsert_catalog({"laptops": [_catalog_item(cid, mpn, 55000.0)]})
    await db_session.flush()
    changed_rows = (
        await db_session.execute(
            select(OfferPriceHistory).where(
                OfferPriceHistory.laptop_configuration_id == laptop.id
            )
        )
    ).scalars().all()
    assert len(changed_rows) == 4


@pytest.mark.asyncio
async def test_price_sync_records_history_and_evicts_cache(db_session: AsyncSession):
    cache = InMemoryCacheProvider()
    await cache.connect()
    await cache.set("catalog:price_history:canon-1:all", b"stale")

    laptop_id = uuid.uuid4()
    offer_id = uuid.uuid4()
    db_session.add(
        LaptopConfiguration(
            id=laptop_id,
            canonical_id="canon-1",
            brand="HP",
            laptop_model="Victus 16",
            title="HP Victus 16",
            cpu_manufacturer="AMD",
            cpu_model="Ryzen 7",
            cpu_cores=8,
            cpu_threads=16,
            gpu_manufacturer="NVIDIA",
            gpu_model="RTX 4050",
            ram_capacity_gb=16,
            ram_type="DDR5",
            storage_capacity_gb=512,
            display_size_inches=16.1,
            display_resolution="1920x1080",
            display_width=1920,
            display_height=1080,
            min_price_egp=55000.0,
            cheapest_store="compumarts",
        )
    )
    db_session.add(
        LaptopOffer(
            id=offer_id,
            laptop_configuration_id=laptop_id,
            store_key="compumarts",
            store_name="Compumarts",
            product_url="https://compumarts.com/victus",
            price_egp=55000.0,
            in_stock=True,
        )
    )
    await db_session.commit()

    service = PriceSyncService(cache=cache)
    batch = PriceCheckBatchResponse(
        batch_id=str(uuid.uuid4()),
        store_key="compumarts",
        total_items=1,
        changed_items_count=1,
        price_drops_count=1,
        duration_seconds=0.2,
        results=[
            PriceCheckItemResult(
                offer_id=str(offer_id),
                laptop_id=str(laptop_id),
                product_url="https://compumarts.com/victus",
                old_price_egp=55000.0,
                new_price_egp=50000.0,
                old_in_stock=True,
                new_in_stock=True,
                has_changed=True,
                change_type=PriceChangeType.PRICE_DROP,
                price_delta_egp=-5000.0,
                http_status=200,
            )
        ],
    )

    summary = await service.apply_batch_results(db_session, batch)
    assert summary.offers_updated == 1

    history_rows = (
        await db_session.execute(
            select(OfferPriceHistory).where(OfferPriceHistory.offer_id == offer_id)
        )
    ).scalars().all()
    assert len(history_rows) == 1
    assert float(history_rows[0].price_egp) == 50000.0

    # Cache eviction is prefix-based; the stale payload must be gone.
    assert await cache.get("catalog:price_history:canon-1:all") is None


@pytest.mark.asyncio
async def test_query_service_returns_price_history(db_session: AsyncSession):
    laptop_id = uuid.uuid4()
    db_session.add(
        LaptopConfiguration(
            id=laptop_id,
            canonical_id="canon-cache-1",
            brand="ASUS",
            laptop_model="TUF F16",
            title="ASUS TUF Gaming F16",
            cpu_manufacturer="Intel",
            cpu_model="Core i5",
            cpu_cores=8,
            cpu_threads=12,
            gpu_manufacturer="NVIDIA",
            gpu_model="RTX 4050",
            ram_capacity_gb=8,
            ram_type="DDR5",
            storage_capacity_gb=512,
            display_size_inches=16.0,
            display_resolution="1920x1200",
            display_width=1920,
            display_height=1200,
            min_price_egp=45000.0,
            cheapest_store="elbadr",
        )
    )
    offer_id = uuid.uuid4()
    db_session.add(
        LaptopOffer(
            id=offer_id,
            laptop_configuration_id=laptop_id,
            store_key="elbadr",
            store_name="El Badr Group",
            product_url="https://elbadr.store/tuf",
            price_egp=45000.0,
            in_stock=True,
        )
    )
    await db_session.commit()

    service = CatalogQueryService(session=db_session)

    res = await service.get_laptop_price_history("canon-cache-1", days=90)
    assert res.canonical_id == "canon-cache-1"
    assert len(res.series) == 1
    assert res.series[0].store_key == "elbadr"
    assert res.current_best_price_egp == 45000.0
    assert res.days_window == 90
