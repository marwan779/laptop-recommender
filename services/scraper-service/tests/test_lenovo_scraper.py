"""Unit tests for app.scrapers.lenovo (LenovoBrandScraper, LenovoDateExtractor, and helpers)."""

from datetime import date, datetime
import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from app.schemas.laptop import LaptopDetail, LaptopSummary
from app.scrapers.lenovo import (
    LenovoBrandScraper,
    LenovoDateExtractor,
    clean_html_text,
    parse_date_param,
)


# =============================================================================
# 1. Helper Functions Tests
# =============================================================================


def test_parse_date_param_lenovo():
    assert parse_date_param(None) is None
    dt = datetime(2024, 8, 1, 9, 0)
    assert parse_date_param(dt) == dt
    d = date(2023, 5, 20)
    assert parse_date_param(d) == datetime(2023, 5, 20)
    assert parse_date_param("") is None
    assert parse_date_param("   ") is None
    assert parse_date_param("2024") == datetime(2024, 1, 1)
    assert parse_date_param("2024-08-15T12:00:00") == datetime(2024, 8, 15, 12, 0)
    assert parse_date_param("2024-08-15") == datetime(2024, 8, 15)
    assert parse_date_param("2024/08/15") == datetime(2024, 8, 15)
    assert parse_date_param("15-08-2024") == datetime(2024, 8, 15)
    assert parse_date_param("15/08/2024") == datetime(2024, 8, 15)
    assert parse_date_param("not-a-date") is None


def test_clean_html_text():
    assert clean_html_text(None) == ""
    assert clean_html_text("") == ""

    raw_html = (
        "<p>Key Features:&reg;</p>"
        "<ul>"
        "<li>Intel Core Ultra 7 &amp; 16GB RAM</li>"
        "<li>1TB SSD<br/>Fast storage</li>"
        "</ul>"
    )
    cleaned = clean_html_text(raw_html)
    assert "Key Features:®" in cleaned
    assert "• Intel Core Ultra 7 & 16GB RAM" in cleaned
    assert "1TB SSD" in cleaned
    assert "Fast storage" in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned


# =============================================================================
# 2. LenovoDateExtractor Tests
# =============================================================================


def test_lenovo_date_extractor_generation_map():
    # Gen 12 -> 2024
    dt, yr = LenovoDateExtractor.extract("ThinkPad X1 Carbon Gen 12", "")
    assert yr == 2024
    assert dt == "2024-03-01"

    # Gen 8 -> 2023
    dt2, yr2 = LenovoDateExtractor.extract("Legion Pro 7 Gen 8", "")
    assert yr2 == 2023
    assert dt2 == "2023-01-01"


def test_lenovo_date_extractor_hardware_map():
    # Snapdragon X Elite -> 2024
    dt, yr = LenovoDateExtractor.extract("Yoga Slim 7x", "Snapdragon X Elite X1E-78-100")
    assert yr == 2024
    assert dt == "2024-06-01"

    # Intel Core Ultra 7 155H (Meteor Lake) -> 2024
    dt, yr = LenovoDateExtractor.extract("IdeaPad Pro 5", "Intel Core Ultra 7 155H")
    assert yr == 2024
    assert dt == "2024-01-01"

    # Intel 13th Gen -> 2023
    dt, yr = LenovoDateExtractor.extract("Lenovo LOQ 15", "Intel Core i7-13700H")
    assert yr == 2023
    assert dt == "2023-01-01"


# =============================================================================
# 3. LenovoBrandScraper Properties & Parsing Helpers
# =============================================================================


def test_lenovo_brand_scraper_properties_and_families():
    scraper = LenovoBrandScraper()
    assert scraper.brand_name == "Lenovo"
    assert "lenovo.com" in scraper.catalog_url

    assert scraper._determine_family("Lenovo Legion Pro 7i", "/legion") == "Legion"
    assert scraper._determine_family("Lenovo LOQ 15IRX9", "/loq") == "LOQ"
    assert scraper._determine_family("ThinkPad T14s Gen 5", "/thinkpad") == "ThinkPad"
    assert scraper._determine_family("ThinkBook 16 Gen 7", "/thinkbook") == "ThinkBook"
    assert scraper._determine_family("Yoga Slim 7x", "/yoga") == "Yoga"
    assert scraper._determine_family("IdeaPad Slim 3 15", "/ideapad") == "IdeaPad"
    assert scraper._determine_family("Generic Lenovo Model", "/laptops/generic") == "Lenovo Laptop"


