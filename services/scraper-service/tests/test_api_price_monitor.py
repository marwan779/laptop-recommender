from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.price_monitor.models import (
    PriceChangeType,
    PriceCheckBatchResponse,
    PriceCheckItemResult,
)

client = TestClient(app)


def test_price_monitor_check_endpoint():
    mock_response = PriceCheckBatchResponse(
        batch_id="test-batch-123",
        store_key="compumarts",
        total_items=1,
        changed_items_count=1,
        price_drops_count=1,
        results=[
            PriceCheckItemResult(
                offer_id="off-1",
                laptop_id="lap-1",
                product_url="https://compumarts.com/p1",
                old_price_egp=50000.0,
                new_price_egp=48000.0,
                old_in_stock=True,
                new_in_stock=True,
                has_changed=True,
                change_type=PriceChangeType.PRICE_DROP,
                price_delta_egp=-2000.0,
                http_status=200,
            )
        ],
    )

    with patch(
        "app.price_monitor.service.PriceMonitorService.check_batch_async",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        payload = {
            "batch_id": "test-batch-123",
            "store_key": "compumarts",
            "store_name": "Compumarts",
            "items": [
                {
                    "offer_id": "off-1",
                    "laptop_id": "lap-1",
                    "product_url": "https://compumarts.com/p1",
                    "current_price_egp": 50000.0,
                    "current_in_stock": True,
                }
            ],
        }
        res = client.post("/api/v1/price-monitor/check", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["batch_id"] == "test-batch-123"
        assert data["price_drops_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["price_delta_egp"] == -2000.0
