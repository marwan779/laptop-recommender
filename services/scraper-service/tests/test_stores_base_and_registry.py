"""Unit tests for app.stores.base (BaseStoreScraper) and app.stores.registry."""

from unittest.mock import MagicMock
import pytest

from app.engine.base import IScraperEngine
from app.schemas.laptop import ConfigurationItem, RetailerProduct, SkippedLaptop
from app.stores.base import BaseStoreScraper
from app.stores.registry import STORE_REGISTRY, get_all_store_scrapers, get_store_scraper


class ConcreteStoreScraper(BaseStoreScraper):
    """Concrete subclass of BaseStoreScraper for testing base methods."""

    @property
    def store_name(self) -> str:
        return "Test Store"

    @property
    def store_key(self) -> str:
        return "test_store"

    @property
    def base_url(self) -> str:
        return "https://www.teststore.com.eg"

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        if query == "fail_query":
            raise RuntimeError("Network search failure")
        return [
            RetailerProduct(
                store_name=self.store_name,
                store_key=self.store_key,
                store_domain=self.base_domain,
                title=f"Result for {query}",
                product_url=f"https://teststore.com.eg/p/{query}",
            )
        ]


# =============================================================================
# 1. BaseStoreScraper Property & Abstract Fallback Tests
# =============================================================================


def test_base_store_scraper_base_domain_computation():
    """Verify base_domain strips 'www.' from netloc."""
    scraper = ConcreteStoreScraper()
    assert scraper.base_domain == "teststore.com.eg"
    assert scraper.store_name == "Test Store"
    assert scraper.store_key == "test_store"


def test_base_store_scraper_default_scrape_catalog():
    """Verify default scrape_catalog delegates to search_candidates with query='laptop'."""
    scraper = ConcreteStoreScraper()
    results = scraper.scrape_catalog(limit=10)
    assert len(results) == 1
    assert results[0].title == "Result for laptop"


def test_base_store_scraper_record_skipped():
    """Verify record_skipped appends structured SkippedLaptop."""
    scraper = ConcreteStoreScraper()
    scraper.record_skipped(
        name="Accessory Sleeve",
        reason="Filtered out non-laptop accessory",
        url="https://teststore.com.eg/sleeve",
        error=None,
        stage="level1_filter",
    )
    assert len(scraper.skipped_laptops) == 1
    s = scraper.skipped_laptops[0]
    assert s.name == "Accessory Sleeve"
    assert s.reason == "Filtered out non-laptop accessory"
    assert s.stage == "level1_filter"


# =============================================================================
# 2. Accessory Filtering Logic (_is_standalone_accessory)
# =============================================================================


def test_is_standalone_accessory_laptop_bundles_and_specs():
    """Verify products with CPU and hardware specs are NOT classified as standalone accessories."""
    # Laptop with accessory in title (e.g. includes bag or mouse)
    title_bundle = "Lenovo Legion 5 Intel Core i7 16GB RAM 512GB SSD RTX 4060 With Free Backpack"
    assert ConcreteStoreScraper._is_standalone_accessory(title_bundle) is False

    # Laptop with keyboard mentioned in specs
    title_keyboard_laptop = "Dell Inspiron 15 Core i5 8GB RAM 256GB SSD Backlit Keyboard Arabic"
    assert ConcreteStoreScraper._is_standalone_accessory(title_keyboard_laptop) is False

    # Standalone keyboard without layout/backlit keywords
    title_standalone_keyboard = "Logitech Wireless Keyboard K120 USB"
    assert ConcreteStoreScraper._is_standalone_accessory(title_standalone_keyboard) is True

    # Keyboard layout/arabic mentioned without CPU still bypasses keyboard check by design
    title_keyboard_layout = "Laptop Keyboard Arabic Layout Replacement"
    assert ConcreteStoreScraper._is_standalone_accessory(title_keyboard_layout) is False

    # Pure accessory without CPU/specs
    assert ConcreteStoreScraper._is_standalone_accessory("Samsung 27 Inch Gaming Monitor") is True
    assert ConcreteStoreScraper._is_standalone_accessory("HP Wireless Mouse 200 Black") is True
    assert ConcreteStoreScraper._is_standalone_accessory("Laptop Cooling Pad with 5 Fans") is True
    assert ConcreteStoreScraper._is_standalone_accessory("Sandisk Flash Drive 64GB USB 3.0") is True
    assert ConcreteStoreScraper._is_standalone_accessory("Samsung 27 Inch Monitor 144Hz") is True


