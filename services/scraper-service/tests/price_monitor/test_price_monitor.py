import pytest

from app.price_monitor.extractors import (
    CompumartsPriceExtractor,
    ElBadrPriceExtractor,
    GenericPriceExtractor,
    SigmaPriceExtractor,
    get_price_extractor,
    parse_egp_number,
)
from app.price_monitor.models import (
    PriceChangeType,
    PriceCheckBatchRequest,
    PriceCheckItem,
)
from app.price_monitor.service import PriceMonitorService


def test_parse_egp_number():
    assert parse_egp_number("81,500.00 EGP") == 81500.0
    assert parse_egp_number("99,550 EGP") == 99550.0
    assert parse_egp_number("EGP 42,000") == 42000.0
    assert parse_egp_number("35.500,00 ج.م") == 35500.0
    assert parse_egp_number("٨١٥٠٠ جنيه") == 81500.0
    assert parse_egp_number(None) is None
    assert parse_egp_number("") is None
    assert parse_egp_number("Sold Out") is None


def test_compumarts_extractor_json_ld():
    html = """
    <html>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": "ASUS TUF A16",
        "offers": {
          "@type": "Offer",
          "price": "99550.00",
          "availability": "https://schema.org/InStock"
        }
      }
      </script>
    </html>
    """
    extractor = CompumartsPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(html, "https://compumarts.com/test")
    assert price == 99550.0
    assert in_stock is True


def test_compumarts_extractor_css_fallback_and_sold_out():
    html = """
    <html>
      <div class="product-label--sold-out">Sold Out</div>
      <span class="price__current">85,000.00 EGP</span>
    </html>
    """
    extractor = CompumartsPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(html, "https://compumarts.com/test")
    assert price == 85000.0
    assert in_stock is False


def test_elbadr_extractor():
    html = """
    <html>
      <div class="product-price-group">
        <span class="price-new">81,500 EGP</span>
      </div>
    </html>
    """
    extractor = ElBadrPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(html, "https://elbadrgroupeg.store/test")
    assert price == 81500.0
    assert in_stock is True


def test_elbadr_extractor_out_of_stock():
    html = """
    <html>
      <script type="application/ld+json">
      {
        "@type": "Product",
        "offers": {
          "price": 81500,
          "availability": "http://schema.org/OutOfStock"
        }
      }
      </script>
      <div class="product-out-of-stock">Out of Stock</div>
    </html>
    """
    extractor = ElBadrPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(html, "https://elbadrgroupeg.store/test")
    assert price == 81500.0
    assert in_stock is False


def test_sigma_extractor_rsc_payload():
    html = r"""
    <html>
      <script>
        self.__next_f.push([1,"3c:[\"$\",\"div\",null,{\"product\":{\"price\":{\"base\":85000,\"current\":92499},\"is_stock\":true}}]\n"])
      </script>
    </html>
    """
    extractor = SigmaPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(html, "https://sigma-computer.com/test")
    assert price == 92499.0
    assert in_stock is True


def test_sigma_extractor_out_of_stock_rsc():
    html = r"""
    <html>
      <script>
        self.__next_f.push([1,"3c:[\"$\",\"div\",null,{\"product\":{\"price\":{\"base\":85000,\"current\":92499},\"is_stock\":false}}]\n"])
      </script>
    </html>
    """
    extractor = SigmaPriceExtractor()
    price, in_stock = extractor.extract_price_and_stock(html, "https://sigma-computer.com/test")
    assert price == 92499.0
    assert in_stock is False


def test_get_price_extractor_factory():
    assert isinstance(get_price_extractor("compumarts"), CompumartsPriceExtractor)
    assert isinstance(get_price_extractor("elbadr"), ElBadrPriceExtractor)
    assert isinstance(get_price_extractor("sigma"), SigmaPriceExtractor)
    assert isinstance(get_price_extractor("unknown_store"), GenericPriceExtractor)


def test_price_monitor_service_mock_batch(monkeypatch):
    import asyncio

    async def _async_test():
        service = PriceMonitorService(default_concurrency=2, request_delay_seconds=0.0)

        class MockResp:
            def __init__(self, status_code, text):
                self.status_code = status_code
                self.text = text

        async def mock_get(url, *args, **kwargs):
            if "drop" in url:
                return MockResp(200, '{"@type":"Product","offers":{"price":70000,"availability":"InStock"}}')
            elif "hike" in url:
                return MockResp(200, '{"@type":"Product","offers":{"price":90000,"availability":"InStock"}}')
            elif "same" in url:
                return MockResp(200, '{"@type":"Product","offers":{"price":80000,"availability":"InStock"}}')
            elif "oos" in url:
                return MockResp(200, '{"@type":"Product","offers":{"price":80000,"availability":"OutOfStock"}}')
            elif "delisted" in url:
                return MockResp(404, "")
            return MockResp(500, "")

        class DummyExtractor:
            def extract_price_and_stock(self, html, url):
                import json

                data = json.loads(html)
                p = float(data["offers"]["price"])
                stock = "InStock" in data["offers"]["availability"]
                return p, stock

        monkeypatch.setattr("app.price_monitor.service.get_price_extractor", lambda k: DummyExtractor())

        from unittest.mock import AsyncMock

        mock_session = AsyncMock()
        mock_session.get = mock_get

        monkeypatch.setattr(
            "app.price_monitor.service.AsyncSession",
            lambda: AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock()),
        )

        batch_req = PriceCheckBatchRequest(
            store_key="compumarts",
            items=[
                PriceCheckItem(
                    offer_id="1",
                    laptop_id="l1",
                    product_url="https://site.com/drop",
                    current_price_egp=80000.0,
                    current_in_stock=True,
                ),
                PriceCheckItem(
                    offer_id="2",
                    laptop_id="l2",
                    product_url="https://site.com/hike",
                    current_price_egp=80000.0,
                    current_in_stock=True,
                ),
                PriceCheckItem(
                    offer_id="3",
                    laptop_id="l3",
                    product_url="https://site.com/same",
                    current_price_egp=80000.0,
                    current_in_stock=True,
                ),
                PriceCheckItem(
                    offer_id="4",
                    laptop_id="l4",
                    product_url="https://site.com/oos",
                    current_price_egp=80000.0,
                    current_in_stock=True,
                ),
                PriceCheckItem(
                    offer_id="5",
                    laptop_id="l5",
                    product_url="https://site.com/delisted",
                    current_price_egp=80000.0,
                    current_in_stock=True,
                ),
            ],
        )

        response = await service.check_batch_async(batch_req)

        assert response.total_items == 5
        assert response.changed_items_count == 4
        assert response.price_drops_count == 1
        assert response.price_hikes_count == 1
        assert response.out_of_stock_count == 2

        res_map = {r.offer_id: r for r in response.results}
        assert res_map["1"].change_type == PriceChangeType.PRICE_DROP
        assert res_map["1"].price_delta_egp == -10000.0
        assert res_map["2"].change_type == PriceChangeType.PRICE_HIKE
        assert res_map["2"].price_delta_egp == 10000.0
        assert res_map["3"].change_type == PriceChangeType.UNCHANGED
        assert res_map["4"].change_type == PriceChangeType.OUT_OF_STOCK
        assert res_map["5"].change_type == PriceChangeType.OUT_OF_STOCK
        assert res_map["5"].new_in_stock is False

    asyncio.run(_async_test())
