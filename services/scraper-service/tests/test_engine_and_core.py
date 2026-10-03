"""Unit tests for app.core.constants, app.core.normalizer, app.engine.base, and app.engine.scrapling_engine."""

from unittest.mock import MagicMock, patch
import pytest

from app.core.constants import BRAND_CATALOGS, BrandConfig
from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine, ScrapedDocument
from app.engine.scrapling_engine import ScraplingEngine


# =============================================================================
# 1. Constants Tests
# =============================================================================


def test_brand_catalogs_structure_and_keys():
    """Verify BRAND_CATALOGS contains all standard brands with valid schema."""
    expected_brands = {"asus", "lenovo", "hp", "dell", "acer", "gigabyte"}
    assert set(BRAND_CATALOGS.keys()) == expected_brands

    for brand_key, config in BRAND_CATALOGS.items():
        assert isinstance(config["name"], str)
        assert len(config["name"]) > 0
        assert config["slug"] == brand_key
        assert config["catalog_url"].startswith("https://")
        assert isinstance(config["region"], str)
        assert len(config["region"]) > 0


def test_brand_catalogs_specific_brand_values():
    """Verify specific brand configurations match expected portal URLs and regions."""
    asus_cfg = BRAND_CATALOGS["asus"]
    assert asus_cfg["name"] == "ASUS"
    assert asus_cfg["catalog_url"] == "https://www.asus.com/eg-en/store/laptops/"
    assert asus_cfg["region"] == "eg-en"

    gigabyte_cfg = BRAND_CATALOGS["gigabyte"]
    assert gigabyte_cfg["name"] == "GigaByte"
    assert gigabyte_cfg["catalog_url"] == "https://www.gigabyte.com/Laptop/All-Series"
    assert gigabyte_cfg["region"] == "eg"

    hp_cfg = BRAND_CATALOGS["hp"]
    assert hp_cfg["name"] == "HP"
    assert "channeladvisor" in hp_cfg["catalog_url"]
    assert hp_cfg["region"] == "emea_middle_east-en"


# =============================================================================
# 2. ModelNormalizer Additional Coverage & Mutation Resistance
# =============================================================================


def test_model_normalizer_mpn_fallback_branches():
    """Verify normalize_mpn handles fallback cleaning when MPN_REGEX does not match."""
    # Matches '90' prefix with >= 12 chars without dash/space
    mpn_raw = "90NB16J1M00410XYZ"
    assert ModelNormalizer.normalize_mpn(mpn_raw) == "90NB16J1M00410XYZ"

    # With spaces and underscores
    mpn_underscores = "  90NB_16J1_M00410_XYZ  "
    assert ModelNormalizer.normalize_mpn(mpn_underscores) == "90NB16J1M00410XYZ"

    # Starts with 90 but length < 12 (boundary check)
    assert ModelNormalizer.normalize_mpn("90NB12345") is None

    # Length >= 12 but does NOT start with 90
    assert ModelNormalizer.normalize_mpn("80NB16J1M00410XYZ") is None

    # Empty / whitespace
    assert ModelNormalizer.normalize_mpn("   ") is None


def test_model_normalizer_extract_base_model_sub_model_and_bm_branches():
    """Verify extract_base_model fallback to sub-model and base-model regexes."""
    # Text where full SKU regex doesn't match, but sub-model regex matches (e.g. S3407CA)
    text_sub = "Laptop Model S3407CA Ultra Thin"
    assert ModelNormalizer.extract_base_model(text_sub) == "S3407"

    # Text where sub-model regex matches but chassis prefix doesn't
    text_sub_no_chassis = "Laptop Model FA506QM Gaming"
    assert ModelNormalizer.extract_base_model(text_sub_no_chassis) == "FA506"

    # Text where full SKU and sub-model do not match, but base model regex matches (e.g. UX3402)
    text_base_only = "Laptop Model UX3402 Series"
    assert ModelNormalizer.extract_base_model(text_base_only) == "UX3402"

    # Text with no matching model tokens
    assert ModelNormalizer.extract_base_model("Generic Laptop Computer") is None
    assert ModelNormalizer.extract_base_model("") is None