# =============================================================================
# 3. Watermark Matching Logic (_matches_watermark)
# =============================================================================


def test_matches_watermark_single_and_list():
    """Verify watermark matching against strings and lists with punctuation variance."""
    assert ConcreteStoreScraper._matches_watermark("ASUS ZenBook UX3402VA", "UX3402") is True
    assert ConcreteStoreScraper._matches_watermark("ASUS ZenBook UX3402VA", "ux-3402") is True
    assert ConcreteStoreScraper._matches_watermark("ASUS ZenBook UX3402VA", ["OtherModel", "UX3402"]) is True

    # No match
    assert ConcreteStoreScraper._matches_watermark("Dell XPS 13", "S5406") is False

    # Empty inputs
    assert ConcreteStoreScraper._matches_watermark(None, "UX3402") is False
    assert ConcreteStoreScraper._matches_watermark("Dell XPS 13", None) is False
    assert ConcreteStoreScraper._matches_watermark("Dell XPS 13", ["", None]) is False


# =============================================================================
# 4. Query Construction (build_candidate_queries)
# =============================================================================


def test_build_candidate_queries_prioritization_and_dedup():
    """Verify build_candidate_queries builds prioritized and deduplicated search queries."""
    cfg1 = ConfigurationItem(
        model="S3407CA-LY065W",
        model_series="S3407CA",
        mpn="90NB16J1-M00410",
        official_specs={},
    )
    cfg2 = ConfigurationItem(
        model="S3407AA",
        model_series="S3407AA",  # Same as model, shouldn't duplicate
        mpn=None,
        official_specs={},
    )

    queries = ConcreteStoreScraper.build_candidate_queries(
        brand="ASUS",
        family_name="Vivobook S 14 (S3407)",
        base_model="S3407",
        configurations=[cfg1, cfg2],
    )

    # Must contain full SKU, sub-model, MPN, base model, family
    assert "S3407CA-LY065W" in queries
    assert "ASUS S3407CA-LY065W" in queries
    assert "S3407CA" in queries
    assert "90NB16J1-M00410" in queries
    assert "ASUS S3407" in queries
    assert "S3407" in queries
    assert "Vivobook S 14 S3407" in queries
    assert "Vivobook S 14" in queries

    # Order preserved and no duplicates
    assert len(queries) == len(set(q.lower() for q in queries))


# =============================================================================
# 5. Candidate Collection & Deduplication (collect_store_candidates)
# =============================================================================


def test_collect_store_candidates_resilient_to_query_errors():
    """Verify collect_store_candidates continues through query errors and respects max_candidates."""
    scraper = ConcreteStoreScraper()
    queries = ["q1", "fail_query", "q2", "q3"]

    candidates = scraper.collect_store_candidates(queries=queries, max_candidates=2)
    assert len(candidates) == 2
    assert candidates[0].title == "Result for q1"
    assert candidates[1].title == "Result for q2"


