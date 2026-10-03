import pytest
from app.scrapers.hp import HpDateExtractor, clean_spec_text, HpBrandScraper
from app.schemas.laptop import LaptopSummary


def test_clean_spec_text():
    raw = "AMD Ryzen™ AI 9 HX 375 * * ( * ) \xa0  5.1 GHz  "
    cleaned = clean_spec_text(raw)
    assert "*" not in cleaned
    assert "\xa0" not in cleaned
    assert "AMD Ryzen™ AI 9 HX 375 5.1 GHz" in cleaned


def test_hp_date_extractor_hardware():
    # Test RTX 5080 -> 2025
    dt, yr = HpDateExtractor.extract("OMEN MAX Gaming Laptop 16", "Discrete, NVIDIA GeForce RTX 5080 Laptop GPU")
    assert yr == 2025
    assert dt == "2025-01-01"

    # Test Ryzen AI 9 -> 2024
    dt, yr = HpDateExtractor.extract("OMEN MAX 16", "AMD Ryzen AI 9 HX 375")
    assert yr == 2024
    assert dt == "2024-07-01"

    # Test Lunar Lake Intel Ultra 7 258V -> 2024
    dt, yr = HpDateExtractor.extract("HP OmniBook Ultra Flip", "Intel Core Ultra 7 258V")
    assert yr == 2024
    assert dt == "2024-09-01"

    # Test Snapdragon X Elite -> 2024
    dt, yr = HpDateExtractor.extract("HP OmniBook X 14", "Snapdragon X Elite X1E-78-100")
    assert yr == 2024
    assert dt == "2024-06-01"

    # Test 13th Gen -> 2023
    dt, yr = HpDateExtractor.extract("HP Victus 15", "Intel Core i5-13500H")
    assert yr == 2023
    assert dt == "2023-01-01"


def test_hp_date_extractor_model_gens():
    # EliteBook G2i -> 2025
    dt, yr = HpDateExtractor.extract("HP EliteBook X Flip G2i 14 inch")
    assert yr == 2025

    # EliteBook G1i -> 2024
    dt, yr = HpDateExtractor.extract("HP EliteBook X Flip G1i 14 inch")
    assert yr == 2024

    # OmniBook -> 2024
    dt, yr = HpDateExtractor.extract("HP OmniBook 5 Flip 2-in-1 Laptop")
    assert yr == 2024


def test_hp_brand_scraper_family():
    scraper = HpBrandScraper()
    assert scraper._determine_family("HP OmniBook 5 Flip 2-in-1", "/products/laptops/...") == "OmniBook"
    assert scraper._determine_family("OMEN MAX Gaming Laptop 16", "/products/laptops/...") == "OMEN"
    assert scraper._determine_family("Victus Gaming Laptop 15", "/products/laptops/...") == "Victus"
    assert scraper._determine_family("HP EliteBook X Flip G1i", "/products/laptops/...") == "EliteBook"
    assert scraper._determine_family("HP ProBook 450 G10", "/products/laptops/...") == "ProBook"
    assert scraper._determine_family("HP Laptop 15-fd0279ne", "/products/laptops/...") == "HP Essential"


def test_hp_watermark_matching():
    scraper = HpBrandScraper()
    assert scraper._matches_watermark("Victus Gaming Laptop 15-fa2005ne (B85M8EA)", "15-fa2005ne") is True
    assert scraper._matches_watermark("Victus Gaming Laptop 15-fa2005ne (B85M8EA)", "B85M8EA") is True
    assert scraper._matches_watermark("OMEN MAX Gaming Laptop 16", "Victus") is False


def test_hp_get_laptop_summaries_unlimited(monkeypatch):
    scraper = HpBrandScraper()
    mock_html = """
    <html>
      <body>
        <api-products data-is-last="true"></api-products>
        <script type="text/product-tile">
          <hppc-product-tile data-product-id="hp-1" data-sku="SKU1">
            <a href="/products/laptops/omen-16.html" data-gtm-value="HP OMEN Gaming Laptop 16"></a>
          </hppc-product-tile>
        </script>
      </body>
    </html>
    """

    class MockResponse:
        status_code = 200
        text = mock_html

    monkeypatch.setattr(scraper._session, "get", lambda url, **kwargs: MockResponse())
    # Calling with max_pages=None (unlimited) must stop naturally at is_last
    summaries = scraper.get_laptop_summaries(max_pages=None)
    assert len(summaries) == 1
    assert summaries[0].name == "HP OMEN Gaming Laptop 16"
    assert summaries[0].family == "OMEN"


def test_hp_get_laptop_summaries_watermark_limit_and_errors(monkeypatch):
    scraper = HpBrandScraper()
    mock_html = """
    <html>
      <body>
        <api-products data-is-last="false"></api-products>
        <script type="text/product-tile">
          <hppc-product-tile data-product-id="hp-1" data-sku="SKU1">
            <a href="/products/laptops/omen-16.html" data-gtm-value="HP OMEN Gaming Laptop 16 (SKU1)"></a>
          </hppc-product-tile>
        </script>
        <script type="text/product-tile">
          <hppc-product-tile data-product-id="hp-2" data-sku="SKU2">
            <a href="/products/laptops/victus-15.html" data-gtm-value="HP Victus 15 (SKU2)"></a>
          </hppc-product-tile>
        </script>
      </body>
    </html>
    """

    class MockResponse:
        status_code = 200
        text = mock_html

    # Test Watermark stopping at SKU2: only SKU1 should be captured
    monkeypatch.setattr(scraper._session, "get", lambda url, **kwargs: MockResponse())
    summaries = scraper.get_laptop_summaries(until_model="SKU2")
    assert len(summaries) == 1
    assert summaries[0].name == "HP OMEN Gaming Laptop 16 (SKU1)"

    # Test Limit ceiling
    summaries_lim = scraper.get_laptop_summaries(limit=1)
    assert len(summaries_lim) == 1

    # Test Error status_code != 200
    class BadResponse:
        status_code = 500
        text = "Server error"

    monkeypatch.setattr(scraper._session, "get", lambda url, **kwargs: BadResponse())
    assert scraper.get_laptop_summaries() == []

    # Test Exception raised
    def raise_err(*args, **kwargs):
        raise RuntimeError("Network disconnect")

    monkeypatch.setattr(scraper._session, "get", raise_err)
    assert scraper.get_laptop_summaries() == []