def test_model_normalizer_extract_model_tokens_branches():
    """Verify extract_model_tokens handles sub-model loop and base-model only text."""
    # Text with sub-model without hyphen (e.g. 'FA507NV')
    text_sub = "ASUS TUF Gaming A15 FA507NV Gaming Laptop"
    tokens_sub = ModelNormalizer.extract_model_tokens(text_sub)
    assert tokens_sub["sub_model"] == "FA507NV"
    assert tokens_sub["base_model"] == "FA507"
    assert tokens_sub["full_sku"] is None

    # Text with base model only (e.g. 'UX3402')
    text_base = "ASUS ZenBook UX3402 Slim"
    tokens_base = ModelNormalizer.extract_model_tokens(text_base)
    assert tokens_base["base_model"] == "UX3402"
    assert tokens_base["sub_model"] is None
    assert tokens_base["full_sku"] is None

    # Sub-model candidate with no digits or no letters (< 5 chars or all alpha/digits)
    text_invalid_sub = "Laptop ABCDE or 12345"
    tokens_invalid = ModelNormalizer.extract_model_tokens(text_invalid_sub)
    assert tokens_invalid["sub_model"] is None


# =============================================================================
# 3. ScrapedDocument Tests (app.engine.base)
# =============================================================================


class FakeElement:
    """Mock DOM element for testing ScrapedDocument parsing."""

    def __init__(self, text: str = "", attrib: dict | None = None):
        self.text = text
        self.attrib = attrib or {}


class FakeRawPage:
    """Mock page object with css, xpath, and markdown methods."""

    def __init__(self, css_map=None, xpath_map=None, md_text="## Sample Markdown"):
        self.css_map = css_map or {}
        self.xpath_map = xpath_map or {}
        self.md_text = md_text

    def css(self, selector: str):
        return self.css_map.get(selector, [])

    def xpath(self, selector: str):
        return self.xpath_map.get(selector, [])

    def markdown(self):
        return self.md_text


def test_scraped_document_defaults_and_raw_fallback():
    """Verify ScrapedDocument defaults and fallback behavior when raw is None."""
    doc = ScrapedDocument(url="https://example.com", status_code=200, html="<html></html>")
    assert doc.url == "https://example.com"
    assert doc.status_code == 200
    assert doc.html == "<html></html>"
    assert doc.raw is None
    assert doc.captured_xhr == []

    # When raw is None, helper methods return safe empty defaults
    assert doc.css(".item") == []
    assert doc.xpath("//div") == []
    assert doc.markdown() == ""
    assert doc.get_meta("description") is None
    assert doc.get_json_ld() == []


def test_scraped_document_css_xpath_markdown_delegation():
    """Verify ScrapedDocument delegates to raw object when methods exist."""
    raw = FakeRawPage(
        css_map={".title": [FakeElement("Laptop Pro")]},
        xpath_map={"//title": [FakeElement("Page Title")]},
        md_text="# Markdown Content",
    )
    doc = ScrapedDocument(url="https://example.com", status_code=200, html="", raw=raw)

    assert doc.css(".title")[0].text == "Laptop Pro"
    assert doc.xpath("//title")[0].text == "Page Title"
    assert doc.markdown() == "# Markdown Content"


