import pytest
from app.stores.tradeline import TradelineStoreScraper
from app.stores.registry import STORE_REGISTRY, get_store_scraper
from app.schemas.laptop import RetailerProduct


def test_tradeline_properties():
    scraper = TradelineStoreScraper()
    assert scraper.store_name == "Tradeline"
    assert scraper.store_key == "tradeline"
    assert scraper.base_url == "https://tradelinestores.com"
    assert scraper.base_domain == "tradelinestores.com"


def test_tradeline_registry():
    assert "tradeline" in STORE_REGISTRY
    assert STORE_REGISTRY["tradeline"] is TradelineStoreScraper


def test_tradeline_parse_price():
    scraper = TradelineStoreScraper()
    val, formatted = scraper.parse_egp_price("195,500.00 EGP")
    assert val == 195500.0
    assert formatted == "195,500.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("98800")
    assert val2 == 98800.0
    assert formatted2 == "98,800.00 EGP"


def test_tradeline_non_laptop_filtering():
    scraper = TradelineStoreScraper()
    accessories = [
        "Apple Magic Mouse - White",
        "Apple 70W USB-C Power Adapter Charger",
        "Incase Laptop Sleeve for 16-inch MacBook Pro",
        "Apple AirPods Pro 2",
        "USB-C to MagSafe 3 Cable",
    ]
    for acc in accessories:
        assert scraper._is_standalone_accessory(acc) is True

    laptops = [
        "16-inch MacBook Pro: Apple M5 Pro chip with 18-core CPU and 20-core GPU, 1TB SSD - Space Black",
        "13-inch MacBook Air: Apple M3 chip with 8-core CPU and 10-core GPU, 16GB RAM, 512GB SSD - Midnight",
        "15-inch MacBook Air: Apple M2 chip - Silver",
    ]
    for lap in laptops:
        assert scraper._is_standalone_accessory(lap) is False


def test_tradeline_specs_from_title():
    specs: dict[str, str] = {}
    title = "16-inch MacBook Pro: Apple M5 Pro chip with 18-core CPU and 20-core GPU, 1TB SSD - Space Black"
    TradelineStoreScraper._extract_specs_from_title(title, specs)

    assert specs.get("Display_Size") == "16-inch"
    assert specs.get("Processor") == "Apple M5 Pro"
    assert specs.get("CPU_Cores") == "18-core"
    assert specs.get("GPU_Cores") == "20-core"
    assert specs.get("Storage") == "1TB SSD"
    assert specs.get("Color") == "Space Black"


def test_tradeline_multi_variant_parsing():
    scraper = TradelineStoreScraper()
    item = {
        "id": 1001,
        "title": "14-inch MacBook Pro M4",
        "handle": "14-inch-macbook-pro-m4",
        "body_html": "<p>MacBook Pro with Apple M4</p>",
        "tags": ["MacBook Pro", "Apple M4", "14-inch"],
        "variants": [
            {
                "id": 5001,
                "title": "16GB RAM / 512GB SSD / Space Black",
                "sku": "MX2J3AB/A",
                "price": 105000.0,
                "available": True,
            },
            {
                "id": 5002,
                "title": "24GB RAM / 1TB SSD / Silver",
                "sku": "MX2K3AB/A",
                "price": 125000.0,
                "available": True,
            },
        ],
    }

    p1 = scraper._parse_product_variant(item, item["variants"][0], "macbook-pro", level=1)
    p2 = scraper._parse_product_variant(item, item["variants"][1], "macbook-pro", level=1)

    assert p1 is not None
    assert p1.retailer_sku == "MX2J3AB/A"
    assert p1.price_egp == 105000.0
    assert "MX2J3AB/A" in p1.mpn or p1.mpn == "MX2J3AB/A"
    assert "16GB RAM" in p1.title

    assert p2 is not None
    assert p2.retailer_sku == "MX2K3AB/A"
    assert p2.price_egp == 125000.0
    assert "24GB RAM" in p2.title


def test_tradeline_mock_pdp_specs(monkeypatch):
    scraper = TradelineStoreScraper()
    mock_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@type": "Product",
          "name": "16-inch MacBook Pro M5 Pro",
          "sku": "MGEA4AE/A",
          "offers": {
            "@type": "Offer",
            "price": "195500.00",
            "availability": "http://schema.org/InStock"
          },
          "description": "High performance MacBook Pro 16 with M5 Pro chip."
        }
        </script>
      </head>
      <body>
        <table>
          <tr><td>Chip</td><td>Apple M5 Pro</td></tr>
          <tr><td>Unified Memory</td><td>24GB</td></tr>
          <tr><td>Storage</td><td>1TB SSD</td></tr>
          <tr><td>Display</td><td>16.2-inch Liquid Retina XDR</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_html)
    specs, desc, p_val, p_str, sku, in_stock = scraper._extract_product_specs(
        "https://tradelinestores.com/products/test-macbook"
    )

    assert sku == "MGEA4AE/A"
    assert p_val == 195500.0
    assert in_stock is True
    assert specs.get("Chip") == "Apple M5 Pro"
    assert specs.get("Unified Memory") == "24GB"
    assert specs.get("Storage") == "1TB SSD"
    assert specs.get("Display") == "16.2-inch Liquid Retina XDR"


def test_tradeline_watermark_stopping(monkeypatch):
    scraper = TradelineStoreScraper()

    mock_collection_data = {
        "products": [
            {
                "id": 1,
                "title": "15-inch MacBook Air M3 16GB 512GB - Midnight",
                "handle": "15-inch-macbook-air-m3-midnight",
                "variants": [{"id": 101, "sku": "MC111AE/A", "price": 85000.0, "available": True}],
            },
            {
                "id": 2,
                "title": "13-inch MacBook Air M2 8GB 256GB - Starlight",
                "handle": "13-inch-macbook-air-m2-starlight",
                "variants": [{"id": 102, "sku": "MC222AE/A", "price": 65000.0, "available": True}],
            },
            {
                "id": 3,
                "title": "14-inch MacBook Pro M4 24GB 1TB - Space Black",
                "handle": "14-inch-macbook-pro-m4-space-black",
                "variants": [{"id": 103, "sku": "MC333AE/A", "price": 115000.0, "available": True}],
            },
        ]
    }

    monkeypatch.setattr(scraper, "_fetch_json", lambda url: mock_collection_data)

    # Test watermark stop at MC222AE/A (so only product 1 is returned)
    results = scraper.scrape_catalog(level=1, until_model="MC222AE/A", max_pages=1)
    assert len(results) == 1
    assert results[0].retailer_sku == "MC111AE/A"


def test_tradeline_search_candidates(monkeypatch):
    scraper = TradelineStoreScraper()

    mock_search_data = {
        "resources": {
            "results": {
                "products": [
                    {
                        "id": 99,
                        "title": "13-inch MacBook Air: Apple M3 chip - Midnight",
                        "handle": "13-inch-macbook-air-m3-midnight",
                        "url": "/products/13-inch-macbook-air-m3-midnight",
                        "price": "68,900.00",
                        "image": "https://cdn.shopify.com/test.jpg",
                    }
                ]
            }
        }
    }

    monkeypatch.setattr(scraper, "_fetch_json", lambda url: mock_search_data)
    monkeypatch.setattr(scraper, "_extract_product_specs", lambda url: ({}, None, 68900.0, "68,900.00 EGP", "MRXN3AB/A", True))

    candidates = scraper.search_candidates("macbook air m3", limit=2)
    assert len(candidates) == 1
    assert "MacBook Air" in candidates[0].title
    assert candidates[0].retailer_sku == "MRXN3AB/A"
