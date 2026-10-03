"""Deep unit and mutation-resistant tests for retail store scrapers.

Covers:
- BTechStoreScraper: Next.js RSC chunks, Level 2 deep PDP crawl, fallback HTML selectors, fetch resilience.
- NoonStoreScraper: Akamai challenge handling, REST catalog API, Level 2 deep crawl, search API fallback.
- SigmaComputerStoreScraper: DOM fallback cards, HTML table specs fallback, Level 2 deep crawl.
- TradelineStoreScraper: HTML collection fallback, search HTML fallback, engine vs session fetch.
- CompumartsStoreScraper & ElBadrStoreScraper & AmazonStoreScraper & TwoBStoreScraper:
  Level 2 PDP enrichment, accessories skipping, stock status, error handling.
"""

import json
from unittest.mock import MagicMock
import pytest

from app.schemas.laptop import RetailerProduct
from app.stores.amazon import AmazonStoreScraper
from app.stores.btech import BTechStoreScraper
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.elbadr import ElBadrStoreScraper
from app.stores.noon import NoonStoreScraper
from app.stores.sigma import SigmaComputerStoreScraper
from app.stores.tradeline import TradelineStoreScraper
from app.stores.twob import TwoBStoreScraper


# =============================================================================
# 1. B.TECH Deep Tests
# =============================================================================


def test_btech_parse_next_f_items_formats():
    scraper = BTechStoreScraper()

    # Format 1: Escaped needle \"items\":[
    escaped_chunk = 'self.__next_f.push([1, "1:{\\"items\\":[{\\"name\\":\\"Lenovo Legion 5\\",\\"sku\\":\\"L123\\",\\"slug\\":\\"lenovo-legion-5\\"}]}"] satisfy'
    items1 = scraper._parse_next_f_items(escaped_chunk)
    assert len(items1) == 1
    assert items1[0]["name"] == "Lenovo Legion 5"
    assert items1[0]["sku"] == "L123"

    # Format 2: Unescaped needle "items":[
    unescaped_chunk = '{"items":[{"name":"HP Victus 15","sku":"H456","slug":"hp-victus-15"}]}'
    items2 = scraper._parse_next_f_items(unescaped_chunk)
    assert len(items2) == 1
    assert items2[0]["name"] == "HP Victus 15"
    assert items2[0]["sku"] == "H456"

    # Malformed chunk returns empty list
    assert scraper._parse_next_f_items("no items here") == []
    assert scraper._parse_next_f_items('{"items": invalid json') == []


def test_btech_fetch_html_engine_and_session_resilience():
    # 1. Engine success
    engine = MagicMock()
    doc = MagicMock()
    doc.html = "<html>" + "b" * 600 + "</html>"
    engine.fetch.return_value = doc
    scraper = BTechStoreScraper(engine=engine)
    assert scraper._fetch_html("https://btech.com/test") == doc.html

    # 2. Engine failure falls back to session
    engine.fetch.side_effect = RuntimeError("Engine failure")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html>session ok</html>"
    scraper._session.get = MagicMock(return_value=mock_resp)
    assert scraper._fetch_html("https://btech.com/test") == "<html>session ok</html>"

    # 3. Session returns non-200 or raises
    mock_resp.status_code = 500
    assert scraper._fetch_html("https://btech.com/test") == ""
    scraper._session.get.side_effect = Exception("Network offline")
    assert scraper._fetch_html("https://btech.com/test") == ""


def test_btech_scrape_catalog_level_2_and_accessory_skipping():
    scraper = BTechStoreScraper()

    # RSC chunk with 1 valid laptop and 1 standalone accessory
    rsc_html = """
    self.__next_f.push([1, "1:{\\"items\\":[
      {\\"name\\":\\"Dell G15 5530 Laptop Intel Core i7 16GB 512GB RTX 4060\\",\\"sku\\":\\"D5530\\",\\"slug\\":\\"dell-g15-5530\\"},
      {\\"name\\":\\"Dell Essential Backpack 15.6 Inch\\",\\"sku\\":\\"BAG01\\",\\"slug\\":\\"dell-backpack\\"}
    ]}"])
    """
    scraper._fetch_html = MagicMock(return_value=rsc_html)

    # Mock PDP specs extraction for Level 2
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"Processor Information": "Intel Core i7-13650HX", "RAM": "16GB DDR5"},
            "Dell Gaming Laptop",
            "G15-5530-E0001",
            "G15 5530",
            48000.0,
            "48,000.00 EGP",
            True,
        )
    )

    products = scraper.scrape_catalog(level=2, max_pages=1)
    # 1 product accepted, 1 accessory skipped
    assert len(products) == 1
    p = products[0]
    assert "Dell G15" in p.title
    assert p.specs.get("Processor Information") == "Intel Core i7-13650HX"
    assert p.mpn == "G15-5530-E0001"
    assert p.price_egp == 48000.0

    # Verify accessory was recorded in skipped_laptops
    assert len(scraper.skipped_laptops) == 1
    assert "Dell Essential Backpack" in scraper.skipped_laptops[0].name
    assert scraper.skipped_laptops[0].stage == "level1_filter"