def test_scraped_document_get_meta_extraction():
    """Verify get_meta extracts content from name and property meta tags with whitespace stripping."""
    meta_name_el = FakeElement(attrib={"content": "  High-performance laptop  "})
    meta_prop_el = FakeElement(attrib={"content": "  OpenGraph Title  "})
    meta_empty_el = FakeElement(attrib={"content": ""})
    meta_no_attrib = FakeElement(attrib={})

    selector = 'meta[name="description"], meta[property="description"]'
    raw = FakeRawPage(css_map={selector: [meta_name_el]})
    doc = ScrapedDocument(url="https://example.com", status_code=200, html="", raw=raw)

    assert doc.get_meta("description") == "High-performance laptop"

    # OpenGraph property tag
    og_selector = 'meta[name="og:title"], meta[property="og:title"]'
    raw_og = FakeRawPage(css_map={og_selector: [meta_prop_el]})
    doc_og = ScrapedDocument(url="https://example.com", status_code=200, html="", raw=raw_og)
    assert doc_og.get_meta("og:title") == "OpenGraph Title"

    # Meta tag exists but content is empty string or attribute missing
    raw_empty = FakeRawPage(css_map={selector: [meta_empty_el, meta_no_attrib]})
    doc_empty = ScrapedDocument(url="https://example.com", status_code=200, html="", raw=raw_empty)
    assert doc_empty.get_meta("description") is None


def test_scraped_document_get_json_ld_parsing():
    """Verify get_json_ld parses both JSON objects and JSON arrays and skips invalid JSON."""
    ld_selector = 'script[type="application/ld+json"]'

    script_obj = FakeElement(text='{"@type": "Product", "name": "ASUS ZenBook"}')
    script_arr = FakeElement(text='[{"@type": "Offer", "price": "1500"}, {"@type": "Offer", "price": "1600"}]')
    script_invalid = FakeElement(text='{not valid json}')
    script_empty = FakeElement(text='   ')

    raw = FakeRawPage(css_map={ld_selector: [script_obj, script_arr, script_invalid, script_empty]})
    doc = ScrapedDocument(url="https://example.com", status_code=200, html="", raw=raw)

    data = doc.get_json_ld()
    assert len(data) == 3
    assert data[0]["name"] == "ASUS ZenBook"
    assert data[1]["price"] == "1500"
    assert data[2]["price"] == "1600"


# =============================================================================
# 4. ScraplingEngine Tests (app.engine.scrapling_engine)
# =============================================================================


def test_scrapling_engine_init():
    """Verify ScraplingEngine constructor stores default_impersonate."""
    engine_default = ScraplingEngine()
    assert engine_default.default_impersonate == "chrome"

    engine_firefox = ScraplingEngine(default_impersonate="firefox")
    assert engine_firefox.default_impersonate == "firefox"


def test_scrapling_engine_fetch_stealth_success():
    """Verify fetch(stealth=True) calls StealthyFetcher with expected kwargs and builds ScrapedDocument."""
    engine = ScraplingEngine()

    mock_page = MagicMock()
    mock_page.html_content = "<html>Stealth Content</html>"
    mock_page.status = 200
    mock_page.captured_xhr = [{"url": "https://api.example.com/xhr"}]

    with patch("app.engine.scrapling_engine.StealthyFetcher.fetch", return_value=mock_page) as mock_fetch:
        doc = engine.fetch(
            url="https://target.com/page",
            stealth=True,
            network_idle=True,
            wait_selector=".loaded",
            disable_resources=True,
            timeout=30000,
        )

        mock_fetch.assert_called_once_with(
            "https://target.com/page",
            headless=True,
            network_idle=True,
            timeout=30000,
            wait_selector=".loaded",
            disable_resources=True,
        )
        assert doc.url == "https://target.com/page"
        assert doc.status_code == 200
        assert doc.html == "<html>Stealth Content</html>"
        assert doc.captured_xhr == [{"url": "https://api.example.com/xhr"}]
        assert doc.raw == mock_page


def test_scrapling_engine_fetch_stealth_body_bytes_fallback():
    """Verify fetch(stealth=True) decodes body bytes when html_content is None."""
    engine = ScraplingEngine()

    mock_page = MagicMock()
    mock_page.html_content = None
    mock_page.body = b"<html>Body Decoded</html>"
    mock_page.status = 200
    mock_page.captured_xhr = []

    with patch("app.engine.scrapling_engine.StealthyFetcher.fetch", return_value=mock_page):
        doc = engine.fetch("https://target.com/bytes", stealth=True)
        assert doc.html == "<html>Body Decoded</html>"


