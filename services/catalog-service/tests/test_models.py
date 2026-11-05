import uuid

from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.models.outbox import OutboxMessage, OutboxStatus
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer


def test_laptop_configuration_instantiation():
    config_id = uuid.uuid4()

    config = LaptopConfiguration(
        id=config_id,
        canonical_id="asus-tuf-a16-fa608pm-rv169w-ryzen-9-rtx-5060-8gb",
        mpn="90NR0MC1-M003T0",
        brand="ASUS",
        laptop_family="Tuf Gaming",
        laptop_model="ASUS TUF Gaming A16 FA608PM-RV169W",
        title="ASUS TUF Gaming A16 FA608PM-RV169W - AMD Ryzen 9 8940HX - RTX 5060",
        cpu_manufacturer="AMD",
        cpu_model="Ryzen 9 8940HX",
        cpu_cores=16,
        cpu_threads=32,
        gpu_manufacturer="NVIDIA",
        gpu_model="GeForce RTX 5060",
        gpu_vram_gb=8,
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=1024,
        display_size_inches=16.0,
        display_resolution="1920x1200",
        display_width=1920,
        display_height=1200,
        min_price_egp=81500.0,
        cheapest_store="elbadr",
        stores_count=3,
        in_stock=True,
    )

    assert config.canonical_id == "asus-tuf-a16-fa608pm-rv169w-ryzen-9-rtx-5060-8gb"
    assert config.cpu_cores == 16
    assert config.gpu_vram_gb == 8
    assert config.min_price_egp == 81500.0


def test_laptop_metrics_instantiation():
    config_id = uuid.uuid4()

    metrics = LaptopMetrics(
        laptop_id=config_id,
        cpu_score=94.5,
        gpu_score=88.2,
        silicon_index=91.35,
        power_therm_score=85.0,
        display_score=78.4,
        mobility_score=62.1,
        longevity_score=84.0,
        ergonomics_score=80.0,
        connectivity_score=87.5,
        community_nlp_score=82.0,
        value_score=76.2,
        effective_price_egp=81500.0,
        is_recommendable_price=True,
        in_stock_active=True,
        delta_p_watts=110.0,
        simultaneous_load_w=170.0,
        electrical_status="BALANCED",
        estimated_battery_hours=5.8,
        silicon_tier="Enthusiast / Heavy Compute",
        display_tier="Gaming High-Refresh (165Hz)",
        portability_tier="Everyday Commuter (2.2kg)",
        upgradeability_tier="High (Dual SO-DIMM + Dual M.2)",
        pricing_status="FAIR_VALUE",
    )

    assert metrics.cpu_score == 94.5
    assert metrics.silicon_index == 91.35
    assert metrics.electrical_status == "BALANCED"


def test_laptop_offer_instantiation():
    config_id = uuid.uuid4()

    offer = LaptopOffer(
        laptop_configuration_id=config_id,
        store_key="elbadr",
        store_name="El Badr Group",
        product_url="https://elbadrgroupeg.store/asus-tuf-gaming-a16",
        price_egp=81500.0,
        in_stock=True,
    )

    assert offer.store_key == "elbadr"
    assert offer.price_egp == 81500.0
    assert offer.in_stock is True


def test_scraping_pointer_and_batch_log_instantiation():
    pointer = StoreScrapingPointer(
        store_key="compumarts",
        store_name="Compumarts",
        latest_pointers=["Laptop A", "Laptop B", "Laptop C"],
        total_active_offers=125,
    )
    assert pointer.store_key == "compumarts"
    assert len(pointer.latest_pointers) == 3

    log = ScrapingBatchLog(
        store_key="compumarts",
        trigger_type="CRON",
        status="SUCCESS",
        new_laptops_added=5,
        offers_updated=12,
    )
    assert log.status == "SUCCESS"
    assert log.new_laptops_added == 5


def test_outbox_message_instantiation():
    msg_id = uuid.uuid4()
    msg = OutboxMessage(
        id=msg_id,
        event_type="catalog.scrape.command",
        routing_key="catalog.scrape.command",
        payload_json='{"batch_id": "batch-100", "targets": ["compumarts"]}',
        status=OutboxStatus.PENDING,
        retry_count=1,
        max_retries=5,
        last_error="Temporary broker connection timeout",
        correlation_id="corr-123",
    )

    assert msg.id == msg_id
    assert msg.event_type == "catalog.scrape.command"
    assert msg.routing_key == "catalog.scrape.command"
    assert msg.status == OutboxStatus.PENDING
    assert msg.retry_count == 1
    assert msg.max_retries == 5
    assert msg.last_error == "Temporary broker connection timeout"
    assert msg.correlation_id == "corr-123"

