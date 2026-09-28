import pytest
from bs4 import BeautifulSoup

from app.stores.elbadr import ElBadrStoreScraper
from app.schemas.laptop import RetailerProduct


def test_elbadr_properties():
    scraper = ElBadrStoreScraper()
    assert scraper.store_name == "El Badr Group"
    assert scraper.store_key == "elbadr"
    assert scraper.base_url == "https://elbadrgroupeg.store"
    assert scraper.base_domain == "elbadrgroupeg.store"


def test_elbadr_parse_price():
    scraper = ElBadrStoreScraper()
    val, formatted = scraper.parse_egp_price("43,000 EGP")
    assert val == 43000.0
    assert formatted == "43,000.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("57,499.00 EGP")
    assert val2 == 57499.0
    assert formatted2 == "57,499.00 EGP"


def test_elbadr_watermark_matching():
    scraper = ElBadrStoreScraper()
    assert scraper._matches_watermark("ASUS TUF Gaming A15 FA506NCG-HN857W", "FA506NCG-HN857W") is True
    assert scraper._matches_watermark("90NR0JF7-M00TP0", "90NR0JF7-M00TP0") is True
    assert scraper._matches_watermark("Lenovo LOQ 15IRX9", "83DV01HSED") is False
    assert scraper._matches_watermark(None, "FA506NCG") is False
    assert scraper._matches_watermark("ASUS TUF", None) is False


def test_elbadr_accessory_filtering():
    scraper = ElBadrStoreScraper()
    # Standalone accessories must be detected
    for kw in ["Lenovo Legion Backpack 16", "HP 65W AC Adapter Charger", "Redragon Gaming Mouse"]:
        assert scraper._is_standalone_accessory(kw) is True

    # A real laptop mentioning keyboard layout must NOT be filtered
    laptop_title = "ASUS TUF Gaming A15 FA506NCG-HN857W Laptop – Ryzen 7 8845HS, RTX 3050, 144Hz FHD - Keyboard English"
    assert scraper._is_standalone_accessory(laptop_title) is False


def test_elbadr_mock_pdp_specs(monkeypatch):
    scraper = ElBadrStoreScraper()
    mock_pdp_html = """
    <html>
      <head><title>ASUS TUF A15</title></head>
      <body>
        <ul class="product-stats">
          <li>Stock: In Stock</li>
          <li>Model: A15FA506NCG-HN857W</li>
          <li>MPN: 90NR0JF7-M00TP0</li>
        </ul>
        <div class="product-price-group">
          <div class="product-price">43,000 EGP</div>
        </div>
        <div class="product_blocks-default">
          <div class="block-content">
            Processor (CPU): AMD Ryzen 7 8845HS
            Discrete Graphics (GPU): NVIDIA GeForce RTX 3050 Laptop GPU
            RAM: 16GB DDR5
            Storage: 512GB PCIe 4.0 NVMe SSD
            Screen Size: 15.6 inches
            Refresh Rate: 144Hz
          </div>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_pdp_html)
    specs, raw_desc, mpn, model_code, p_val, p_str = scraper._extract_product_specs(
        "https://elbadrgroupeg.store/asus-tuf-test"
    )

    assert mpn == "90NR0JF7-M00TP0"
    assert model_code == "A15FA506NCG-HN857W"
    assert p_val == 43000.0
    assert specs.get("Processor (CPU)") == "AMD Ryzen 7 8845HS"
    assert specs.get("RAM") == "16GB DDR5"
    assert specs.get("Refresh Rate") == "144Hz"


def test_elbadr_catalog_watermark_stop(monkeypatch):
    scraper = ElBadrStoreScraper()
    mock_catalog_html = """
    <html>
      <body>
        <div class="main-products">
          <div class="product-layout">
            <div class="name">
              <a href="https://elbadrgroupeg.store/laptop-1">Laptop One RTX 4060</a>
            </div>
            <div class="price">50,000 EGP</div>
          </div>
          <div class="product-layout">
            <div class="name">
              <a href="https://elbadrgroupeg.store/laptop-watermark">Laptop Stop Watermark Model</a>
            </div>
            <div class="price">45,000 EGP</div>
          </div>
          <div class="product-layout">
            <div class="name">
              <a href="https://elbadrgroupeg.store/laptop-3">Laptop Three</a>
            </div>
            <div class="price">40,000 EGP</div>
          </div>
        </div>
        <div class="results">Showing 1 to 3 of 3</div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_catalog_html)

    # Crawl with watermark stopping at laptop-watermark
    products = scraper.scrape_catalog(level=1, until_model="watermark", max_pages=1)
    assert len(products) == 1
    assert products[0].title == "Laptop One RTX 4060"
    assert products[0].price_egp == 50000.0


def test_elbadr_search_candidates(monkeypatch):
    scraper = ElBadrStoreScraper()
    mock_search_html = """
    <html>
      <body>
        <div class="main-products">
          <div class="product-layout">
            <div class="name">
              <a href="https://elbadrgroupeg.store/asus-tuf-fa506ncg">ASUS TUF Gaming A15 FA506NCG-HN857W</a>
            </div>
            <div class="price">43,000 EGP</div>
          </div>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_search_html)

    candidates = scraper.search_candidates("FA506NCG", limit=5)
    assert len(candidates) == 1
    assert "FA506NCG" in candidates[0].title
    assert candidates[0].price_egp == 43000.0
