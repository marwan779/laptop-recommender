"""Unit tests for domain schemas and data transfer models."""

import pytest
from pydantic import ValidationError

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
    """Verify RetailOffer schema representation."""
    offer = RetailOffer(
        store_name="Amazon Egypt",
        store_key="amazon_eg",
        store_domain="amazon.eg",
        title="MacBook Air M2",
        price_egp=48000.0,
        price_str="48,000 EGP",
        in_stock=True,
    )
    assert offer.store_name == "Amazon Egypt"
    assert offer.price_egp == 48000.0
    assert offer.in_stock is True
