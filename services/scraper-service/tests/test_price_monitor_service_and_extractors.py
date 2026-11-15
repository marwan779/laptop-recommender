"""Unit tests for Flow B price monitoring classification and Compumarts/Sigma extractors."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.price_monitor.extractors import (
    CompumartsPriceExtractor,
    SigmaPriceExtractor,
)
from app.price_monitor.models import (
    PriceChangeType,
    PriceCheckBatchRequest,
    PriceCheckItem,
)
from app.price_monitor.service import PriceMonitorService


def _wrap_sigma_rsc(payload_obj: object) -> str:
    raw_json = json.dumps(payload_obj)
    escaped_push = json.dumps([1, raw_json])
    return f"<html><body><script>self.__next_f.push({escaped_push})</script></body></html>"


def test_compumarts_extractor_ignores_sold_out_in_related_products():
    html = """
    <html>
      <body>
        <main>
          <section class="product-info">
            <script type="application/ld+json">
              {
                "@type": "Product",
                "url": "https://www.compumarts.com/products/lenovo-legion-5",
                "offers": {"price": "65000.00"}
              }
            </script>
            <span class="price__current">65,000 EGP</span>
            <form action="/cart/add">
              <button type="submit" name="add">Add to cart</button>
            </form>
          </section>
          <section class="product-recommendations">
            <product-card>
              <span class="price__current">18,000 EGP</span>
              <span class="product-label--sold-out">Sold out</span>
            </product-card>
          </section>
        </main>
      </body>
    </html>
    """
    extractor = CompumartsPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(
        html,
        "https://www.compumarts.com/products/lenovo-legion-5",
    )
    assert price == 65000.0
    assert in_stock is True


def test_compumarts_extractor_detects_primary_sold_out_button_and_badge():
    html = """
    <html>
      <body>
        <main>
          <section class="product-info">
            <span class="price__current">65,000 EGP</span>
            <form action="/cart/add">
              <button type="submit" name="add" disabled>Sold out</button>
            </form>
          </section>
        </main>
      </body>
    </html>
    """
    extractor = CompumartsPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(
        html,
        "https://www.compumarts.com/products/lenovo-legion-5",
    )
    assert price == 65000.0
    assert in_stock is False


def test_sigma_extractor_matches_target_slug_and_avoids_wrong_product():
    payload = {
        "related_products": [
            {
                "slug": "cheap-accessory-laptop",
                "price": {"base": 20000, "current": 19500},
                "is_stock": False,
            }
        ],
        "product": {
            "slug": "asus-tuf-f15-target",
            "thumbnail": {"url": "https://cdn.example.com/a.jpg"},
            "price": {"base": 56000, "current": 54000},
            "is_stock": True,
        },
    }
    html = _wrap_sigma_rsc(payload)
    extractor = SigmaPriceExtractor()

    price, in_stock = extractor.extract_price_and_stock(
        html,
        "https://www.sigma-computer.com/en/item?id=asus-tuf-f15-target",
    )
    assert price == 54000.0
    assert in_stock is True

    # Missing target slug in multi-product RSC must not borrow another product's price
    missing_price, _ = extractor.extract_price_and_stock(
        html,
        "https://www.sigma-computer.com/en/item?id=nonexistent-laptop",
    )
    assert missing_price is None


class _MockResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_price_monitor_prioritizes_stock_transitions_over_simultaneous_price_changes(
    monkeypatch: pytest.MonkeyPatch,
):
    responses = {
        "https://store.example/oos-with-hike": _MockResponse(200, "<html></html>"),
        "https://store.example/restock-with-drop": _MockResponse(200, "<html></html>"),
        "https://store.example/oos-no-price": _MockResponse(200, "<html></html>"),
        "https://store.example/missing-price-same-stock": _MockResponse(200, "<html></html>"),
    }
    extractors_by_url = {
        "https://store.example/oos-with-hike": (55000.0, False),
        "https://store.example/restock-with-drop": (47000.0, True),
        "https://store.example/oos-no-price": (None, False),
        "https://store.example/missing-price-same-stock": (None, True),
    }

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            return responses[url]

    class _DispatchExtractor:
        def extract_price_and_stock(self, html: str, url: str):
            return extractors_by_url[url]

    import app.price_monitor.service as pm_mod

    monkeypatch.setattr(pm_mod, "AsyncSession", _FakeSession)
    monkeypatch.setattr(pm_mod, "get_price_extractor", lambda _store: _DispatchExtractor())

    service = PriceMonitorService(request_delay_seconds=0.0)
    batch = PriceCheckBatchRequest(
        batch_id="flow-b-batch",
        store_key="sigma",
        items=[
            PriceCheckItem(
                offer_id="1",
                laptop_id="l1",
                product_url="https://store.example/oos-with-hike",
                current_price_egp=50000.0,
                current_in_stock=True,
            ),
            PriceCheckItem(
                offer_id="2",
                laptop_id="l2",
                product_url="https://store.example/restock-with-drop",
                current_price_egp=50000.0,
                current_in_stock=False,
            ),
            PriceCheckItem(
                offer_id="3",
                laptop_id="l3",
                product_url="https://store.example/oos-no-price",
                current_price_egp=50000.0,
                current_in_stock=True,
            ),
            PriceCheckItem(
                offer_id="4",
                laptop_id="l4",
                product_url="https://store.example/missing-price-same-stock",
                current_price_egp=50000.0,
                current_in_stock=True,
            ),
        ],
    )

    resp = asyncio.run(service.check_batch_async(batch))
    by_id = {r.offer_id: r for r in resp.results}

    assert by_id["1"].change_type == PriceChangeType.OUT_OF_STOCK
    assert by_id["1"].has_changed is True
    assert by_id["1"].new_price_egp == 55000.0
    assert by_id["1"].price_delta_egp == 5000.0

    assert by_id["2"].change_type == PriceChangeType.RESTOCKED
    assert by_id["2"].has_changed is True
    assert by_id["2"].new_price_egp == 47000.0
    assert by_id["2"].price_delta_egp == -3000.0

    assert by_id["3"].change_type == PriceChangeType.OUT_OF_STOCK
    assert by_id["3"].has_changed is True
    assert by_id["3"].new_price_egp is None
    assert by_id["3"].error_message is None

    assert by_id["4"].change_type == PriceChangeType.ERROR
    assert by_id["4"].has_changed is False

    assert resp.out_of_stock_count == 2
    assert resp.errors_count == 1
    assert resp.changed_items_count == 3