# =============================================================================
# 2. Noon Deep Tests
# =============================================================================


def test_noon_fetch_html_akamai_challenge_fallback():
    engine = MagicMock()
    # Engine returns Akamai challenge page
    doc_challenge = MagicMock()
    doc_challenge.html = "<html><head><title>Akamai Access Denied</title></head><body>sec-if-cpt-container</body></html>"
    engine.fetch.return_value = doc_challenge

    scraper = NoonStoreScraper(engine=engine)
    # Session returns legitimate page
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body>Legitimate Noon Page</body></html>"
    scraper._session.get = MagicMock(return_value=mock_resp)

    # Because engine returned akamai challenge, it must fall back to session!
    res = scraper._fetch_html("https://www.noon.com/p")
    assert res == "<html><body>Legitimate Noon Page</body></html>"


def test_noon_fetch_catalog_api_success_and_error():
    scraper = NoonStoreScraper()

    api_payload = {
        "hits": [
            {
                "sku": "N88888888A",
                "name": "Asus TUF Gaming A15 FA506NFR",
                "pdp_url": "/egypt-en/asus-tuf-gaming-a15/N88888888A/p/",
                "sale_price": 38999.0,
                "is_buyable": True,
                "image_key": "tuf_thumb",
                "model_number": "FA506NFR-HN005W",
                "model_name": "FA506NFR",
                "brand": "ASUS",
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = api_payload
    scraper._session.get = MagicMock(return_value=mock_resp)

    raw_items = scraper._fetch_catalog_api(page=1)
    assert len(raw_items) == 1
    it = raw_items[0]
    assert it["sku"] == "N88888888A"
    assert it["title"] == "Asus TUF Gaming A15 FA506NFR"
    assert it["price_val"] == 38999.0
    assert it["mpn"] == "FA506NFR-HN005W"
    assert "tuf_thumb.jpg" in it["thumbnail_url"]

    # Exception returns empty list
    scraper._session.get.side_effect = Exception("API down")
    assert scraper._fetch_catalog_api(page=1) == []


def test_noon_search_candidates_api_fallback_when_next_data_empty():
    scraper = NoonStoreScraper()
    # 1. HTML fetch returns page without __NEXT_DATA__
    scraper._fetch_html = MagicMock(return_value="<html><body>No next data</body></html>")

    # 2. Search API fallback payload
    api_payload = {
        "hits": [
            {
                "sku": "N99999999A",
                "name": "Acer Nitro V 15 Gaming Laptop",
                "url": "/egypt-en/acer-nitro-v/N99999999A/p/",
                "sale_price": 35500.0,
                "is_buyable": True,
                "model_number": "ANV15-51-51H9",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = api_payload
    scraper._session.get = MagicMock(return_value=mock_resp)

    # Mock PDP specs
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"Processor": "Intel Core i5-13420H"},
            "Acer Nitro V",
            "ANV15-51-51H9",
            "ANV15-51",
            35500.0,
            "35,500.00 EGP",
            True,
        )
    )

    candidates = scraper.search_candidates("nitro v", limit=2)
    assert len(candidates) == 1
    assert candidates[0].retailer_sku == "N99999999A"
    assert candidates[0].price_egp == 35500.0
    assert candidates[0].mpn == "ANV15-51-51H9"


# =============================================================================
# 3. Sigma Deep Tests
# =============================================================================


def test_sigma_extract_products_from_html_fallback():
    scraper = SigmaComputerStoreScraper()

    html_dom = """
    <div class="product-grid">
      <div class="card rounded">
        <a href="/en/item?id=asus-rog-strix-g16">ASUS ROG Strix G16 G614JVR Core i9 32GB 1TB RTX 4080</a>
        <span class="price">108,000 EGP</span>
        <img src="https://sigma-computer.com/images/rog.jpg" />
      </div>
      <div class="card rounded">
        <a href="/en/item?id=short">Bad</a>
      </div>
    </div>
    """
    products = scraper._extract_products_from_html(html_dom)
    assert len(products) == 1
    assert products[0]["slug"] == "asus-rog-strix-g16"
    assert "ASUS ROG Strix" in products[0]["name"]
    assert products[0]["price_str"] == "108,000 EGP"
    assert products[0]["thumbnail"] == "https://sigma-computer.com/images/rog.jpg"


def test_sigma_extract_pdp_specs_html_table_fallback():
    scraper = SigmaComputerStoreScraper()
    # HTML without RSC script, but with <table>
    html_with_table = """
    <html>
      <body>
        <table>
          <tr><th>Processor</th><td>AMD Ryzen 9 7940HS</td></tr>
          <tr><th>VGA</th><td>NVIDIA GeForce RTX 4070</td></tr>
          <tr><th>RAM</th><td>32GB DDR5 5600MHz</td></tr>
        </table>
      </body>
    </html>
    """
    scraper._fetch_html = MagicMock(return_value=html_with_table)
    specs, desc = scraper._extract_product_specs("https://sigma-computer.com/en/item?id=zephyrus")
    assert specs.get("Processor") == "AMD Ryzen 9 7940HS"
    assert specs.get("VGA") == "NVIDIA GeForce RTX 4070"
    assert specs.get("RAM") == "32GB DDR5 5600MHz"


def test_sigma_scrape_catalog_level_2_enrichment():
    scraper = SigmaComputerStoreScraper()

    # Search page DOM fallback
    search_html = """
    <div class="product-grid">
      <div class="card rounded">
        <a href="/en/item?id=lenovo-yoga-pro-7">Lenovo Yoga Pro 7 14IMH9 Intel Core Ultra 7 32GB 1TB</a>
        <span class="price">62,000 EGP</span>
      </div>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=search_html)
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"Processor": "Intel Core Ultra 7 155H", "Memory": "32GB LPDDR5X"},
            "Lenovo Premium Yoga Laptop",
        )
    )

    products = scraper.scrape_catalog(level=2, max_pages=1)
    assert len(products) == 1
    p = products[0]
    assert "Yoga Pro 7" in p.title
    assert p.price_egp == 62000.0
    assert p.specs.get("Processor") == "Intel Core Ultra 7 155H"
    assert p.specs.get("Memory") == "32GB LPDDR5X"


# =============================================================================
# 4. Tradeline Deep Tests
# =============================================================================


def test_tradeline_scrape_collection_html_fallback():
    scraper = TradelineStoreScraper()

    html_fallback = """
    <div class="product-grid">
      <div class="card--product">
        <a href="/products/macbook-pro-14-m4">14-inch MacBook Pro Apple M4 16GB 512GB - Space Black</a>
        <div class="price">102,000 EGP</div>
      </div>
      <div class="card--product">
        <a href="/products/apple-magic-mouse">Apple Magic Mouse - White</a>
        <div class="price">4,500 EGP</div>
      </div>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=html_fallback)

    # Scrape collection via HTML fallback
    prods = scraper._scrape_collection_html("macbook-pro", page=1, level=1)
    # 1 macbook accepted, 1 accessory mouse skipped!
    assert len(prods) == 1
    assert "MacBook Pro" in prods[0].title
    assert prods[0].price_egp == 102000.0
    assert prods[0].retailer_sku == "macbook-pro-14-m4"

    # Verify accessory was recorded
    assert len(scraper.skipped_laptops) == 1
    assert "Magic Mouse" in scraper.skipped_laptops[0].name
    assert scraper.skipped_laptops[0].stage == "html_fallback_filter"


def test_tradeline_search_candidates_html_fallback():
    scraper = TradelineStoreScraper()
    # 1. Predictive search returns 0 products
    scraper._fetch_json = MagicMock(return_value={"resources": {"results": {"products": []}}})

    # 2. HTML search returns valid link
    html_search = """
    <div class="search-results">
      <a href="/products/macbook-air-15-m3">15-inch MacBook Air Apple M3 16GB 512GB - Silver</a>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=html_search)

    candidates = scraper.search_candidates("air m3", limit=2)
    assert len(candidates) == 1
    assert "MacBook Air" in candidates[0].title
    assert candidates[0].retailer_sku == "macbook-air-15-m3"


# =============================================================================
# 5. Compumarts, ElBadr, Amazon & 2B Deep Tests
# =============================================================================


def test_compumarts_scrape_catalog_level_2_enrichment():
    scraper = CompumartsStoreScraper()

    cat_html = """
    <div class="collection">
      <product-card>
        <a class="card-link" href="/products/asus-zenbook-duo">
          <span class="card__title">ASUS Zenbook Duo OLED UX8406MA Core Ultra 9 32GB 2TB</span>
        </a>
        <span class="price">115,000 EGP</span>
      </product-card>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=cat_html)
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"Processor": "Intel Core Ultra 9 185H", "RAM": "32GB LPDDR5X"},
            "Dual-screen OLED Zenbook",
            115000.0,
            "115,000.00 EGP",
            "UX8406MA-PZ024W",
            True,
        )
    )

    products = scraper.scrape_catalog(level=2, max_pages=1)
    assert len(products) == 1
    p = products[0]
    assert "Zenbook Duo" in p.title
    assert p.specs["Processor"] == "Intel Core Ultra 9 185H"
    assert p.mpn == "UX8406MA-PZ024W"
    assert p.price_egp == 115000.0


