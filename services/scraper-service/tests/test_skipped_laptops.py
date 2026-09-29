import pytest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

from app.schemas.laptop import BrandCatalogResult, LaptopSummary, SkippedLaptop, StoreCatalogResult
from app.scrapers.gigabyte import GigabyteBrandScraper
from app.scrapers.asus import AsusBrandScraper
from app.scrapers.lenovo import LenovoBrandScraper
from app.scrapers.hp import HpBrandScraper
from app.stores.amazon import AmazonStoreScraper
from app.stores.btech import BTechStoreScraper
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.elbadr import ElBadrStoreScraper
from app.stores.noon import NoonStoreScraper
from app.stores.sigma import SigmaComputerStoreScraper
from app.stores.twob import TwoBStoreScraper
from app.stores.tradeline import TradelineStoreScraper


def test_skipped_laptop_schema_serialization():
    skipped = SkippedLaptop(
        name="Test Laptop X",
        url="https://example.com/test",
        reason="Specs page not found",
        error="404 Not Found",
        stage="level2_specs",
    )
    brand_result = BrandCatalogResult(
        brand="test_brand",
        official_catalog_url="https://example.com",
        total_laptops=0,
        total_skipped=1,
        skipped_laptops=[skipped],
    )
    dumped = brand_result.model_dump()
    assert dumped["total_skipped"] == 1
    assert len(dumped["skipped_laptops"]) == 1
    assert dumped["skipped_laptops"][0]["name"] == "Test Laptop X"
    assert dumped["skipped_laptops"][0]["reason"] == "Specs page not found"
    assert dumped["skipped_laptops"][0]["stage"] == "level2_specs"

    store_result = StoreCatalogResult(
        store_name="Test Store",
        store_key="test_store",
        store_domain="test.com",
        total_products=0,
        total_skipped=1,
        skipped_laptops=[skipped],
    )
    store_dumped = store_result.model_dump()
    assert store_dumped["total_skipped"] == 1
    assert len(store_dumped["skipped_laptops"]) == 1
    assert store_dumped["skipped_laptops"][0]["name"] == "Test Laptop X"


def test_gigabyte_records_skipped_on_fetch_failure():
    scraper = GigabyteBrandScraper()
    # Mock _fetch_html to return None (simulating 404 or connection timeout)
    scraper._fetch_html = MagicMock(return_value=None)

    summary = LaptopSummary(
        brand="GigaByte",
        name="GIGABYTE GAMING A18 PRO GA8J",
        product_url="https://www.gigabyte.com/Laptop/GIGABYTE-GAMING-A18-PRO-GA8J",
    )
    detail = scraper.get_laptop_detail(summary)
    assert detail is None
    assert len(scraper.skipped_laptops) == 1
    skip = scraper.skipped_laptops[0]
    assert skip.name == "GIGABYTE GAMING A18 PRO GA8J"
    assert "Specs page not found" in skip.reason
    assert skip.stage == "level2_specs"


def test_gigabyte_records_skipped_on_placeholder_no_specs():
    scraper = GigabyteBrandScraper()
    scraper._fetch_html = MagicMock(return_value="<html><body><div>Empty specs</div></body></html>")

    summary = LaptopSummary(
        brand="GigaByte",
        name="Empty Laptop",
        product_url="https://www.gigabyte.com/Laptop/Empty-Laptop",
    )
    detail = scraper.get_laptop_detail(summary)
    assert detail is None
    assert len(scraper.skipped_laptops) == 1
    skip = scraper.skipped_laptops[0]
    assert skip.name == "Empty Laptop"
    assert "No specifications found" in skip.reason


def test_asus_records_skipped_on_zero_configs():
    mock_engine = MagicMock()
    mock_doc = MagicMock()
    mock_doc.markdown.return_value = "Viewing 0 - 0 of 0 products"
    mock_engine.fetch.return_value = mock_doc

    scraper = AsusBrandScraper(engine=mock_engine)
    summary = LaptopSummary(
        brand="ASUS",
        name="ASUS ROG Strix Placeholder",
        product_url="https://www.asus.com/eg-en/store/laptops/placeholder",
    )
    detail = scraper.get_laptop_detail(summary)
    assert detail is None
    assert len(scraper.skipped_laptops) == 1
    assert "0 configurations published" in scraper.skipped_laptops[0].reason


