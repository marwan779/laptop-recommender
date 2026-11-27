import uuid
from types import SimpleNamespace

import pytest

from app.domain.pricing import PriceChangeType
from app.schemas.events import EventType, LaptopPriceChangedBatchEvent
from app.schemas.price_sync import PriceCheckBatchResponse, PriceCheckItemResult
from app.services.price_sync_service import PriceSyncService


@pytest.mark.asyncio
async def test_apply_batch_results_stages_single_batch_event_for_changed_laptops(monkeypatch):
    laptop1_id = uuid.uuid4()
    laptop2_id = uuid.uuid4()
    offer1_id = uuid.uuid4()
    offer2_id = uuid.uuid4()

    laptops = {
        laptop1_id: SimpleNamespace(
            id=laptop1_id,
            canonical_id="laptop_tuf_f16",
            title="ASUS TUF Gaming F16",
            min_price_egp=73500.0,
            max_price_egp=75000.0,
            previous_min_price_egp=None,
            cheapest_store="twob",
            price_spread_egp=1500.0,
            stores_count=1,
            available_stores=["twob"],
            in_stock=True,
            ram_capacity_gb=16,
            price_updated_at=None,
            price_checked_at=None,
        ),
        laptop2_id: SimpleNamespace(
            id=laptop2_id,
            canonical_id="laptop_legion_5",
            title="Lenovo Legion 5",
            min_price_egp=80000.0,
            max_price_egp=80000.0,
            previous_min_price_egp=None,
            cheapest_store="btech",
            price_spread_egp=0.0,
            stores_count=0,
            available_stores=[],
            in_stock=False,
            ram_capacity_gb=16,
            price_updated_at=None,
            price_checked_at=None,
        ),
    }

    offers = {
        offer1_id: SimpleNamespace(
            id=offer1_id,
            laptop_configuration_id=laptop1_id,
            store_key="twob",
            price_egp=73500.0,
            previous_price_egp=None,
            in_stock=True,
            is_valid_price=True,
            price_updated_at=None,
            last_checked_at=None,
        ),
        offer2_id: SimpleNamespace(
            id=offer2_id,
            laptop_configuration_id=laptop2_id,
            store_key="btech",
            price_egp=80000.0,
            previous_price_egp=None,
            in_stock=False,
            is_valid_price=True,
            price_updated_at=None,
            last_checked_at=None,
        ),
    }

    class _FakeSession:
        async def commit(self):
            return None

    class _FakeOfferRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, oid):
            return offers.get(oid)

        async def get_offers_by_laptop_id(self, lid):
            return [o for o in offers.values() if o.laptop_configuration_id == lid]

        async def bulk_touch_watermarks(self, ids):
            return None

    class _FakeLaptopRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, lid):
            return laptops.get(lid)

        async def get_metrics_by_laptop_id(self, lid):
            return None

    class _FakeLogRepo:
        def __init__(self, session):
            self.session = session

        async def record_batch_log(self, **kwargs):
            return None

    class _FakeHistoryRepo:
        def __init__(self, session):
            self.session = session

        async def record_point(self, **kwargs):
            return None

    staged_events = []

    class _FakeOutboxRepo:
        def __init__(self, session):
            self.session = session

        async def insert_outbox_event(self, **kwargs):
            staged_events.append(kwargs)
            return None

    import app.services.price_sync_service as pss_mod

    monkeypatch.setattr(pss_mod, "OfferRepository", _FakeOfferRepo)
    monkeypatch.setattr(pss_mod, "LaptopRepository", _FakeLaptopRepo)
    monkeypatch.setattr(pss_mod, "BatchLogRepository", _FakeLogRepo)
    monkeypatch.setattr(pss_mod, "PriceHistoryRepository", _FakeHistoryRepo)
    monkeypatch.setattr(pss_mod, "OutboxRepository", _FakeOutboxRepo)

    service = PriceSyncService()
    batch_resp = PriceCheckBatchResponse(
        batch_id=str(uuid.uuid4()),
        store_key="twob",
        total_items=2,
        changed_items_count=2,
        results=[
            PriceCheckItemResult(
                offer_id=str(offer1_id),
                laptop_id=str(laptop1_id),
                product_url="https://2b.com.eg/tuf",
                old_price_egp=73500.0,
                new_price_egp=69999.0,
                old_in_stock=True,
                new_in_stock=True,
                has_changed=True,
                change_type=PriceChangeType.PRICE_DROP,
                http_status=200,
            ),
            PriceCheckItemResult(
                offer_id=str(offer2_id),
                laptop_id=str(laptop2_id),
                product_url="https://btech.com/legion",
                old_price_egp=80000.0,
                new_price_egp=80000.0,
                old_in_stock=False,
                new_in_stock=True,
                has_changed=True,
                change_type=PriceChangeType.RESTOCKED,
                http_status=200,
            ),
        ],
    )

    await service.apply_batch_results(_FakeSession(), batch_resp, commit=True)

    assert len(staged_events) == 1
    outbox_call = staged_events[0]
    assert outbox_call["event_type"] == EventType.LAPTOP_PRICE_CHANGED_EVENT
    assert outbox_call["routing_key"] == EventType.LAPTOP_PRICE_CHANGED_EVENT

    evt = outbox_call["payload"]
    assert isinstance(evt, LaptopPriceChangedBatchEvent)
    assert len(evt.payload.changes) == 2

    by_id = {c.canonical_id: c for c in evt.payload.changes}
    assert by_id["laptop_tuf_f16"].change_type == "PRICE_DROP"
    assert by_id["laptop_tuf_f16"].old_price_egp == 73500.0
    assert by_id["laptop_tuf_f16"].new_price_egp == 69999.0
    assert by_id["laptop_legion_5"].change_type == "RESTOCK"
    assert by_id["laptop_legion_5"].in_stock is True