def test_lenovo_brand_scraper_extract_tables_from_html():
    scraper = LenovoBrandScraper()

    # Valid JSON raw_decode script
    html_with_script = """
    <html>
    <head>
    <script>
    window["techSpecs_82XW"] = {
        "data": {
            "requestApiData": [
                {
                    "data": {
                        "data": {
                            "tables": [
                                {
                                    "groupHeadline": "Processor",
                                    "specs": [
                                        {"headline": "CPU", "text": "Intel Core i7-13700HX"}
                                    ]
                                }
                            ]
                        }
                    }
                }
            ]
        }
    };
    </script>
    </head>
    </html>
    """
    tables = scraper._extract_tables_from_html(html_with_script)
    assert len(tables) == 1
    assert tables[0]["groupHeadline"] == "Processor"
    assert tables[0]["specs"][0]["headline"] == "CPU"

    # Malformed script returns empty list
    bad_html = '<html><script>window["techSpecs_bad"] = { bad json };</script></html>'
    assert scraper._extract_tables_from_html(bad_html) == []


def test_lenovo_brand_scraper_fetch_specs_via_api():
    scraper = LenovoBrandScraper()

    api_response = {
        "data": {
            "tables": [
                {
                    "groupHeadline": "Memory",
                    "specs": [{"headline": "RAM", "text": "16GB DDR5 5200MHz"}],
                }
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(api_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        tables = scraper._fetch_specs_via_api("82XW000NED")
    assert len(tables) == 1
    assert tables[0]["groupHeadline"] == "Memory"

    # API failure returns empty list
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Failed")):
        tables_fail = scraper._fetch_specs_via_api("82XW000NED")
    assert tables_fail == []


# =============================================================================
# 4. LenovoBrandScraper Level 1: get_laptop_summaries Tests
# =============================================================================


def test_lenovo_get_laptop_summaries_dlp_api_success():
    scraper = LenovoBrandScraper()

    dlp_payload = {
        "data": {
            "pageCount": 1,
            "data": [
                {
                    "products": [
                        {
                            "productCode": "LEN-001",
                            "productName": "Lenovo Legion Pro 5 Gen 8 (16″ AMD)",
                            "url": "/eg/en/p/laptops/legion-laptops/legion-pro-series/legion-pro-5-gen-8-16-amd/len101g0025",
                            "price": 68999,
                            "media": {"image": {"imageAddress": "//static.lenovo.com/legion5.png"}},
                        },
                        {
                            "id": "LEN-002",
                            "productName": "Lenovo LOQ 15IAX9",
                            "url": "https://www.lenovo.com/eg/en/p/laptops/loq/loq-15iax9/len101q0005",
                            "price": 34500,
                            "media": {"image": {"imageAddress": "https://static.lenovo.com/loq15.png"}},
                        },
                    ]
                }
            ],
        }
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(dlp_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        summaries = scraper.get_laptop_summaries(max_pages=1)

    assert len(summaries) == 2
    s1 = summaries[0]
    assert s1.name == "Lenovo Legion Pro 5 Gen 8 (16″ AMD)"
    assert s1.family == "Legion"
    assert s1.price == "68999 EGP"
    assert s1.price_egp == 68999.0
    assert s1.thumbnail_url == "https://static.lenovo.com/legion5.png"

    s2 = summaries[1]
    assert s2.family == "LOQ"
    assert s2.price_egp == 34500.0


def test_lenovo_get_laptop_summaries_watermark_and_limit():
    scraper = LenovoBrandScraper()

    dlp_payload = {
        "data": {
            "pageCount": 1,
            "data": [
                {
                    "products": [
                        {
                            "productCode": "P1",
                            "productName": "ThinkPad T14 Gen 4",
                            "url": "/eg/en/p/laptops/thinkpad-t14-gen-4",
                            "price": 50000,
                        },
                        {
                            "productCode": "P2",
                            "productName": "ThinkPad X1 Carbon Gen 12",
                            "url": "/eg/en/p/laptops/thinkpad-x1-carbon-gen-12",
                            "price": 90000,
                        },
                    ]
                }
            ],
        }
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(dlp_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    # Watermark stop at X1 Carbon: only P1 should be returned!
    with patch("urllib.request.urlopen", return_value=mock_resp):
        summaries = scraper.get_laptop_summaries(until_model="thinkpad-x1-carbon-gen-12")
    assert len(summaries) == 1
    assert summaries[0].name == "ThinkPad T14 Gen 4"

    # Limit stop
    mock_resp.read.return_value = json.dumps(dlp_payload).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        summaries_lim = scraper.get_laptop_summaries(limit=1)
    assert len(summaries_lim) == 1


# =============================================================================
# 5. LenovoBrandScraper Level 2: get_laptop_detail & extract_configurations
# =============================================================================


def test_lenovo_get_laptop_detail_missing_core_specs():
    engine_mock = MagicMock()
    scraper = LenovoBrandScraper(engine=engine_mock)

    summary = LaptopSummary(
        brand="Lenovo",
        name="Empty Lenovo Notebook",
        product_url="https://www.lenovo.com/eg/en/p/laptops/empty",
    )

    doc_mock = MagicMock()
    doc_mock.html = "<html><body>No specs published here</body></html>"
    doc_mock.markdown.return_value = "No specs"
    engine_mock.fetch.return_value = doc_mock

    res = scraper.get_laptop_detail(summary)
    assert res is None
    assert len(scraper.skipped_laptops) == 1
    assert "No hardware specs found" in scraper.skipped_laptops[0].reason


def test_lenovo_get_laptop_detail_and_configurations_success():
    engine_mock = MagicMock()
    scraper = LenovoBrandScraper(engine=engine_mock)

    summary = LaptopSummary(
        brand="Lenovo",
        name="Lenovo Legion Pro 5 16IRX9",
        product_url="https://www.lenovo.com/eg/en/p/laptops/legion-pro-5-16irx9/83df001hed",
        model="83DF001HED",
        family="Legion",
    )

    html_content = """
    <html>
    <head>
      <meta name="productid" content="83DF001HED">
      <meta name="processor" content="14th Generation Intel Core i7-14650HX Processor">
      <meta name="graphics" content="NVIDIA GeForce RTX 4060 8GB GDDR6">
      <meta name="memory" content="16 GB DDR5-5600MHz (SODIMM)">
      <meta name="hard_drive" content="1 TB SSD M.2 2280 PCIe Gen4 TLC">
      <meta name="display_type" content="16 inch WQXGA (2560 x 1600), IPS, 165Hz">
      <meta name="operating_system" content="Windows 11 Home">
    </head>
    <body>
      <div>Colors: Eclipse Black, Luna Grey</div>
      <img src="//p1-ofp.static.pub/gallery1.png">
      <div>Available MTM: 83DF001HED and 83DF0002ED</div>
    </body>
    </html>
    """

    doc_mock = MagicMock()
    doc_mock.html = html_content
    doc_mock.markdown.return_value = "Lenovo Legion Pro 5 16IRX9 specifications"
    engine_mock.fetch.return_value = doc_mock

    detail = scraper.get_laptop_detail(summary)
    assert detail is not None
    assert detail.brand == "Lenovo"
    assert detail.sku_part_number == "83DF001HED"
    assert detail.structured_specs["processor"] == "14th Generation Intel Core i7-14650HX Processor"
    assert detail.structured_specs["graphics"] == "NVIDIA GeForce RTX 4060 8GB GDDR6"
    assert detail.structured_specs["memory"] == "16 GB DDR5-5600MHz (SODIMM)"
    assert detail.structured_specs["storage"] == "1 TB SSD M.2 2280 PCIe Gen4 TLC"
    assert "83DF001HED" in detail.model_variants
    assert "83DF0002ED" in detail.model_variants
    assert len(detail.gallery_images) >= 1
    assert "gallery1.png" in detail.gallery_images[0]

    # Verify configurations expansion
    assert len(detail.configurations) >= 2
    cfg_models = [c.model for c in detail.configurations]
    assert "83DF001HED" in cfg_models
    assert "83DF0002ED" in cfg_models
    for c in detail.configurations:
        assert c.official_specs["Processor"] == "14th Generation Intel Core i7-14650HX Processor"
        assert c.official_specs["Graphics"] == "NVIDIA GeForce RTX 4060 8GB GDDR6"