def test_lenovo_records_skipped_on_no_hardware_specs():
    mock_engine = MagicMock()
    mock_doc = MagicMock()
    mock_doc.html = "<html><body><div>Empty Lenovo page</div></body></html>"
    mock_doc.text = "Empty Lenovo page"
    mock_doc.markdown.return_value = "Empty Lenovo page"
    mock_engine.fetch.return_value = mock_doc

    scraper = LenovoBrandScraper(engine=mock_engine)

    summary = LaptopSummary(
        brand="Lenovo",
        name="Lenovo Unreleased Laptop",
        product_url="https://www.lenovo.com/eg/en/laptops/unreleased",
    )
    detail = scraper.get_laptop_detail(summary)
    assert detail is None
    assert len(scraper.skipped_laptops) == 1
    assert "No hardware specs found" in scraper.skipped_laptops[0].reason


def test_hp_records_skipped_on_no_specs():
    scraper = HpBrandScraper()
    scraper._fetch_page = MagicMock(return_value="<html><body><div>Empty PDP</div></body></html>")
    scraper._fetch_specs_page = MagicMock(return_value="<html><body><div>Empty specs</div></body></html>")

    summary = LaptopSummary(
        brand="HP",
        name="HP Unreleased Laptop",
        product_url="https://www.hp.com/products/laptops/unreleased.html",
    )
    detail = scraper.get_laptop_detail(summary)
    assert detail is None
    assert len(scraper.skipped_laptops) == 1
    assert "Could not fetch specs" in scraper.skipped_laptops[0].reason


def test_compumarts_records_skipped_accessory():
    scraper = CompumartsStoreScraper()
    # Card with accessory title
    card_html = """
    <product-card>
      <a class="card-link" href="/products/dell-laptop-backpack-15">Dell Laptop Backpack 15</a>
      <div class="card__title">Dell Laptop Backpack 15</div>
      <div class="price__current"><span class="js-value">1,500.00 EGP</span></div>
    </product-card>
    """
    soup = BeautifulSoup(card_html, "html.parser")
    seen_urls = set()
    product = scraper._parse_card(soup.find("product-card"), seen_urls=seen_urls, level=1)
    assert product is None
    assert len(scraper.skipped_laptops) == 1
    assert scraper.skipped_laptops[0].name == "Dell Laptop Backpack 15"
    assert "Filtered out as standalone accessory" in scraper.skipped_laptops[0].reason


def test_twob_records_skipped_accessory():
    scraper = TwoBStoreScraper()
    scraper._fetch_html = MagicMock()
    # Mock page 1 returning 1 accessory card within 2B DOM wrapper
    page_html = """
    <html>
      <body>
        <div class="products wrapper">
          <ul class="product-items">
            <li class="product-item">
              <div class="product-item-info" data-product-id="12345">
                <a class="product-item-link" href="https://2b.com.eg/en/laptop-backpack.html">
                  HP Laptop Backpack 15.6 inch
                </a>
                <span class="price">1,200.00 EGP</span>
              </div>
            </li>
          </ul>
        </div>
      </body>
    </html>
    """
    scraper._fetch_html.side_effect = [page_html, None]

    products = scraper.scrape_catalog(level=1, max_pages=1)
    assert len(products) == 0
    assert len(scraper.skipped_laptops) == 1
    assert "HP Laptop Backpack 15.6 inch" in scraper.skipped_laptops[0].name
    assert "Filtered out as standalone accessory" in scraper.skipped_laptops[0].reason


def test_tradeline_records_skipped_accessory():
    scraper = TradelineStoreScraper()
    mock_json = {
        "products": [
            {
                "id": 111,
                "title": "Apple Magic Mouse - White",
                "handle": "apple-magic-mouse",
                "variants": [{"id": 1111, "title": "Default Title", "price": "3999.00", "available": True}],
            },
            {
                "id": 222,
                "title": "Apple MacBook Air 13-inch M3",
                "handle": "macbook-air-13-m3",
                "variants": [
                    {"id": 2221, "title": "16GB / 256GB / Midnight", "sku": "MRXV3AB/A", "price": "54000.00", "available": True},
                ],
            },
        ]
    }
    scraper._fetch_json = MagicMock(return_value=mock_json)

    products = scraper.scrape_catalog(level=1, max_pages=1, limit=5)
    assert len(products) == 1
    assert len(scraper.skipped_laptops) >= 1
    skipped_names = [s.name for s in scraper.skipped_laptops]
    assert "Apple Magic Mouse - White" in skipped_names
    assert any("Filtered out non-laptop accessory" in s.reason for s in scraper.skipped_laptops)