def test_elbadr_scrape_catalog_level_2_enrichment():
    scraper = ElBadrStoreScraper()

    cat_html = """
    <div class="main-products">
      <div class="product-layout">
        <div class="name">
          <a href="https://elbadrgroupeg.store/lenovo-loq-15">Lenovo LOQ 15IAX9 Intel Core i5-12450HX 16GB 512GB RTX 3050</a>
        </div>
        <span class="price">31,500 EGP</span>
      </div>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=cat_html)
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"CPU": "Intel Core i5-12450HX", "GPU": "NVIDIA GeForce RTX 3050 6GB"},
            "Lenovo LOQ Gaming",
            "83GS008GED",
            "15IAX9",
            31500.0,
            "31,500.00 EGP",
        )
    )

    products = scraper.scrape_catalog(level=2, max_pages=1)
    assert len(products) == 1
    p = products[0]
    assert "Lenovo LOQ" in p.title
    assert p.specs["CPU"] == "Intel Core i5-12450HX"
    assert p.mpn == "83GS008GED"
    assert p.price_egp == 31500.0


def test_amazon_search_candidates_filtering_and_parsing():
    scraper = AmazonStoreScraper()

    # Search result HTML with 1 laptop card and 1 non-laptop accessory
    search_html = """
    <div class="s-result-item" data-asin="B0CX212345">
      <h2><a href="/dp/B0CX212345"><span>Acer Aspire 3 A315-59 Laptop Intel Core i5-1235U 8GB RAM 512GB SSD</span></a></h2>
      <span class="a-price"><span class="a-offscreen">22,499.00 EGP</span></span>
    </div>
    <div class="s-result-item" data-asin="B0CX999999">
      <h2><a href="/dp/B0CX999999"><span>UGREEN Laptop Stand Ergonomic Aluminum Holder</span></a></h2>
      <span class="a-price"><span class="a-offscreen">850.00 EGP</span></span>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=search_html)
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"Processor": "Intel Core i5-1235U"},
            "Acer Aspire 3",
            "NX.K6TEM.006",
            "A315-59",
            22499.0,
            "22,499.00 EGP",
            True,
        )
    )

    candidates = scraper.search_candidates("aspire 3", limit=2)
    # Laptop accepted, laptop stand filtered out!
    assert len(candidates) == 1
    assert candidates[0].retailer_sku == "B0CX212345"
    assert candidates[0].price_egp == 22499.0
    assert candidates[0].mpn == "NX.K6TEM.006"


