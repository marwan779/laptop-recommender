"""Unit tests for app.scrapers.asus (AsusBrandScraper, AsusDateExtractor, and helpers)."""

from datetime import date, datetime
import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from app.engine.base import ScrapedDocument
from app.schemas.laptop import LaptopDetail, LaptopSummary
from app.scrapers.asus import (
    AsusBrandScraper,
    AsusDateExtractor,
    extract_colors,
    extract_structured_specs,
    is_in_date_range,
    parse_date_param,
    parse_price_egp,
)
from app.scrapers.base import BaseBrandScraper


# =============================================================================
# 1. BaseBrandScraper & Asus Date / Price Helper Tests
# =============================================================================


class DummyBrandScraper(BaseBrandScraper):
    @property
    def brand_name(self) -> str:
        return "Dummy"

    @property
    def catalog_url(self) -> str:
        return "https://dummy.com/catalog"

    def get_laptop_summaries(self, limit=None, until_model=None, max_pages=None):
        return []

    def get_laptop_detail(self, summary):
        return None


def test_base_brand_scraper_record_skipped_and_extract_configurations():
    scraper = DummyBrandScraper()
    scraper.record_skipped(
        name="Dummy Laptop",
        reason="Missing specs",
        url="https://dummy.com/item",
        stage="level2",
    )
    assert len(scraper.skipped_laptops) == 1
    assert scraper.skipped_laptops[0].name == "Dummy Laptop"
    assert scraper.skipped_laptops[0].reason == "Missing specs"
    assert scraper.skipped_laptops[0].stage == "level2"

    # Test extract_configurations fallback
    detail = LaptopDetail(
        brand="Dummy",
        name="Dummy Laptop",
        price=None,
        price_egp=None,
        currency="EGP",
        family="DummyFam",
        model=None,  # Fallback to UNKNOWN
        base_model=None,
        sku_part_number="SKU-999",
        product_url="https://dummy.com/p",
        all_specs={"CPU": "Test CPU"},
    )
    configs = scraper.extract_configurations(detail)
    assert len(configs) == 1
    assert configs[0].model == "UNKNOWN"
    assert configs[0].base_model is None
    assert configs[0].mpn == "SKU-999"
    assert configs[0].official_specs == {"CPU": "Test CPU"}


def test_parse_date_param_all_types_and_formats():
    assert parse_date_param(None) is None
    dt = datetime(2024, 5, 10, 12, 0)
    assert parse_date_param(dt) == dt

    d = date(2023, 11, 20)
    assert parse_date_param(d) == datetime(2023, 11, 20)

    assert parse_date_param("   ") is None
    assert parse_date_param("2024") == datetime(2024, 1, 1)
    assert parse_date_param("2024-05-15T10:30:00") == datetime(2024, 5, 15, 10, 30)
    assert parse_date_param("2024-05-15") == datetime(2024, 5, 15)
    assert parse_date_param("2024/05/15") == datetime(2024, 5, 15)
    assert parse_date_param("15-05-2024") == datetime(2024, 5, 15)
    assert parse_date_param("15/05/2024") == datetime(2024, 5, 15)
    assert parse_date_param("invalid-date-string") is None


def test_is_in_date_range_exact_dates_and_years():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31)

    # Both None -> always True
    assert is_in_date_range(None, None, None, None) is True
    assert is_in_date_range("2022-01-01", 2022, None, None) is True

    # Exact date within range
    assert is_in_date_range("2024-06-15T00:00:00", None, start, end) is True
    # Exact date before start
    assert is_in_date_range("2023-12-31", None, start, end) is False
    # Exact date after end
    assert is_in_date_range("2025-01-01", None, start, end) is False
    # Unparseable date falls back to release_year
    assert is_in_date_range("invalid-iso", 2024, start, end) is True
    assert is_in_date_range("invalid-iso", 2023, start, end) is False
    assert is_in_date_range("invalid-iso", 2025, start, end) is False

    # Completely unspecified falls back to True
    assert is_in_date_range(None, None, start, end) is True


