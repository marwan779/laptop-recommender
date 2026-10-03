"""Unit tests for domain schemas, data models, and core normalizers."""

from pydantic import ValidationError
import pytest

from app.core.normalizer import ModelNormalizer
from app.matching.normalizer import ModelNormalizer as AliasedModelNormalizer
from app.schemas.laptop import (
    BrandCatalogResult,
    LaptopDetail,
    LaptopSummary,
    MatchMethod,
    MatchStatus,
    RetailOffer,
    RetailerProduct,
    SkippedLaptop,
    StoreCatalogResult,
)


def test_match_status_and_method_enum_values():
    """Verify MatchStatus and MatchMethod enum values conform to expectations."""
    assert MatchStatus.EXACT == "EXACT"
    assert MatchStatus.PROBABLE == "PROBABLE"
    assert MatchStatus.UNKNOWN == "UNKNOWN"
    assert MatchStatus.REJECTED == "REJECTED"

    assert MatchMethod.MPN == "MPN"
    assert MatchMethod.FULL_SKU == "FULL_SKU"
    assert MatchMethod.SUB_MODEL_SERIES == "SUB_MODEL_SERIES"
    assert MatchMethod.BASE_MODEL_SPECS == "BASE_MODEL_SPECS"
    assert MatchMethod.NONE == "NONE"


def test_laptop_summary_defaults_and_serialization():
    """Verify LaptopSummary default values and JSON serialization."""
    summary = LaptopSummary(
        brand="asus",
        name="ZenBook 14",
        product_url="https://asus.com/zenbook-14",
    )
    assert summary.brand == "asus"
    assert summary.name == "ZenBook 14"
    assert summary.currency == "EGP"
    assert summary.price_egp is None
    assert summary.scraped_at is not None

    data = summary.model_dump()
    assert data["brand"] == "asus"
    assert data["product_url"] == "https://asus.com/zenbook-14"


def test_laptop_detail_inheritance():
    """Verify LaptopDetail inherits all LaptopSummary fields and adds detail fields."""
    detail = LaptopDetail(
        brand="lenovo",
        name="Legion Pro 7",
        product_url="https://lenovo.com/legion-pro-7",
        base_model="Legion Pro 7 16IRX8H",
        model_variants=["82WQ002RUS", "82WQ002SUS"],
        specs_url="https://psref.lenovo.com/Product/Legion_Pro_7",
    )
    assert detail.brand == "lenovo"
    assert detail.base_model == "Legion Pro 7 16IRX8H"
    assert len(detail.model_variants) == 2
    assert detail.model_variants[0] == "82WQ002RUS"
    assert detail.specs_url == "https://psref.lenovo.com/Product/Legion_Pro_7"


def test_skipped_laptop_schema():
    """Verify SkippedLaptop stores structured debugging info."""
    skipped = SkippedLaptop(
        name="Mystery Laptop",
        url="https://example.com/item/123",
        reason="HTTP 404 Not Found",
        stage="spec_fetching",
    )
    assert skipped.name == "Mystery Laptop"
    assert skipped.url == "https://example.com/item/123"
    assert skipped.reason == "HTTP 404 Not Found"
    assert skipped.stage == "spec_fetching"
    assert skipped.scraped_at is not None


def test_retailer_product_schema():
    """Verify RetailerProduct schema handles pricing and stock status."""
    product = RetailerProduct(
        store_name="B.TECH",
        store_key="btech",
        store_domain="btech.com",
        title="Dell Inspiron 15 3520",
        product_url="https://btech.com/dell-inspiron-15",
        price_egp=24500.0,
        in_stock=True,
    )
    assert product.store_name == "B.TECH"
    assert product.price_egp == 24500.0
    assert product.in_stock is True
    assert product.specs == {}


def test_brand_catalog_result_aggregation():
    """Verify BrandCatalogResult aggregates summaries and skipped laptops."""
    summary = LaptopSummary(
        brand="hp",
        name="HP Pavilion 15",
        product_url="https://hp.com/pavilion-15",
    )
    skipped = SkippedLaptop(
        name="HP Omen Obsolete",
        reason="Product Discontinued",
    )
    catalog = BrandCatalogResult(
        brand="hp",
        official_catalog_url="https://hp.com/catalogs",
        total_laptops=1,
        total_skipped=1,
        laptops=[summary],
        skipped_laptops=[skipped],
    )
    assert catalog.brand == "hp"
    assert len(catalog.laptops) == 1
    assert len(catalog.skipped_laptops) == 1
    assert catalog.scrape_mode == "level2"