def test_scrapling_engine_fetch_non_stealth_fetcher_session():
    """Verify fetch(stealth=False) uses FetcherSession context manager and passes correct timeout in seconds."""
    engine = ScraplingEngine(default_impersonate="chrome120")

    mock_page = MagicMock()
    mock_page.html_content = "<html>Standard HTTP Content</html>"
    mock_page.status = 200

    mock_session = MagicMock()
    mock_session.get.return_value = mock_page
    mock_session_cls = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session

    with patch("app.engine.scrapling_engine.FetcherSession", mock_session_cls):
        doc = engine.fetch("https://target.com/standard", stealth=False, timeout=25000)

        mock_session_cls.assert_called_once_with(impersonate="chrome120")
        mock_session.get.assert_called_once_with(
            "https://target.com/standard",
            stealthy_headers=True,
            timeout=25.0,  # 25000 / 1000
        )
        assert doc.url == "https://target.com/standard"
        assert doc.status_code == 200
        assert doc.html == "<html>Standard HTTP Content</html>"


def test_scrapling_engine_fetch_non_stealth_text_fallback():
    """Verify fetch(stealth=False) falls back to text or str(page) when html_content and body are empty."""
    engine = ScraplingEngine()

    mock_page = MagicMock()
    mock_page.html_content = None
    mock_page.body = None
    mock_page.text = "Text only content"
    mock_page.status = 200

    mock_session = MagicMock()
    mock_session.get.return_value = mock_page
    mock_session_cls = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session

    with patch("app.engine.scrapling_engine.FetcherSession", mock_session_cls):
        doc = engine.fetch("https://target.com/text", stealth=False)
        assert doc.html == "Text only content"


def test_scrapling_engine_fetch_non_stealth_body_bytes_fallback():
    """Verify fetch(stealth=False) decodes body bytes when html_content is None."""
    engine = ScraplingEngine()

    mock_page = MagicMock()
    mock_page.html_content = None
    mock_page.body = b"<html>Body Bytes in Non-Stealth</html>"
    mock_page.status = 200

    mock_session = MagicMock()
    mock_session.get.return_value = mock_page
    mock_session_cls = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session

    with patch("app.engine.scrapling_engine.FetcherSession", mock_session_cls):
        doc = engine.fetch("https://target.com/bytes-non-stealth", stealth=False)
        assert doc.html == "<html>Body Bytes in Non-Stealth</html>"


def test_scrapling_engine_fetch_stealth_str_page_fallback():
    """Verify fetch(stealth=True) falls back to str(page) when html_content, body, and text are empty."""
    engine = ScraplingEngine()

    class EmptyPage:
        html_content = None
        body = None
        text = ""
        status = 200
        captured_xhr = []

        def __str__(self):
            return "<html>Stringified Page</html>"

    with patch("app.engine.scrapling_engine.StealthyFetcher.fetch", return_value=EmptyPage()):
        doc = engine.fetch("https://target.com/str-fallback", stealth=True)
        assert doc.html == "<html>Stringified Page</html>"


def test_scrapling_engine_fetch_json():
    """Verify fetch_json uses FetcherSession and returns parsed json dictionary."""
    engine = ScraplingEngine(default_impersonate="chrome")

    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ok", "items": [1, 2, 3]}

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_session_cls = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session

    with patch("app.engine.scrapling_engine.FetcherSession", mock_session_cls):
        data = engine.fetch_json("https://target.com/api/data.json")

        mock_session_cls.assert_called_once_with(impersonate="chrome")
        mock_session.get.assert_called_once_with("https://target.com/api/data.json", stealthy_headers=True)
        assert data == {"status": "ok", "items": [1, 2, 3]}
