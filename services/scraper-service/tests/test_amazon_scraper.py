import pytest
from bs4 import BeautifulSoup

from app.stores.amazon import AmazonStoreScraper
from app.schemas.laptop import RetailerProduct


def test_amazon_properties():
    scraper = AmazonStoreScraper()
    assert scraper.store_name == "Amazon Egypt"
    assert scraper.store_key == "amazon"
    assert scraper.base_url == "https://www.amazon.eg"
    assert scraper.base_domain == "amazon.eg"


def test_amazon_parse_price():
    scraper = AmazonStoreScraper()
    val, formatted = scraper.parse_egp_price("EGP 45,999.00")
    assert val == 45999.0
    assert formatted == "45,999.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("32,500 EGP")
    assert val2 == 32500.0
    assert formatted2 == "32,500.00 EGP"


def test_amazon_accessory_filtering():
    scraper = AmazonStoreScraper()
    # Standalone accessories must be detected
    for title in [
        "Dell EcoLoop Pro Backpack 15 - CP5723",
        "HP 65W Smart AC Adapter Charger for Laptops",
        "Logitech MX Master 3S Wireless Mouse",
        "Cooling Pad for Laptops 15.6 inch RGB",
    ]:
        assert scraper._is_standalone_accessory(title) is True

    # Real laptops must NOT be filtered
    for laptop in [
        "Lenovo IdeaPad Slim 3 Laptop - Intel Core i5-12450H - 8GB RAM - 512GB SSD - 15.6 inch FHD",
        "ASUS TUF Gaming F15 FX507ZC4-HN002W Laptop - Intel Core i7-12700H - 16GB RAM - RTX 3050",
        "Apple MacBook Air 13-inch M3 chip 16GB RAM 256GB SSD",
    ]:
        assert scraper._is_standalone_accessory(laptop) is False


def test_amazon_watermark_matching():
    scraper = AmazonStoreScraper()
    assert scraper._matches_watermark("Lenovo IdeaPad Slim 3 B0D1234567", "B0D1234567") is True
    assert scraper._matches_watermark("ASUS TUF Gaming FX507ZC4", "FX507ZC4") is True
    assert scraper._matches_watermark("HP Pavilion", "B0D1234567") is False


def test_amazon_mock_pdp_specs(monkeypatch):
    scraper = AmazonStoreScraper()
    mock_pdp_html = """
    <html>
      <head><title>Lenovo IdeaPad Slim 3</title></head>
      <body>
        <div id="availability"><span>In Stock</span></div>
        <div id="corePrice_feature_div"><span class="a-offscreen">EGP 24,999.00</span></div>
        <table id="productDetails_techSpec_section_1">
          <tr><th>Item model number</th><td>82RK00EUEG</td></tr>
          <tr><th>Model Name</th><td>IdeaPad Slim 3 15IAH8</td></tr>
          <tr><th>Processor Brand</th><td>Intel</td></tr>
          <tr><th>Processor Type</th><td>Core i5-12450H</td></tr>
          <tr><th>RAM Size</th><td>8 GB</td></tr>
          <tr><th>Hard Drive Size</th><td>512 GB</td></tr>
          <tr><th>Graphics Coprocessor</th><td>Intel UHD Graphics</td></tr>
          <tr><th>Operating System</th><td>Windows 11 Home</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_pdp_html)
    specs, raw_desc, mpn, model_code, p_val, p_str, in_stock = scraper._extract_product_specs(
        "https://www.amazon.eg/dp/B0D1234567"
    )

    assert mpn == "82RK00EUEG"
    assert model_code == "IdeaPad Slim 3 15IAH8"
    assert p_val == 24999.0
    assert in_stock is True
    assert specs.get("RAM Size") == "8 GB"
    assert specs.get("Hard Drive Size") == "512 GB"
    assert specs.get("Operating System") == "Windows 11 Home"


def test_amazon_catalog_watermark_stop(monkeypatch):
    scraper = AmazonStoreScraper()
    mock_catalog_html = """
    <html>
      <body>
        <div class="s-main-slot">
          <div class="s-result-item" data-asin="B0DNEWEST">
            <h2><a href="/dp/B0DNEWEST"><span>HP Victus 15-fa1093ne Gaming Laptop Intel Core i7-13620H 16GB 512GB RTX 4050</span></a></h2>
            <div class="a-price"><span class="a-offscreen">EGP 48,999.00</span></div>
          </div>
          <div class="s-result-item" data-asin="B0DWATERMARK">
            <h2><a href="/dp/B0DWATERMARK"><span>Lenovo LOQ 15IRX9 Watermark Target B0DWATERMARK Laptop</span></a></h2>
            <div class="a-price"><span class="a-offscreen">EGP 42,999.00</span></div>
          </div>
          <div class="s-result-item" data-asin="B0DOLDER">
            <h2><a href="/dp/B0DOLDER"><span>Dell Inspiron 3520 Laptop Intel Core i3 8GB 256GB SSD</span></a></h2>
            <div class="a-price"><span class="a-offscreen">EGP 18,500.00</span></div>
          </div>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_catalog_html)

    products = scraper.scrape_catalog(level=1, until_model="B0DWATERMARK", max_pages=1)
    assert len(products) == 1
    assert products[0].retailer_sku == "B0DNEWEST"
    assert products[0].price_egp == 48999.0


def test_amazon_search_candidates(monkeypatch):
    scraper = AmazonStoreScraper()
    mock_search_html = """
    <html>
      <body>
        <div class="s-result-item" data-asin="B0DSEARCH1">
          <h2><a href="/dp/B0DSEARCH1"><span>ASUS TUF Gaming F15 FX507ZC4-HN002W Laptop Intel Core i7 16GB 512GB RTX 3050</span></a></h2>
          <div class="a-price"><span class="a-offscreen">EGP 38,500.00</span></div>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_search_html)
    monkeypatch.setattr(
        scraper,
        "_extract_product_specs",
        lambda url: (
            {"Processor Type": "Intel Core i7-12700H", "Item model number": "FX507ZC4-HN002W"},
            "ASUS TUF Gaming",
            "FX507ZC4-HN002W",
            "FX507ZC4",
            38500.0,
            "38,500.00 EGP",
            True,
        ),
    )

    candidates = scraper.search_candidates("TUF Gaming", limit=5)
    assert len(candidates) == 1
    assert "ASUS TUF" in candidates[0].title
    assert candidates[0].retailer_sku == "B0DSEARCH1"
    assert candidates[0].price_egp == 38500.0
    assert candidates[0].mpn == "FX507ZC4-HN002W"
