import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.repositories.seeder import CatalogSeederRepository, SeederSummary


def _build_sample_catalog_item(
    canonical_id: str,
    mpn: str = "TEST-MPN-100",
    min_price: float = 60000.0,
    store_key: str = "compumarts",
    ram_gb: int = 16,
    storage_gb: int = 1024,
) -> dict:
    return {
        "canonical_id": canonical_id,
        "mpn": mpn,
        "brand": "Lenovo",
        "laptop_family": "Legion",
        "laptop_model": "Legion Pro 5 16IRX9",
        "title": f"Lenovo Legion Pro 5 16IRX9 - Core i7-14700HX - RTX 4060 - {ram_gb}GB {storage_gb}GB",
        "thumbnail_url": "https://example.com/legion.jpg",
        "min_price_egp": min_price,
        "max_price_egp": min_price + 5000.0,
        "cheapest_store": store_key,
        "price_spread_egp": 5000.0,
        "stores_count": 2,
        "specs": {
            "identity": {
                "brand": "Lenovo",
                "laptop_family": "Legion",
                "laptop_model": "Legion Pro 5 16IRX9",
                "manufacturer_part_number": mpn,
                "color": "Onyx Grey",
                "form_factor": "Clamshell",
                "release_year": 2024,
                "warranty_years": 2,
            },
            "cpu": {
                "manufacturer": "Intel",
                "line": "Core i7",
                "model": "Core i7-14700HX",
                "cores": 20,
                "threads": 28,
                "clock_base_ghz": 2.1,
                "clock_boost_ghz": 5.5,
                "cache_mb": 33,
                "base_power_w": 55,
            },
            "gpu": {
                "manufacturer": "NVIDIA",
                "model": "GeForce RTX 4060",
                "vram_gb": 8,
                "vram_type": "GDDR6",
                "tdp_w": 140,
                "integrated": False,
            },
            "memory": {
                "capacity_gb": ram_gb,
                "memory_type": "DDR5",
                "speed": "5600 MHz",
                "slot_count": 2,
                "max_supported_gb": 64,
            },
            "storage": {
                "capacity_gb": storage_gb,
                "storage_type": "SSD",
                "interface": "PCIe 4.0 NVMe",
                "slot_count": 2,
            },
            "display": {
                "size_inches": 16.0,
                "resolution": "2560x1600",
                "resolution_width": 2560,
                "resolution_height": 1600,
                "panel_type": "IPS",
                "refresh_rate_hz": 240,
                "brightness_nits": 500,
                "color_gamut": "100% sRGB",
            },
            "power_battery": {
                "battery_capacity_wh": 80.0,
                "power_adapter_w": 300.0,
                "fast_charging": True,
            },
            "physical": {
                "weight_kg": 2.5,
                "width_mm": 363.4,
                "depth_mm": 260.3,
                "height_mm": 26.9,
            },
            "build_security": {
                "has_backlit_keyboard": True,
                "keyboard_backlight_type": "4-Zone RGB",
                "has_fingerprint": False,
                "security_features": ["Firmware TPM 2.0"],
            },
            "audio_webcam": {
                "speaker_count": 2,
                "audio_system": "Nahimic Audio",
                "webcam_resolution": "1080p",
                "has_privacy_shutter": True,
            },
            "connectivity": {
                "wifi": "Wi-Fi 6E",
                "bluetooth": "Bluetooth 5.2",
                "ethernet": True,
                "ports": ["4x USB-A", "2x USB-C", "1x HDMI 2.1"],
            },
            "operating_system": {
                "name": "Windows 11 Home",
            },
        },
        "offers": [
            {
                "store_key": store_key,
                "store_name": "Compumarts Egypt",
                "store_domain": "compumarts.com",
                "product_url": f"https://compumarts.com/{canonical_id}",
                "price_egp": min_price,
                "in_stock": True,
                "is_valid_price": True,
                "retailer_sku": f"SKU-{canonical_id}",
                "mpn": mpn,
            },
            {
                "store_key": "elbadr",
                "store_name": "El Badr Group",
                "store_domain": "elbadrgroupeg.store",
                "product_url": f"https://elbadrgroupeg.store/{canonical_id}",
                "price_egp": min_price + 5000.0,
                "in_stock": True,
                "is_valid_price": True,
                "retailer_sku": f"SKU-ELB-{canonical_id}",
                "mpn": mpn,
            },
        ],
        "derived_metrics": {
            "topsis_inputs": {
                "cpu_score": 92.5,
                "gpu_score": 88.0,
                "silicon_index": 90.0,
                "power_therm_score": 95.0,
                "display_score": 85.0,
                "mobility_score": 60.0,
                "longevity_score": 92.0,
                "ergonomics_score": 80.0,
                "connectivity_score": 85.0,
                "community_nlp_score": 75.0,
                "value_score": 82.0,
                "effective_price_egp": min_price,
                "is_recommendable_price": True,
                "in_stock_active": True,
            },
            "silicon": {
                "effective_cpu_score": 92.5,
                "effective_gpu_score": 88.0,
                "silicon_index": 90.0,
                "tgp_source": "EXPLICIT_SPEC",
                "is_copilot_plus_pc": False,
            },
            "power": {
                "delta_p_watts": 105.0,
                "simultaneous_load_w": 195.0,
                "electrical_status": "UNCONSTRAINED_HEADROOM",
            },
            "display": {
                "display_score": 85.0,
                "color_gamut_tier": "100% sRGB",
            },
            "mobility": {
                "portability_score": 60.0,
                "portability_tier": "BALANCED",
                "battery_hours_estimate": 5.5,
            },
            "longevity": {
                "upgradeability_score": 92.0,
                "upgradeability_tier": "MAXIMUM_UPGRADEABLE",
            },
            "economics": {
                "pricing_status": "IN_STOCK_ACTIVE",
                "min_price_egp": min_price,
            },
        },
    }