def test_twob_scrape_catalog_level_2_enrichment():
    scraper = TwoBStoreScraper()

    cat_html = """
    <div class="products wrapper">
      <ul class="product-items">
        <li class="product-item" data-product-id="5555">
          <div class="product-item-name">
            <a class="product-item-link" href="https://2b.com.eg/en/hp-victus-15-fa1093ne.html">
              HP Victus 15-fa1093ne Gaming Laptop Intel Core i5 16GB 512GB RTX 3050
            </a>
          </div>
          <span class="price">37,999 EGP</span>
        </li>
      </ul>
    </div>
    """
    scraper._fetch_html = MagicMock(return_value=cat_html)
    scraper._extract_product_specs = MagicMock(
        return_value=(
            {"Processor": "Intel Core i5-13420H", "Graphic": "RTX 3050 6GB"},
            "HP Victus Gaming",
            "804W8EA",
            "15-fa1093ne",
            37999.0,
            "37,999.00 EGP",
            True,
        )
    )

    products = scraper.scrape_catalog(level=2, max_pages=1)
    assert len(products) == 1
    p = products[0]
    assert "HP Victus" in p.title
    assert p.specs["Processor"] == "Intel Core i5-13420H"
    assert p.mpn == "804W8EA"
    assert p.price_egp == 37999.0
