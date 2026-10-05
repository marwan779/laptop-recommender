import pytest
from bs4 import BeautifulSoup

from app.stores.compumarts import CompumartsStoreScraper
from app.schemas.laptop import RetailerProduct


def test_compumarts_properties():
    scraper = CompumartsStoreScraper()
    assert scraper.store_name == "Compumarts"
    assert scraper.store_key == "compumarts"
    assert scraper.base_url == "https://www.compumarts.com"
    assert scraper.base_domain == "compumarts.com"


def test_compumarts_parse_price():
    scraper = CompumartsStoreScraper()
    val, formatted = scraper.parse_egp_price("59,999.00 EGP")
    assert val == 59999.0
    assert formatted == "59,999.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("Regular price 62,222 EGP")
    assert val2 == 62222.0


def test_compumarts_non_laptop_filtering():
    scraper = CompumartsStoreScraper()
    for kw in ["Lenovo Legion Backpack 16", "HP 65W AC Adapter Charger", "Redragon Gaming Mouse"]:
        assert scraper._is_standalone_accessory(kw) is True

    # A laptop with keyboard details or bundle keywords must NOT be filtered
    laptop_title = "Lenovo Legion Pro 5 - Intel Core i7-14700HX - 16GB DDR5 - RTX 4060 - Keyboard English"
    assert scraper._is_standalone_accessory(laptop_title) is False


def test_compumarts_mock_pdp_specs(monkeypatch):
    scraper = CompumartsStoreScraper()
    mock_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@type": "Product",
          "name": "HP Victus 15-fa2352TX",
          "sku": "15-fa2352TX",
          "offers": {
            "@type": "Offer",
            "price": "59999.00",
            "availability": "http://schema.org/InStock"
          }
        }
        </script>
      </head>
      <body>
        <table>
          <tr><td>CPU</td><td>Intel Core i7-13620H</td></tr>
          <tr><td>GPU</td><td>NVIDIA RTX 5050 8GB</td></tr>
          <tr><td>MEMORY</td><td>16GB DDR5</td></tr>
          <tr><td>STORAGE</td><td>512GB SSD</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_html)
    specs, desc, p_val, p_str, sku, in_stock = scraper._extract_product_specs(
        "https://www.compumarts.com/products/test"
    )

    assert sku == "15-fa2352TX"
    assert p_val == 59999.0
    assert in_stock is True
    assert specs.get("CPU") == "Intel Core i7-13620H"
    assert specs.get("GPU") == "NVIDIA RTX 5050 8GB"
    assert specs.get("STORAGE") == "512GB SSD"


def test_compumarts_watermark_matching():
    scraper = CompumartsStoreScraper()
    assert scraper._matches_watermark("ACER Nitro ANV15-52-786F", "ANV15-52-786F") is True
    assert scraper._matches_watermark("lenovo-loq-15irx9-83dv01hsed", "83DV01HSED") is True
    assert scraper._matches_watermark("HP Victus 15-fa2352TX", "fa2352tx") is True
    assert scraper._matches_watermark("HP Victus 15-fa2352TX", "completely-different-model") is False
    assert scraper._matches_watermark(None, "83DV01HSED") is False
    assert scraper._matches_watermark("HP Victus", None) is False


def test_compumarts_catalog_watermark_stop(monkeypatch):
    scraper = CompumartsStoreScraper()
    mock_collection_html = """
    <html>
      <body>
        <product-card>
          <a class="card-link" href="/products/lenovo-loq-1">Lenovo LOQ Model 1</a>
          <span class="price__current"><span class="js-value">50,000 EGP</span></span>
        </product-card>
        <product-card>
          <a class="card-link" href="/products/lenovo-loq-2">Lenovo LOQ Model 2</a>
          <span class="price__current"><span class="js-value">55,000 EGP</span></span>
        </product-card>
        <product-card>
          <a class="card-link" href="/products/lenovo-loq-3">Lenovo LOQ Model 3</a>
          <span class="price__current"><span class="js-value">60,000 EGP</span></span>
        </product-card>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_collection_html)

    # Halt at Model 2 (so only Model 1 is ingested)
    results = scraper.scrape_catalog(level=1, until_model="Model 2", max_pages=1)
    assert len(results) == 1
    assert "Model 1" in results[0].title


def test_compumarts_pattern_registry_profile():
    from app.core.patterns.registry import PatternRegistry

    cfg = PatternRegistry.get("compumarts")
    assert cfg.store_key == "compumarts"
    assert "table" in cfg.container_selectors
    assert any(".product-description" in sel for sel in cfg.container_selectors)
    assert any(".rte" in sel for sel in cfg.container_selectors)


def test_compumarts_empty_pdp_title_fallback(monkeypatch):
    scraper = CompumartsStoreScraper()
    mock_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@type": "Product",
          "name": "ASUS TUF Gaming FX607VU",
          "sku": "FX607VU-RL167W",
          "offers": {
            "@type": "Offer",
            "price": "49999.00",
            "availability": "http://schema.org/InStock"
          }
        }
        </script>
      </head>
      <body>
        <div class="rte">
          <p>Welcome to our store. Learn more</p>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_html)
    card_html = BeautifulSoup(
        """
        <product-card>
          <a class="card-link" href="/products/asus-tuf-f16">
            Laptop ASUS TUF Gaming FX607VU – Intel Core 7 240H RTX 4050 6GB 16GB DDR5 512GB SSD 16 FHD
          </a>
        </product-card>
        """,
        "html.parser",
    )
    product = scraper._parse_card(card_html, seen_urls=set(), level=2)
    assert product is not None
    assert product.has_text_specs is False
    assert product.specs_extraction_source == "title_fallback"
    assert product.specs_fallback_reason == "No text specs found in PDP"
    assert product.specs.get("Processor") == "Intel Core 7 240H"
    assert product.specs.get("Graphics") == "RTX 4050 6GB"
    assert product.specs.get("Memory") == "16GB DDR5"
    assert product.specs.get("Storage") == "512GB SSD"