def test_store_catalog_result_aggregation():
    """Verify StoreCatalogResult aggregates store items."""
    product = RetailerProduct(
        store_name="2B",
        store_key="twob",
        store_domain="2b.com.eg",
        title="Acer Aspire 3",
        product_url="https://2b.com.eg/acer-aspire-3",
    )
    catalog = StoreCatalogResult(
        store_name="2B",
        store_key="twob",
        store_domain="2b.com.eg",
        total_products=1,
        products=[product],
    )
    assert catalog.store_key == "twob"
    assert len(catalog.products) == 1
    assert catalog.products[0].title == "Acer Aspire 3"


def test_retail_offer_schema():
    """Verify RetailOffer schema validation and fields."""
    offer = RetailOffer(
        store_name="Amazon Egypt",
        store_key="amazon_eg",
        store_domain="amazon.eg",
        title="MacBook Air M2",
        product_url="https://amazon.eg/dp/B0B3C9B8",
        price_egp=48000.0,
        price_str="48,000 EGP",
        in_stock=True,
    )
    assert offer.store_name == "Amazon Egypt"
    assert offer.product_url == "https://amazon.eg/dp/B0B3C9B8"
    assert offer.price_egp == 48000.0
    assert offer.in_stock is True


def test_retail_offer_missing_required_url_raises():
    """Verify RetailOffer requires product_url and raises ValidationError if omitted."""
    with pytest.raises(ValidationError):
        RetailOffer(
            store_name="Amazon Egypt",
            store_key="amazon_eg",
            store_domain="amazon.eg",
            title="Incomplete Laptop",
        )


# =============================================================================
# ModelNormalizer Tests
# =============================================================================


def test_model_normalizer_arabic_numerals():
    """Verify Eastern Arabic numeral normalization."""
    assert ModelNormalizer.normalize_arabic_numerals("كمبيوتر ١٥ بوصة") == "كمبيوتر 15 بوصة"
    assert ModelNormalizer.normalize_arabic_numerals("") == ""
    assert ModelNormalizer.normalize_arabic_numerals(None) == ""


def test_model_normalizer_clean_noisy_title():
    """Verify removal of marketing buzzwords in Arabic and English."""
    noisy = "Asus ZenBook 14 Brand New Special Offer ضمان محلي"
    cleaned = ModelNormalizer.clean_noisy_title(noisy)
    assert "Brand New" not in cleaned
    assert "Special Offer" not in cleaned
    assert "ضمان محلي" not in cleaned
    assert "Asus ZenBook 14" in cleaned
    assert ModelNormalizer.clean_noisy_title(None) == ""


def test_model_normalizer_token_and_mpn():
    """Verify token stripping and MPN extraction."""
    assert ModelNormalizer.normalize_token("S3407CA - LY065W") == "s3407caly065w"
    assert ModelNormalizer.normalize_token(None) == ""

    assert ModelNormalizer.normalize_mpn("Part: 90NB16J1-M00410 in stock") == "90NB16J1-M00410"
    assert ModelNormalizer.normalize_mpn(None) is None


def test_model_normalizer_extract_model_tokens():
    """Verify token extraction from title containing SKU."""
    text = "ASUS Vivobook S 14 OLED S3407CA-LY065W Intel Core Ultra 7"
    tokens = ModelNormalizer.extract_model_tokens(text)
    assert tokens["full_sku"] == "S3407CA-LY065W"
    assert tokens["sub_model"] == "S3407CA"
    assert tokens["base_model"] == "S3407"

    # Test empty input handling
    empty_tokens = ModelNormalizer.extract_model_tokens(None)
    assert empty_tokens["full_sku"] is None

    # Test base model extraction
    base_model = ModelNormalizer.extract_base_model(text)
    assert base_model == "S3407"
    assert ModelNormalizer.extract_base_model(None) is None


def test_aliased_model_normalizer_import():
    """Verify normalizer can be imported from app.matching.normalizer."""
    assert AliasedModelNormalizer is ModelNormalizer