def test_parse_price_egp_arabic_and_english():
    assert parse_price_egp(None) is None
    assert parse_price_egp("") is None
    assert parse_price_egp("   ") is None
    assert parse_price_egp("Price: 45,999.00 EGP") == 45999.00
    assert parse_price_egp("32000 EGP") == 32000.0
    # Arabic numerals: ١٢٣٤٥ -> 12345
    assert parse_price_egp("١٢,٣٤٥ ج.م") == 12345.0
    assert parse_price_egp("No numbers here") is None


def test_extract_colors():
    assert extract_colors(None) == []
    assert extract_colors("") == []
    colors = extract_colors("Indie Black / Cool Silver, Transparent Silver\nSolar Blue")
    assert "Indie Black" in colors
    assert "Cool Silver" in colors
    assert "Transparent Silver" in colors
    assert "Solar Blue" in colors
    # Short noisy strings filtered out (< 3 chars)
    assert extract_colors("A / BB") == []


def test_extract_structured_specs_mapping():
    raw_specs = {
        "Processor": "Intel Core Ultra 7 155H",
        "Operating System": "Windows 11 Home",
        "Graphics": "NVIDIA GeForce RTX 4060 8GB GDDR6",
        "Display": '16.0-inch 3.2K OLED 120Hz',
        "Memory": "16GB LPDDR5X",
        "Storage": "1TB M.2 NVMe PCIe 4.0 SSD",
        "I/O Ports": "2x Thunderbolt 4, 1x USB 3.2 Gen 1",
        "Camera": "FHD camera with IR",
        "Battery": "75WHrs, 4S1P, 4-cell Li-ion",
        "Weight": "1.50 kg",
    }
    structured = extract_structured_specs(raw_specs)
    assert structured["processor"] == "Intel Core Ultra 7 155H"
    assert structured["operating_system"] == "Windows 11 Home"
    assert structured["graphics"] == "NVIDIA GeForce RTX 4060 8GB GDDR6"
    assert structured["display"] == '16.0-inch 3.2K OLED 120Hz'
    assert structured["memory"] == "16GB LPDDR5X"
    assert structured["storage"] == "1TB M.2 NVMe PCIe 4.0 SSD"
    assert structured["io_ports"] == "2x Thunderbolt 4, 1x USB 3.2 Gen 1"
    assert structured["camera"] == "FHD camera with IR"
    assert structured["battery"] == "75WHrs, 4S1P, 4-cell Li-ion"
    assert structured["weight"] == "1.50 kg"
    assert structured["security"] is None


# =============================================================================
# 2. AsusDateExtractor Tests
# =============================================================================


def test_asus_date_extractor_meta_tags():
    doc = MagicMock(spec=ScrapedDocument)
    doc.get_meta.side_effect = lambda prop: "2024-08-15" if prop == "article:published_time" else None
    doc.get_json_ld.return_value = []
    doc.html = "<html><body>ASUS Vivobook</body></html>"

    dt, yr, c_yr = AsusDateExtractor.extract_from_doc(doc, text_corpus="ASUS Vivobook")
    assert dt == "2024-08-15"
    assert yr == 2024


def test_asus_date_extractor_json_ld():
    doc = MagicMock(spec=ScrapedDocument)
    doc.get_meta.return_value = None
    doc.get_json_ld.return_value = [{"@type": "Product", "datePublished": "2023-11-01"}]
    doc.html = "<html><body>ASUS ROG</body></html>"

    dt, yr, c_yr = AsusDateExtractor.extract_from_doc(doc, text_corpus="ASUS ROG")
    assert dt == "2023-11-01"
    assert yr == 2023


