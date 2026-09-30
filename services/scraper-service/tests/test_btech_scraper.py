import pytest
from bs4 import BeautifulSoup

from app.stores.btech import BTechStoreScraper
from app.schemas.laptop import RetailerProduct


def test_btech_properties():
    scraper = BTechStoreScraper()
    assert scraper.store_name == "B.TECH"
    assert scraper.store_key == "btech"
    assert scraper.base_url == "https://btech.com"
    assert scraper.base_domain == "btech.com"


def test_btech_parse_price():
    scraper = BTechStoreScraper()
    val, formatted = scraper.parse_egp_price("EGP 34,999")
    assert val == 34999.0
    assert formatted == "34,999.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("51,200.00 EGP")
    assert val2 == 51200.0
    assert formatted2 == "51,200.00 EGP"


def test_btech_accessory_filtering():
    scraper = BTechStoreScraper()
    for title in [
        "L'AVVENTO Laptop Bag 15.6 inch Anti-Theft",
        "HP 65W Smart AC Adapter Laptop Charger",
        "Logitech Wireless Mouse M185",
        "Cooling Pad for Gaming Laptop",
    ]:
        assert scraper._is_standalone_accessory(title) is True

    for laptop in [
        "HP Pavilion x360 Convertible 14-ek1009ne Laptop Intel Core i5 8GB 512GB SSD",
        "Lenovo Legion 5 15IAH7H Laptop Intel Core i7 16GB RAM 512GB SSD RTX 3060",
        "Dell Inspiron 3520 Laptop Intel Core i5-1235U 8GB 512GB SSD 15.6 FHD",
    ]:
        assert scraper._is_standalone_accessory(laptop) is False


def test_btech_watermark_matching():
    scraper = BTechStoreScraper()
    assert scraper._matches_watermark("HP Pavilion x360 14-ek1009ne", "14-ek1009ne") is True
    assert scraper._matches_watermark("Lenovo Legion 15IAH7H", "15IAH7H") is True
    assert scraper._matches_watermark("Dell Inspiron 3520", "14-ek1009ne") is False


def test_btech_mock_pdp_specs(monkeypatch):
    scraper = BTechStoreScraper()
    mock_pdp_html = """
    <html>
      <head><title>HP Pavilion x360 14-ek1009ne</title></head>
      <body>
        <div class="stock available"><span>In stock</span></div>
        <div class="price-box"><span class="price">EGP 36,999</span></div>
        <table id="product-attribute-specs-table">
          <tr><th>Brand</th><td>HP</td></tr>
          <tr><th>Model Name</th><td>14-ek1009ne</td></tr>
          <tr><th>MPN</th><td>7Z744EA</td></tr>
          <tr><th>Processor Information</th><td>Intel Core i5-1335U</td></tr>
          <tr><th>RAM Information</th><td>8GB DDR4</td></tr>
          <tr><th>Storage</th><td>512GB PCIe NVMe SSD</td></tr>
          <tr><th>Display Type</th><td>14 inch FHD Touchscreen</td></tr>
          <tr><th>Operating System</th><td>Windows 11 Home</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_pdp_html)
    specs, raw_desc, mpn, model_code, p_val, p_str, in_stock = scraper._extract_product_specs(
        "https://btech.com/en/hp-pavilion-x360-14-ek1009ne.html"
    )

    assert mpn == "7Z744EA"
    assert model_code == "14-ek1009ne"
    assert p_val == 36999.0
    assert in_stock is True
    assert specs.get("Processor Information") == "Intel Core i5-1335U"
    assert specs.get("RAM Information") == "8GB DDR4"
    assert specs.get("Operating System") == "Windows 11 Home"


def test_btech_catalog_watermark_stop(monkeypatch):
    scraper = BTechStoreScraper()
    mock_catalog_html = """
    <html>
      <body>
        <div class="products wrapper grid products-grid">
          <ol class="products list items product-items">
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="9001">
                <a class="product-item-link" href="https://btech.com/en/hp-victus-15-fa1093ne.html">
                  HP Victus 15-fa1093ne Gaming Laptop Intel Core i7 16GB 512GB RTX 4050
                </a>
                <span class="price">EGP 49,999</span>
              </div>
            </li>
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="9002">
                <a class="product-item-link" href="https://btech.com/en/lenovo-loq-15irx9-watermark.html">
                  Lenovo LOQ 15IRX9 Watermark Target 83DV009GED Laptop
                </a>
                <span class="price">EGP 44,500</span>
              </div>
            </li>
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="9003">
                <a class="product-item-link" href="https://btech.com/en/dell-inspiron-3520.html">
                  Dell Inspiron 3520 Older Laptop
                </a>
                <span class="price">EGP 19,200</span>
              </div>
            </li>
          </ol>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_catalog_html)

    products = scraper.scrape_catalog(level=1, until_model="83DV009GED", max_pages=1)
    assert len(products) == 1
    assert "HP Victus" in products[0].title
    assert products[0].retailer_product_id == "9001"
    assert products[0].price_egp == 49999.0


def test_btech_search_candidates(monkeypatch):
    scraper = BTechStoreScraper()
    mock_search_html = """
    <html>
      <body>
        <div class="products wrapper grid products-grid">
          <ol class="products list items product-items">
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="9500">
                <a class="product-item-link" href="https://btech.com/en/lenovo-legion-5.html">
                  Lenovo Legion 5 15IAH7H Laptop Intel Core i7 16GB 512GB RTX 3060
                </a>
                <span class="price">EGP 58,000</span>
              </div>
            </li>
          </ol>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_search_html)
    monkeypatch.setattr(
        scraper,
        "_extract_product_specs",
        lambda url: (
            {"Processor Information": "Intel Core i7-12700H", "MPN": "82RB00EUEG"},
            "Lenovo Legion Gaming Laptop",
            "82RB00EUEG",
            "Legion 5 15IAH7H",
            58000.0,
            "58,000.00 EGP",
            True,
        ),
    )

    candidates = scraper.search_candidates("Legion", limit=5)
    assert len(candidates) == 1
    assert "Lenovo Legion" in candidates[0].title
    assert candidates[0].retailer_product_id == "9500"
    assert candidates[0].price_egp == 58000.0
    assert candidates[0].mpn == "82RB00EUEG"