@pytest.mark.asyncio
async def test_seeder_upsert_new_laptops(db_session: AsyncSession):
    cid1 = f"test_seed_laptop_1_{uuid.uuid4().hex[:8]}"
    cid2 = f"test_seed_laptop_2_{uuid.uuid4().hex[:8]}"

    catalog_dict = {
        "laptops": [
            _build_sample_catalog_item(cid1, mpn=f"MPN-1-{uuid.uuid4().hex[:6]}", min_price=55000.0),
            _build_sample_catalog_item(cid2, mpn=f"MPN-2-{uuid.uuid4().hex[:6]}", min_price=65000.0),
        ]
    }

    seeder = CatalogSeederRepository(db_session)
    summary: SeederSummary = await seeder.upsert_catalog(catalog_dict)

    assert summary.total_laptops_processed == 2
    assert summary.new_laptops_created == 2
    assert summary.laptops_updated == 0
    assert summary.offers_created == 4
    assert summary.metrics_created == 2

    # Verify query from database
    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == cid1)
        .options(
            selectinload(LaptopConfiguration.offers),
            selectinload(LaptopConfiguration.metrics),
        )
    )
    result = await db_session.execute(stmt)
    laptop = result.scalar_one_or_none()

    assert laptop is not None
    assert laptop.brand == "Lenovo"
    assert laptop.cpu_model == "Core i7-14700HX"
    assert laptop.ram_speed_mhz == 5600
    assert laptop.display_refresh_rate_hz == 240
    assert laptop.min_price_egp == 55000.0
    assert len(laptop.offers) == 2
    assert laptop.metrics is not None
    assert float(laptop.metrics.cpu_score) == 92.50
    assert float(laptop.metrics.gpu_score) == 88.00


@pytest.mark.asyncio
async def test_seeder_upsert_existing_laptop_and_price_history(db_session: AsyncSession):
    cid = f"test_seed_price_change_{uuid.uuid4().hex[:8]}"
    mpn = f"MPN-PRICE-{uuid.uuid4().hex[:6]}"

    # Initial seed
    catalog_v1 = {
        "laptops": [
            _build_sample_catalog_item(cid, mpn=mpn, min_price=70000.0),
        ]
    }

    seeder = CatalogSeederRepository(db_session)
    summary_v1 = await seeder.upsert_catalog(catalog_v1)
    assert summary_v1.new_laptops_created == 1

    # Second seed with updated price and modified title
    catalog_v2 = {
        "laptops": [
            _build_sample_catalog_item(cid, mpn=mpn, min_price=64000.0),
        ]
    }
    catalog_v2["laptops"][0]["title"] = "Updated Title with Discount"

    summary_v2 = await seeder.upsert_catalog(catalog_v2)
    assert summary_v2.new_laptops_created == 0
    assert summary_v2.laptops_updated == 1
    assert summary_v2.offers_updated == 2
    assert summary_v2.metrics_updated == 1

    # Verify database state has previous_min_price_egp and new price
    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == cid)
        .options(
            selectinload(LaptopConfiguration.offers),
            selectinload(LaptopConfiguration.metrics),
        )
    )
    result = await db_session.execute(stmt)
    laptop = result.scalar_one_or_none()

    assert laptop is not None
    assert laptop.title == "Updated Title with Discount"
    assert float(laptop.previous_min_price_egp) == 70000.0
    assert float(laptop.min_price_egp) == 64000.0

    # Verify offer previous price
    comp_offer = next(o for o in laptop.offers if o.store_key == "compumarts")
    assert float(comp_offer.previous_price_egp) == 70000.0
    assert float(comp_offer.price_egp) == 64000.0


@pytest.mark.asyncio
async def test_seeder_identity_matching_by_mpn(db_session: AsyncSession):
    cid_initial = f"test_mpn_initial_{uuid.uuid4().hex[:8]}"
    mpn_shared = f"MPN-SHARED-{uuid.uuid4().hex[:6]}"

    catalog_v1 = {
        "laptops": [
            _build_sample_catalog_item(cid_initial, mpn=mpn_shared, min_price=50000.0),
        ]
    }

    seeder = CatalogSeederRepository(db_session)
    await seeder.upsert_catalog(catalog_v1)

    # In a second batch, incoming item has a different canonical_id but identical MPN
    cid_secondary = f"test_mpn_secondary_{uuid.uuid4().hex[:8]}"
    catalog_v2 = {
        "laptops": [
            _build_sample_catalog_item(cid_secondary, mpn=mpn_shared, min_price=49000.0),
        ]
    }

    summary_v2 = await seeder.upsert_catalog(catalog_v2)
    # MPN match resolves to existing laptop
    assert summary_v2.new_laptops_created == 0
    assert summary_v2.laptops_updated == 1