def test_hp_fetch_page_engine_and_session():
    from unittest.mock import MagicMock
    engine = MagicMock()
    doc = MagicMock()
    doc.html = "<html>" + "a" * 600 + "</html>"
    engine.fetch.return_value = doc

    scraper = HpBrandScraper(engine=engine)
    assert scraper._fetch_page("https://hp.com/p") == doc.html

    # Fallback to session when engine fails
    engine.fetch.side_effect = RuntimeError("Engine crash")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html>session fallback</html>"
    scraper._session.get = MagicMock(return_value=mock_resp)
    assert scraper._fetch_page("https://hp.com/p") == "<html>session fallback</html>"


def test_hp_get_laptop_detail_missing_specs_records_skipped():
    scraper = HpBrandScraper()
    scraper._fetch_page = lambda url: "<html><body>No specs here</body></html>"

    summary = LaptopSummary(
        brand="HP",
        name="Empty HP Laptop",
        product_url="https://hp.com/p",
        specs_url="https://hp.com/p/specs",
    )
    detail = scraper.get_laptop_detail(summary)
    assert detail is None
    assert len(scraper.skipped_laptops) == 1
    assert "Could not fetch specs" in scraper.skipped_laptops[0].reason


def test_hp_get_laptop_detail_and_display_parsing_success():
    scraper = HpBrandScraper()

    pdp_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@type": "Product",
          "sku": "B85M8EA",
          "releaseDate": "2024-05-20",
          "image": ["https://hp.com/omen1.jpg", "https://hp.com/omen2.jpg"],
          "description": "High performance gaming laptop with OMEN Tempest Cooling."
        }
        </script>
      </head>
      <body>
        <div class="c-product-details__short-specs">Short preview</div>
      </body>
    </html>
    """

    specs_html = """
    <html>
      <body>
        <table class="c-product-all-details-table__table">
          <tr><th>Processor</th><td>AMD Ryzen 7 8845HS</td></tr>
          <tr><th>Graphics</th><td>NVIDIA GeForce RTX 4070 Laptop GPU (8 GB)</td></tr>
          <tr><th>Memory</th><td>32 GB DDR5-5600 MHz RAM</td></tr>
          <tr><th>Internal Storage</th><td>1 TB PCIe Gen4 NVMe M.2 SSD</td></tr>
          <tr><th>Display</th><td>16.1 inch diagonal, QHD (2560 x 1440), 240 Hz, OLED, 300 nits</td></tr>
          <tr><th>Product Color</th><td>Shadow black aluminum</td></tr>
          <tr><th>Operating System</th><td>Windows 11 Home</td></tr>
          <tr><th>Battery Type</th><td>6-cell, 83 Wh Li-ion polymer</td></tr>
          <tr><th>Weight</th><td>2.39 kg</td></tr>
          <tr><th>Dimensions (W x D x H)</th><td>36.9 x 25.94 x 2.35 cm</td></tr>
        </table>
      </body>
    </html>
    """

    def fake_fetch(url):
        if "specs" in url:
            return specs_html
        return pdp_html

    scraper._fetch_page = fake_fetch

    summary = LaptopSummary(
        brand="HP",
        name="OMEN Gaming Laptop 16-xf0000ne",
        model="16-xf0000ne",
        family="OMEN",
        product_url="https://hp.com/products/omen-16/12345",
        specs_url="https://hp.com/products/omen-16/specs/12345",
    )

    detail = scraper.get_laptop_detail(summary)
    assert detail is not None
    assert detail.brand == "HP"
    assert detail.sku_part_number == "B85M8EA"
    assert detail.release_date == "2024-05-20"
    assert detail.release_year == 2024
    assert len(detail.gallery_images) == 2
    assert "https://hp.com/omen1.jpg" in detail.gallery_images
    assert "Shadow black aluminum" in detail.colors
    assert detail.structured_specs["processor"] == "AMD Ryzen 7 8845HS"
    assert detail.structured_specs["gpu"] == "NVIDIA GeForce RTX 4070 Laptop GPU (8 GB)"
    assert detail.structured_specs["ram"] == "32 GB DDR5-5600 MHz RAM"
    assert detail.structured_specs["storage"] == "1 TB PCIe Gen4 NVMe M.2 SSD"
    assert detail.structured_specs["display_size"] == '16.1"'
    assert "QHD" in detail.structured_specs["resolution"]
    assert detail.structured_specs["refresh_rate"] == "240 Hz"
    assert detail.structured_specs["panel_type"] == "OLED"

    # Configurations check
    assert len(detail.configurations) == 1
    cfg = detail.configurations[0]
    assert cfg.model == "16-xf0000ne"
    assert cfg.mpn == "B85M8EA"
    assert cfg.official_specs["Processor"] == "AMD Ryzen 7 8845HS"
    assert cfg.official_specs["Graphics"] == "NVIDIA GeForce RTX 4070 Laptop GPU (8 GB)"