def test_asus_date_extractor_hardware_and_chassis_inference():
    doc = MagicMock(spec=ScrapedDocument)
    doc.get_meta.return_value = None
    doc.get_json_ld.return_value = []
    doc.html = "<div>Copyright © 2024 ASUSTeK Computer Inc.</div>"

    # Hardware inference: Lunar Lake Ultra 7 258V -> 2024-09-01
    dt, yr, c_yr = AsusDateExtractor.extract_from_doc(
        doc,
        text_corpus="ASUS Zenbook S 14",
        all_specs={"Processor": "Intel Core Ultra 7 258V Processor"},
    )
    assert yr == 2024
    assert dt == "2024-09-01"
    assert c_yr == 2024

    # Chassis inference: UX3404 -> 2023
    dt2, yr2, _ = AsusDateExtractor.extract_from_doc(
        doc,
        text_corpus="ASUS Zenbook 14 OLED UX3404",
        all_specs={},
    )
    assert yr2 == 2023
    assert dt2 == "2023-01-01"


# =============================================================================
# 3. AsusBrandScraper Family & Model Code Extraction Tests
# =============================================================================


def test_asus_brand_scraper_family_and_model_extraction():
    scraper = AsusBrandScraper()
    assert scraper.brand_name == "ASUS"
    assert "asus.com" in scraper.catalog_url

    # Family checks
    assert scraper._determine_family("ROG Zephyrus G16", "/laptops/rog-zephyrus-g16") == "ROG"
    assert scraper._determine_family("ASUS TUF Gaming A15", "/laptops/tuf-a15") == "TUF Gaming"
    assert scraper._determine_family("Zenbook Duo", "/laptops/zenbook-duo") == "Zenbook"
    assert scraper._determine_family("Vivobook Pro 15", "/laptops/vivobook-pro") == "Vivobook"
    assert scraper._determine_family("ProArt P16", "/laptops/proart-p16") == "ProArt"
    assert scraper._determine_family("ExpertBook B9", "/laptops/expertbook-b9") == "ExpertBook"
    assert scraper._determine_family("Chromebook Plus", "/laptops/chromebook-plus") == "Chromebook"
    assert scraper._determine_family("Unknown Model", "/laptops/some-laptop") == "ASUS Laptop"

    # Model code extraction
    assert scraper._extract_model_code("Vivobook S 14 OLED", "https://asus.com/eg-en/store/laptops/s5452/") == "S5452"
    assert scraper._extract_model_code("ASUS Zenbook 14 UX3405MA", "https://asus.com/eg-en/store/laptops/zenbook/") == "UX3405MA"
    assert scraper._extract_model_code("No Model In Title", "https://asus.com/eg-en/store/laptops/simple/") is None


# =============================================================================
# 4. AsusBrandScraper Level 1: Odin API & HTML DOM Fallback Tests
# =============================================================================


