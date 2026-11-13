import uuid
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.price_sync_cron import PriceSyncCronJob
from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.schemas.price_sync import (
    PriceChangeType,
    PriceCheckBatchResponse,
    PriceCheckItemResult,
)


@pytest.mark.asyncio
async def test_price_sync_cron_run_once_success(db_session: AsyncSession):
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
        cheapest_store="compumarts",
    )
    await db_session.merge(laptop)

    offer = LaptopOffer(
        id=offer_id,
        laptop_configuration_id=laptop_id,
        store_key="compumarts",
        store_name="Compumarts",
        product_url="https://compumarts.com/legion5",
        price_egp=55000.0,
        in_stock=True,
    )
    await db_session.merge(offer)

    metrics = LaptopMetrics(
        laptop_id=laptop_id,
        cpu_score=80.0,
        gpu_score=80.0,
        silicon_index=80.0,
        power_therm_score=80.0,
        display_score=80.0,
        mobility_score=60.0,
        longevity_score=80.0,
        ergonomics_score=80.0,
        connectivity_score=80.0,
        community_nlp_score=75.0,
        value_score=65.0,
        effective_price_egp=55000.0,
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
    await db_session.merge(metrics)
    await db_session.commit()

    # Mock response from scraper-service price monitor endpoint
    def mock_handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        mock_resp = PriceCheckBatchResponse(
            batch_id=body["batch_id"],
            store_key=body["store_key"],
            total_items=len(body["items"]),
            changed_items_count=1,
            price_drops_count=1,
            results=[
                PriceCheckItemResult(
                    offer_id=str(offer_id),
                    laptop_id=str(laptop_id),
                    product_url="https://compumarts.com/legion5",
                    old_price_egp=55000.0,
                    new_price_egp=51000.0,  # 4000 EGP price drop!
                    old_in_stock=True,
                    new_in_stock=True,
                    has_changed=True,
                    change_type=PriceChangeType.PRICE_DROP,
                    price_delta_egp=-4000.0,
                    http_status=200,
                )
            ],
        )
        return httpx.Response(200, json=mock_resp.model_dump(mode="json"))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    job = PriceSyncCronJob()

    summaries = await job.run_once(store_key="compumarts", session=db_session, http_client=mock_client)

    assert len(summaries) >= 1
    compumarts_summary = next(s for s in summaries if s.store_key == "compumarts")
    assert compumarts_summary.offers_updated == 1
    assert compumarts_summary.price_drops_detected == 1

    # Verify DB updated
    updated_offer = await db_session.get(LaptopOffer, offer_id)
    assert float(updated_offer.price_egp) == 51000.0
    assert float(updated_offer.previous_price_egp) == 55000.0