def test_deduplicate_candidates_by_url_sku_and_mpn():
    """Verify deduplicate_candidates removes duplicate products matching by URL, ID, or SKU."""
    p1 = RetailerProduct(
        store_name="Store",
        store_key="store",
        store_domain="store.com",
        title="Laptop A",
        product_url="https://store.com/p/item1?ref=search",
        retailer_product_id="ID-100",
        retailer_sku="SKU-100",
        mpn="90NB16J1-M00410",
    )
    # Duplicate by URL (different query params)
    p2 = RetailerProduct(
        store_name="Store",
        store_key="store",
        store_domain="store.com",
        title="Laptop A Copy",
        product_url="https://store.com/p/item1?other=param",
        retailer_product_id="ID-999",
    )
    # Duplicate by SKU
    p3 = RetailerProduct(
        store_name="Store",
        store_key="store",
        store_domain="store.com",
        title="Laptop B",
        product_url="https://store.com/p/item2",
        retailer_sku="SKU-100",
    )
    # Unique product
    p4 = RetailerProduct(
        store_name="Store",
        store_key="store",
        store_domain="store.com",
        title="Laptop C",
        product_url="https://store.com/p/item3",
        retailer_sku="SKU-300",
    )

    deduped = ConcreteStoreScraper.deduplicate_candidates([p1, p2, p3, p4])
    assert len(deduped) == 2
    assert deduped[0].title == "Laptop A"
    assert deduped[1].title == "Laptop C"


# =============================================================================
# 6. EGP Price Parsing Logic (parse_egp_price)
# =============================================================================


def test_parse_egp_price_formats():
    """Verify parse_egp_price handles various Egyptian retail price formats and Arabic numerals."""
    # Standard formats
    val, text = ConcreteStoreScraper.parse_egp_price("54,999.00 EGP")
    assert val == 54999.0
    assert text == "54,999.00 EGP"

    val, text = ConcreteStoreScraper.parse_egp_price("EGP 24,500")
    assert val == 24500.0
    assert text == "24,500.00 EGP"

    # Eastern Arabic numerals (٥٤٩٩٩)
    val, text = ConcreteStoreScraper.parse_egp_price("٥٤,٩٩٩ ج.م")
    assert val == 54999.0
    assert text == "54,999.00 EGP"

    # Egyptian Pound text
    val, text = ConcreteStoreScraper.parse_egp_price("جنيه 18,250")
    assert val == 18250.0
    assert text == "18,250.00 EGP"

    # None or empty
    assert ConcreteStoreScraper.parse_egp_price(None) == (None, None)
    assert ConcreteStoreScraper.parse_egp_price("") == (None, None)

    # No digits present
    val_nodigits, text_nodigits = ConcreteStoreScraper.parse_egp_price("Call for price")
    assert val_nodigits is None
    assert text_nodigits == "Call for price"


# =============================================================================
# 7. Store Registry Tests (app.stores.registry)
# =============================================================================


def test_store_registry_contains_all_eight_stores():
    """Verify STORE_REGISTRY contains exactly the 8 supported Egyptian stores."""
    expected_stores = {
        "compumarts",
        "elbadr",
        "sigma",
        "twob",
        "tradeline",
        "amazon",
        "noon",
        "btech",
    }
    assert set(STORE_REGISTRY.keys()) == expected_stores


def test_get_store_scraper_case_insensitive():
    """Verify get_store_scraper instantiates scraper with case-insensitive key."""
    engine = MagicMock(spec=IScraperEngine)
    scraper_upper = get_store_scraper("BTECH", engine=engine)
    assert scraper_upper.store_key == "btech"

    scraper_mixed = get_store_scraper("CompuMarts", engine=engine)
    assert scraper_mixed.store_key == "compumarts"


def test_get_store_scraper_unknown_key_raises_value_error():
    """Verify get_store_scraper raises ValueError when given an unknown store key."""
    engine = MagicMock(spec=IScraperEngine)
    with pytest.raises(ValueError, match="Unknown store 'invalid_store'"):
        get_store_scraper("invalid_store", engine=engine)


def test_get_all_store_scrapers_returns_all_instances():
    """Verify get_all_store_scrapers instantiates and returns all 8 store scrapers."""
    engine = MagicMock(spec=IScraperEngine)
    all_scrapers = get_all_store_scrapers(engine=engine)
    assert len(all_scrapers) == 8
    keys = {s.store_key for s in all_scrapers}
    assert "btech" in keys
    assert "amazon" in keys
    assert "noon" in keys
    assert "twob" in keys
    assert "tradeline" in keys
    assert "sigma" in keys
    assert "compumarts" in keys
    assert "elbadr" in keys
