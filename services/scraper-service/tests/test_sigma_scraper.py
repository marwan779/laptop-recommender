import pytest
from app.stores.sigma import SigmaComputerStoreScraper


def test_sigma_properties():
    scraper = SigmaComputerStoreScraper()
    assert scraper.store_name == "Sigma Computer"
    assert scraper.store_key == "sigma"
    assert scraper.base_url == "https://www.sigma-computer.com"
    assert scraper.base_domain == "sigma-computer.com"


def test_sigma_parse_price():
    scraper = SigmaComputerStoreScraper()
    val, formatted = scraper.parse_egp_price("42,999 EGP")
    assert val == 42999.0
    assert formatted == "42,999.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("59499")
    assert val2 == 59499.0


def test_sigma_watermark_matching():
    scraper = SigmaComputerStoreScraper()
    assert scraper._matches_watermark("ASUS TUF Gaming A15-FA506NCG-HN857W", "FA506NCG-HN857W") is True
    assert scraper._matches_watermark("HP Victus 15-r0050nia", "81Q08EA") is False
    assert scraper._matches_watermark("HP Victus 15-r0050nia", "15-r0050nia") is True
    assert scraper._matches_watermark(None, "FA506NCG") is False
    assert scraper._matches_watermark("ASUS TUF", None) is False


def test_sigma_accessory_filter():
    scraper = SigmaComputerStoreScraper()
    # A laptop with "Keyboard English" must NOT be considered an accessory
    loq_laptop = "LENOVO LOQ 15IRX9 83DV01HPSA - Intel Core i7 13645HX - NVIDIA GeForce RTX 4050 6GB - 16GB DDR5 4800Hz - 512GB Nvme GEN 4 - 15.6-inch FHD IPS 100% sRGB 300nits 144Hz - Dos - White Backlit - Keyboard English."
    assert scraper._is_standalone_accessory(loq_laptop) is False

    # Standalone mouse or backpack MUST be filtered
    assert scraper._is_standalone_accessory("Lenovo 15.6 Laptop Casual Backpack") is True
    assert scraper._is_standalone_accessory("Redragon Gaming Mouse") is True


def test_sigma_rsc_decode_and_extract():
    scraper = SigmaComputerStoreScraper()
    mock_html = """
    <html>
      <head>
        <script>self.__next_f.push([1,"1:{\\"products\\":[{\\"slug\\":\\"test-laptop-slug\\",\\"name\\":\\"Test Gaming Laptop RTX 4060\\",\\"sku\\":\\"TEST-SKU-123\\",\\"price\\":{\\"current\\":45000},\\"is_stock\\":true}]}"])</script>
      </head>
      <body></body>
    </html>
    """
    rsc_text = scraper._decode_rsc_payload(mock_html)
    assert '"products":' in rsc_text

    products = scraper._extract_products_from_rsc(rsc_text)
    assert len(products) == 1
    assert products[0]["slug"] == "test-laptop-slug"
    assert products[0]["sku"] == "TEST-SKU-123"
    assert products[0]["price"]["current"] == 45000


def test_sigma_extract_pdp_specs(monkeypatch):
    scraper = SigmaComputerStoreScraper()
    mock_pdp_html = """
    <html>
      <head>
        <script>self.__next_f.push([1,"1:{\\"specifications\\":[{\\"name\\":\\"Processor\\",\\"value\\":\\"Intel Core i7-13620H\\"},{\\"name\\":\\"Graphics Card\\",\\"value\\":\\"RTX 4060 8GB\\"},{\\"name\\":\\"Memory\\",\\"value\\":\\"16GB DDR5\\"}]}"])</script>
      </head>
      <body></body>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_pdp_html)
    specs, desc = scraper._extract_product_specs("https://www.sigma-computer.com/en/item?id=test")
    assert specs.get("Processor") == "Intel Core i7-13620H"
    assert specs.get("Graphics Card") == "RTX 4060 8GB"
    assert specs.get("Memory") == "16GB DDR5"


def test_sigma_catalog_mock(monkeypatch):
    scraper = SigmaComputerStoreScraper()
    mock_search_html = """
    <html>
      <script>self.__next_f.push([1,"1:{\\"products\\":[{\\"slug\\":\\"laptop-1\\",\\"name\\":\\"Laptop One Model 1\\",\\"sku\\":\\"SKU-1\\",\\"price\\":{\\"current\\":30000},\\"is_stock\\":true},{\\"slug\\":\\"laptop-2\\",\\"name\\":\\"Laptop Two Model 2\\",\\"sku\\":\\"SKU-2\\",\\"price\\":{\\"current\\":40000},\\"is_stock\\":true}]}"])</script>
    </html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: mock_search_html)

    # Test Level 1
    items = scraper.scrape_catalog(level=1, max_pages=1)
    assert len(items) == 2
    assert items[0].title == "Laptop One Model 1"
    assert items[0].price_egp == 30000.0
    assert items[0].retailer_sku == "SKU-1"
    assert items[0].specs == {}

    # Test Watermark stop at SKU-2
    items_wm = scraper.scrape_catalog(level=1, until_model="SKU-2", max_pages=1)
    assert len(items_wm) == 1
    assert items_wm[0].retailer_sku == "SKU-1"