def test_asus_get_laptop_summaries_odin_api_success():
    scraper = AsusBrandScraper()

    mock_odin_response = {
        "Result": {
            "ProductList": [
                {
                    "Name": "ASUS Vivobook S 14 OLED <b>(S5452)</b>",
                    "ProductURL": "/eg-en/laptops/for-home/vivobook/asus-vivobook-s-14-oled-s5452/",
                    "SortPrice": "49,999",
                    "ImageList": [{"ImageURL": ["https://dlcdnwebimgs.asus.com/gain/thumb1.png"]}],
                    "ProductOnlineDt": "2024-05-10 12:00:00",
                },
                {
                    "Name": "ROG Zephyrus G16 (GA605)",
                    "ProductURL": "/eg-en/laptops/for-gaming/rog-zephyrus-g16-ga605/",
                    "SortPrice": 95000,
                    "ImageList": [{"ImageURL": ["https://dlcdnwebimgs.asus.com/gain/thumb2.png"]}],
                    "ProductOnlineDt": "2024-07-20 00:00:00",
                },
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_odin_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    empty_resp = MagicMock()
    empty_resp.read.return_value = json.dumps({"Result": {"ProductList": []}}).encode("utf-8")
    empty_resp.__enter__.return_value = empty_resp

    with patch("urllib.request.urlopen", side_effect=[mock_resp, empty_resp]):
        summaries = scraper.get_laptop_summaries(max_pages=2)

    assert len(summaries) == 2
    s1 = summaries[0]
    assert s1.name == "ASUS Vivobook S 14 OLED (S5452)"
    assert s1.model == "S5452"
    assert s1.family == "Vivobook"
    assert s1.price == "49,999 EGP"
    assert s1.price_egp == 49999.0
    assert s1.release_date == "2024-05-10"
    assert s1.release_year == 2024
    assert s1.thumbnail_url == "https://dlcdnwebimgs.asus.com/gain/thumb1.png"

    s2 = summaries[1]
    assert s2.family == "ROG"
    assert s2.price_egp == 95000.0


def test_asus_get_laptop_summaries_odin_api_watermark_and_limit():
    scraper = AsusBrandScraper()

    mock_odin_response = {
        "Result": {
            "ProductList": [
                {
                    "Name": "ASUS Vivobook S 14 OLED (S5452)",
                    "ProductURL": "/eg-en/laptops/vivobook-s-14-s5452/",
                    "SortPrice": "45,000",
                },
                {
                    "Name": "ASUS Zenbook 14 OLED (UX3405)",
                    "ProductURL": "/eg-en/laptops/zenbook-14-ux3405/",
                    "SortPrice": "60,000",
                },
                {
                    "Name": "ROG Strix G16 (G614)",
                    "ProductURL": "/eg-en/laptops/rog-strix-g614/",
                    "SortPrice": "80,000",
                },
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_odin_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    # Test Watermark stopping at UX3405: only S5452 should be recorded!
    with patch("urllib.request.urlopen", return_value=mock_resp):
        summaries = scraper.get_laptop_summaries(until_model="UX3405")
    assert len(summaries) == 1
    assert summaries[0].model == "S5452"

    # Test Limit
    mock_resp.read.return_value = json.dumps(mock_odin_response).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        summaries_limited = scraper.get_laptop_summaries(limit=2)
    assert len(summaries_limited) == 2


def test_asus_get_laptop_summaries_odin_failure_fallback_to_html_dom():
    engine_mock = MagicMock()
    scraper = AsusBrandScraper(engine=engine_mock)

    card_mock = MagicMock()
    link_mock = MagicMock()
    link_mock.attrib = {"href": "/eg-en/laptops/zenbook/zenbook-14-ux3405/"}
    link_mock.text = "ASUS Zenbook 14 OLED UX3405"
    card_mock.css.side_effect = lambda sel: (
        [link_mock] if 'a[href*="/laptops/"]' in sel
        else [MagicMock(text="65,000 EGP")] if "price" in sel.lower()
        else [MagicMock(attrib={"src": "https://img.asus.com/zen.jpg"})] if "img" in sel
        else []
    )

    doc_mock = MagicMock()
    doc_mock.raw.css.return_value = [card_mock]
    empty_doc = MagicMock()
    empty_doc.raw.css.return_value = []
    engine_mock.fetch.side_effect = [doc_mock, empty_doc]

    # Force Odin API to fail so it falls back to HTML DOM
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network down")):
        summaries = scraper.get_laptop_summaries(max_pages=2)

    assert len(summaries) == 1
    assert "Zenbook" in summaries[0].name
    assert summaries[0].family == "Zenbook"
    assert summaries[0].price == "65,000 EGP"
    assert summaries[0].price_egp == 65000.0


# =============================================================================
# 5. AsusBrandScraper Level 2: get_laptop_detail & extract_configurations
# =============================================================================


def test_asus_get_laptop_detail_placeholder_detection():
    engine_mock = MagicMock()
    scraper = AsusBrandScraper(engine=engine_mock)

    summary = LaptopSummary(
        brand="ASUS",
        name="Empty ASUS Laptop",
        product_url="https://asus.com/p",
        specs_url="https://asus.com/p/techspec/",
    )

    # 1. 0 of 0 placeholder
    doc_placeholder = MagicMock()
    doc_placeholder.markdown.return_value = "Viewing 1 - 0 of 0 products"
    engine_mock.fetch.return_value = doc_placeholder

    res = scraper.get_laptop_detail(summary)
    assert res is None
    assert len(scraper.skipped_laptops) == 1
    assert "Placeholder" in scraper.skipped_laptops[0].reason

    # 2. No core hardware specs
    doc_no_specs = MagicMock()
    doc_no_specs.markdown.return_value = "Model\nASUS Laptop 15\nColor\nSilver\nIncluded in the Box\nPower Cable"
    engine_mock.fetch.return_value = doc_no_specs

    res2 = scraper.get_laptop_detail(summary)
    assert res2 is None
    assert len(scraper.skipped_laptops) == 2
    assert "No core hardware specifications" in scraper.skipped_laptops[1].reason


def test_asus_get_laptop_detail_and_configuration_extraction_success():
    engine_mock = MagicMock()
    scraper = AsusBrandScraper(engine=engine_mock)

    summary = LaptopSummary(
        brand="ASUS",
        name="ASUS Vivobook S 14 OLED (S5452)",
        product_url="https://asus.com/eg-en/store/laptops/s5452",
        specs_url="https://asus.com/eg-en/store/laptops/s5452/techspec/",
        model="S5452",
        family="Vivobook",
    )

    sample_markdown = """
Model
S5452QA-QD001W, S5452QA-QD002W
Color
Neutral Black / Cool Silver
Operating System
Windows 11 Home
Processor
Snapdragon X Plus X1P-42-100 Processor
Display
14.0-inch 3K (2880 x 1800) OLED 16:10 aspect ratio
Memory
16GB LPDDR5X on board
Storage
512GB M.2 NVMe PCIe 4.0 SSD
Battery
70WHrs, 3S1P, 3-cell Li-ion
Price: 42,999 EGP
Visit https://store.asus.com/eg/90NB1471-M002W0.html to purchase.
"""

    doc_mock = MagicMock()
    doc_mock.markdown.return_value = sample_markdown
    doc_mock.get_meta.return_value = "2024-06-18"
    doc_mock.get_json_ld.return_value = []
    doc_mock.html = sample_markdown

    img_mock = MagicMock()
    img_mock.attrib = {"src": "/gallery/photo1.webp"}
    doc_mock.raw.css.return_value = [img_mock]

    engine_mock.fetch.return_value = doc_mock

    detail = scraper.get_laptop_detail(summary)
    assert detail is not None
    assert detail.brand == "ASUS"
    assert detail.model in ("S5452QA-QD001W", "S5452QA-QD002W")
    assert detail.base_model == "S5452"
    assert detail.price_egp == 42999.0
    assert detail.sku_part_number == "90NB1471-M002W0"
    assert detail.release_date == "2024-06-18"
    assert detail.release_year == 2024
    assert "Neutral Black" in detail.colors
    assert "Cool Silver" in detail.colors
    assert len(detail.gallery_images) == 1
    assert "photo1.webp" in detail.gallery_images[0]

    # Verify extracted physical configurations
    assert len(detail.configurations) >= 2
    full_sku_models = [cfg.model for cfg in detail.configurations]
    assert "S5452QA-QD001W" in full_sku_models
    assert "S5452QA-QD002W" in full_sku_models
    for cfg in detail.configurations:
        assert cfg.official_specs["Processor"] == "Snapdragon X Plus X1P-42-100 Processor"
        assert cfg.official_specs["Storage"] == "512GB M.2 NVMe PCIe 4.0 SSD"
