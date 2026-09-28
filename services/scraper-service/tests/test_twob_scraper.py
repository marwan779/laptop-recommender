import pytest
from bs4 import BeautifulSoup

from app.stores.twob import TwoBStoreScraper
from app.schemas.laptop import RetailerProduct


def test_twob_properties():
    scraper = TwoBStoreScraper()
    assert scraper.store_name == "2B"
    assert scraper.store_key == "twob"
    assert scraper.base_url == "https://2b.com.eg"
    assert scraper.base_domain == "2b.com.eg"


def test_twob_parse_price():
    scraper = TwoBStoreScraper()
    val, formatted = scraper.parse_egp_price("EGP 80,849")
    assert val == 80849.0
    assert formatted == "80,849.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("109,499.00 EGP")
    assert val2 == 109499.0
    assert formatted2 == "109,499.00 EGP"


def test_twob_watermark_matching():
    scraper = TwoBStoreScraper()
    assert scraper._matches_watermark("HP OmniBook 5 Flip 14-km0007ne Laptop", "14-km0007ne") is True
    assert scraper._matches_watermark("ASUS Vivobook 15 M1502NAQ-BQ855W", "M1502NAQ") is True
    assert scraper._matches_watermark("Apple MacBook Neo MHFE4", "MHFE4") is True
    assert scraper._matches_watermark("Lenovo ThinkPad E16", "FA506NCG") is False
    assert scraper._matches_watermark(None, "14-km0007ne") is False
    assert scraper._matches_watermark("HP OmniBook", None) is False


def test_twob_accessory_filtering():
    scraper = TwoBStoreScraper()
    # Standalone accessories must be detected
    for kw in [
        "L'AVVENTO (BG937) Business & Travel Backpack Anti-Theft Back",
        "E-train (BG53U) Backpack Bag Up to 15.6 - Purple",
        "HP 65W Smart AC Adapter Charger",
        "Redragon Wireless Gaming Mouse",
    ]:
        assert scraper._is_standalone_accessory(kw) is True

    # Real laptops (including bundles or keyboard layout) must NOT be filtered
    laptop1 = "HP OmniBook 5 Flip 14-km0007ne Laptop - Intel Core Ultra 5-322 - 16GB - 512GB SSD - Win11 + HP Smart Tank 581 All-in-One (4A8D4A)"
    assert scraper._is_standalone_accessory(laptop1) is False

    laptop2 = "ASUS ROG Strix SCAR 18 G835LX-AI464W Laptop - Intel Core Ultra 9-275HX - 64GB - 4TB SSD - RTX 5090 24GB - 18 2.5K Mini LED 240Hz"
    assert scraper._is_standalone_accessory(laptop2) is False

    laptop3 = "Lenovo LOQ 15IRX9 Laptop - Intel Core i7-13650HX - 16GB DDR5 - RTX 4060 - Keyboard English"
    assert scraper._is_standalone_accessory(laptop3) is False