def test_amazon_records_skipped_accessory():
    scraper = AmazonStoreScraper()
    mock_html = """
    <html>
      <body>
        <div class="s-main-slot">
          <div class="s-result-item" data-asin="B0DACC111">
            <h2><a href="/dp/B0DACC111"><span>Dell EcoLoop Pro Laptop Backpack 15 inch</span></a></h2>
            <div class="a-price"><span class="a-offscreen">EGP 1,800.00</span></div>
          </div>
          <div class="s-result-item" data-asin="B0DLAP222">
            <h2><a href="/dp/B0DLAP222"><span>Dell Inspiron 3520 Laptop Intel Core i5 8GB 512GB SSD 15.6 FHD</span></a></h2>
            <div class="a-price"><span class="a-offscreen">EGP 22,500.00</span></div>
          </div>
        </div>
      </body>
    </html>
    """
    scraper._fetch_html = MagicMock(return_value=mock_html)

    products = scraper.scrape_catalog(level=1, max_pages=1)
    assert len(products) == 1
    assert len(scraper.skipped_laptops) == 1
    assert "Dell EcoLoop Pro Laptop Backpack" in scraper.skipped_laptops[0].name
    assert "Filtered out non-laptop accessory" in scraper.skipped_laptops[0].reason


def test_noon_records_skipped_accessory():
    scraper = NoonStoreScraper()
    import json
    next_data_json = {
        "props": {
            "pageProps": {
                "catalog": {
                    "hits": [
                        {
                            "name": "Noon East Laptop Sleeve Bag 15.6 Inch",
                            "sku": "N50000000A",
                            "price": 399.00,
                            "url": "/egypt-en/laptop-sleeve/N50000000A/p/",
                        },
                        {
                            "name": "Lenovo V15 G3 IAP Laptop Intel Core i5 8GB 512GB SSD",
                            "sku": "N53381483A",
                            "price": 21999.00,
                            "url": "/egypt-en/lenovo-v15-g3/N53381483A/p/",
                        },
                    ]
                }
            }
        }
    }
    mock_html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data_json)}</script></body></html>'
    scraper._fetch_html = MagicMock(return_value=mock_html)

    products = scraper.scrape_catalog(level=1, max_pages=1)
    assert len(products) == 1
    assert len(scraper.skipped_laptops) == 1
    assert "Noon East Laptop Sleeve" in scraper.skipped_laptops[0].name
    assert "Filtered out non-laptop accessory" in scraper.skipped_laptops[0].reason


def test_btech_records_skipped_accessory():
    scraper = BTechStoreScraper()
    mock_html = """
    <html>
      <body>
        <div class="products wrapper grid products-grid">
          <ol class="products list items product-items">
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="7001">
                <a class="product-item-link" href="https://btech.com/en/hp-65w-smart-ac-adapter.html">
                  HP 65W Smart AC Adapter Charger
                </a>
                <span class="price">EGP 1,200</span>
              </div>
            </li>
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="7002">
                <a class="product-item-link" href="https://btech.com/en/hp-pavilion-14.html">
                  HP Pavilion x360 Convertible 14-ek1009ne Laptop Intel Core i5 8GB 512GB
                </a>
                <span class="price">EGP 36,999</span>
              </div>
            </li>
          </ol>
        </div>
      </body>
    </html>
    """
    scraper._fetch_html = MagicMock(return_value=mock_html)

    products = scraper.scrape_catalog(level=1, max_pages=1)
    assert len(products) == 1
    assert len(scraper.skipped_laptops) == 1
    assert "HP 65W Smart AC Adapter Charger" in scraper.skipped_laptops[0].name
    assert "Filtered out non-laptop accessory" in scraper.skipped_laptops[0].reason