@pytest.mark.asyncio
async def test_seeder_safe_fallbacks_for_partial_specs(db_session: AsyncSession):
    cid = f"test_minimal_specs_{uuid.uuid4().hex[:8]}"
    minimal_laptop = {
        "canonical_id": cid,
        "title": "Minimal Specification Laptop",
        "specs": {
            "identity": {"brand": "Generic"},
            "cpu": {"model": "Intel Celeron"},
            "gpu": {"model": "Intel UHD Graphics"},
        },
    }

    catalog = {"laptops": [minimal_laptop]}
    seeder = CatalogSeederRepository(db_session)
    summary = await seeder.upsert_catalog(catalog)

    assert summary.new_laptops_created == 1

    stmt = select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid)
    result = await db_session.execute(stmt)
    laptop = result.scalar_one_or_none()

    assert laptop is not None
    assert laptop.brand == "Generic"
    assert laptop.ram_capacity_gb == 8  # Default applied
    assert laptop.storage_capacity_gb == 256  # Default applied
    assert laptop.display_resolution == "1920x1080"  # Default applied


@pytest.mark.asyncio
async def test_seeder_hardware_guarded_resolution_for_same_mpn_variants(db_session: AsyncSession):
    """Verify that multiple retailer hardware configurations sharing an identical factory MPN

    are preserved as separate database records and not incorrectly overwritten.
    """
    base_mpn = f"83DV01HSED-{uuid.uuid4().hex[:6]}"
    cid_8_512 = f"laptop_lenovo_loq_{base_mpn.lower()}_8gb_512gb"
    cid_16_512 = f"laptop_lenovo_loq_{base_mpn.lower()}_16gb_512gb"
    cid_16_1024 = f"laptop_lenovo_loq_{base_mpn.lower()}_16gb_1024gb"

    seeder = CatalogSeederRepository(db_session)

    # Batch 1: Seed base 8GB / 512GB model
    catalog_b1 = {
        "laptops": [
            _build_sample_catalog_item(cid_8_512, mpn=base_mpn, min_price=35000.0, ram_gb=8, storage_gb=512),
        ]
    }
    summary_b1 = await seeder.upsert_catalog(catalog_b1)
    assert summary_b1.new_laptops_created == 1
    assert summary_b1.laptops_updated == 0

    # Batch 2: Seed all 3 upgraded/base variants together
    catalog_b2 = {
        "laptops": [
            _build_sample_catalog_item(cid_8_512, mpn=base_mpn, min_price=34000.0, ram_gb=8, storage_gb=512),
            _build_sample_catalog_item(cid_16_512, mpn=base_mpn, min_price=38000.0, ram_gb=16, storage_gb=512),
            _build_sample_catalog_item(cid_16_1024, mpn=base_mpn, min_price=42000.0, ram_gb=16, storage_gb=1024),
        ]
    }
    summary_b2 = await seeder.upsert_catalog(catalog_b2)
    assert summary_b2.new_laptops_created == 2  # The 16GB/512GB and 16GB/1024GB variants are new
    assert summary_b2.laptops_updated == 1      # The 8GB/512GB variant was updated

    # Verify all 3 configurations exist distinctly in PostgreSQL
    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.mpn == base_mpn)
        .order_by(LaptopConfiguration.ram_capacity_gb, LaptopConfiguration.storage_capacity_gb)
    )
    result = await db_session.execute(stmt)
    records = result.scalars().all()

    assert len(records) == 3
    assert (records[0].ram_capacity_gb, records[0].storage_capacity_gb) == (8, 512)
    assert (records[1].ram_capacity_gb, records[1].storage_capacity_gb) == (16, 512)
    assert (records[2].ram_capacity_gb, records[2].storage_capacity_gb) == (16, 1024)

    # Batch 3: Alternate canonical ID with exact same MPN and 16GB / 1024GB hardware specs
    # Should resolve to records[2] via secondary identity resolution without creating duplicate
    cid_alt = f"laptop_legacy_slug_{base_mpn.lower()}_alt"
    catalog_b3 = {
        "laptops": [
            _build_sample_catalog_item(cid_alt, mpn=base_mpn, min_price=41000.0, ram_gb=16, storage_gb=1024),
        ]
    }
    summary_b3 = await seeder.upsert_catalog(catalog_b3)
    assert summary_b3.new_laptops_created == 0
    assert summary_b3.laptops_updated == 1

    # Verify count is still exactly 3
    result_b3 = await db_session.execute(stmt)
    assert len(result_b3.scalars().all()) == 3