def test_twob_mock_pdp_specs(monkeypatch):
    scraper = TwoBStoreScraper()
    mock_pdp_html = """
    <html>
      <head><title>HP OmniBook 5 Flip</title></head>
      <body>
        <div class="product-info-price">
          <div class="price-box">
            <span class="price">EGP 83,499</span>
          </div>
        </div>
        <div class="stock available"><span>In stock</span></div>
        <table id="product-attribute-specs-table">
          <tr><th>Brand</th><td>HP</td></tr>
          <tr><th>Model</th><td>HP OmniBook 5 Flip 14-km0007ne</td></tr>
          <tr><th>MPN</th><td>4A8D4A</td></tr>
          <tr><th>Part Number</th><td>4A8D4A</td></tr>
          <tr><th>Processor Information</th><td>Intel Core Ultra 5-322 up to 4.4GHz</td></tr>
          <tr><th>RAM Information</th><td>16GB LPDDR5x</td></tr>
          <tr><th>Hard Disk Type</th><td>512GB PCIe NVMe SSD</td></tr>
          <tr><th>Graphics Card Details</th><td>Intel Graphics</td></tr>
          <tr><th>Display Type</th><td>14" 2K (1920 x 1200) Touch</td></tr>
          <tr><th>Operating System</th><td>Windows 11</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_pdp_html)
    specs, raw_desc, mpn, model_code, p_val, p_str, in_stock = scraper._extract_product_specs(
        "https://2b.com.eg/en/hp-omnibook-test.html"
    )

    assert mpn == "4A8D4A"
    assert model_code == "HP OmniBook 5 Flip 14-km0007ne"
    assert p_val == 83499.0
    assert in_stock is True
    assert specs.get("Processor Information") == "Intel Core Ultra 5-322 up to 4.4GHz"
    assert specs.get("RAM Information") == "16GB LPDDR5x"
    assert specs.get("Hard Disk Type") == "512GB PCIe NVMe SSD"
    assert specs.get("Operating System") == "Windows 11"


def test_twob_catalog_watermark_stop(monkeypatch):
    scraper = TwoBStoreScraper()
    mock_catalog_html = """
    <html>
      <body>
        <div class="products wrapper grid products-grid">
          <ol class="products list items product-items">
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="101">
                <a class="product-item-link" href="https://2b.com.eg/en/laptop-newest.html">
                  Apple MacBook Neo - A18 Pro - 8GB - 512GB SSD
                </a>
                <span class="price">EGP 80,849</span>
              </div>
            </li>
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="102">
                <a class="product-item-link" href="https://2b.com.eg/en/laptop-watermark.html">
                  HP OmniBook 5 Flip 14-km0007ne Laptop Watermark Stop
                </a>
                <span class="price">EGP 83,499</span>
              </div>
            </li>
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="103">
                <a class="product-item-link" href="https://2b.com.eg/en/laptop-older.html">
                  ASUS Vivobook 15 M1502NAQ Older
                </a>
                <span class="price">EGP 41,999</span>
              </div>
            </li>
          </ol>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_catalog_html)

    # Crawl with watermark stopping at 14-km0007ne
    products = scraper.scrape_catalog(level=1, until_model="14-km0007ne", max_pages=1)
    assert len(products) == 1
    assert "Apple MacBook Neo" in products[0].title
    assert products[0].price_egp == 80849.0
    assert products[0].product_url == "https://2b.com.eg/en/laptop-newest.html"


def test_twob_search_candidates(monkeypatch):
    scraper = TwoBStoreScraper()
    mock_search_html = """
    <html>
      <body>
        <div class="products wrapper grid products-grid">
          <ol class="products list items product-items">
            <li class="item product product-item">
              <div class="product-item-info" data-product-id="201">
                <a class="product-item-link" href="https://2b.com.eg/en/lenovo-loq-15irx9.html">
                  Lenovo LOQ 15IRX9 Laptop - Intel Core i7-13650HX - 16GB - 512GB SSD - RTX 3050 6GB
                </a>
                <span class="price">EGP 84,949</span>
              </div>
            </li>
          </ol>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_search_html)
    # Mock PDP fetch for search enrichment
    monkeypatch.setattr(
        scraper,
        "_extract_product_specs",
        lambda url: (
            {"Processor Information": "Intel Core i7-13650HX", "MPN": "83DV009GED"},
            "Lenovo LOQ Gaming Laptop",
            "83DV009GED",
            "Lenovo LOQ 15IRX9",
            84949.0,
            "84,949.00 EGP",
            True,
        ),
    )

    candidates = scraper.search_candidates("LOQ", limit=5)
    assert len(candidates) == 1
    assert "Lenovo LOQ" in candidates[0].title
    assert candidates[0].price_egp == 84949.0
    assert candidates[0].mpn == "83DV009GED"
    assert candidates[0].in_stock is True
