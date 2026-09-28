from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


def utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class MatchStatus(str, Enum):
    """Confidence level of matching a retailer product to an official configuration."""
    EXACT = "EXACT"
    PROBABLE = "PROBABLE"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


class MatchMethod(str, Enum):
    """The mechanism by which identity was established."""
    MPN = "MPN"
    FULL_SKU = "FULL_SKU"
    SUB_MODEL_SERIES = "SUB_MODEL_SERIES"
    BASE_MODEL_SPECS = "BASE_MODEL_SPECS"
    NONE = "NONE"


# =============================================================================
# Official Brand Schemas (Preserved for Level 1 / Level 2 Brand Scraping)
# =============================================================================

class LaptopSummary(BaseModel):
    """Level 1: Summary extracted from catalog listing page."""
    brand: str
    name: str
    price: str | None = None
    price_egp: float | None = None
    currency: str | None = "EGP"
    family: str | None = None
    model: str | None = None
    product_url: str
    specs_url: str | None = None
    store_url: str | None = None
    thumbnail_url: str | None = None
    release_date: str | None = None
    release_year: int | None = None
    scraped_at: str = Field(default_factory=utcnow_str)


class LaptopDetail(LaptopSummary):
    """Level 2: Deep crawl with every detail provided on the official spec sheet."""
    base_model: str | None = None
    model_variants: list[str] = Field(default_factory=list)
    sku_part_number: str | None = None
    copyright_year: int | None = None
    gallery_images: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    structured_specs: dict[str, str | None] = Field(default_factory=dict)
    all_specs: dict[str, str] = Field(default_factory=dict)
    spec_sections: dict[str, dict[str, str]] = Field(default_factory=dict)
    configurations: list[Any] = Field(default_factory=list)
    raw_markdown: str = ""
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class AsusBrandCatalogResult(BaseModel):
    """Top-level output schema for ASUS brand scraping, stored as a standalone JSON."""
    brand: str = "ASUS"
    official_catalog_url: str = "https://www.asus.com/eg-en/store/laptops/"
    scrape_mode: str = "level2"  # "level1" or "level2"
    until_model: str | None = None
    latest_pointers: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    total_laptops: int = 0
    total_configurations: int = 0
    scraped_at: str = Field(default_factory=utcnow_str)
    laptops: list[LaptopDetail | LaptopSummary] = Field(default_factory=list)


class LenovoBrandCatalogResult(BaseModel):
    """Top-level output schema for Lenovo brand scraping, stored as a standalone JSON."""
    brand: str = "Lenovo"
    official_catalog_url: str = "https://www.lenovo.com/eg/en/laptops/subseries-results/"
    scrape_mode: str = "level2"  # "level1" or "level2"
    until_model: str | None = None
    latest_pointers: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    total_laptops: int = 0
    total_configurations: int = 0
    scraped_at: str = Field(default_factory=utcnow_str)
    laptops: list[LaptopDetail | LaptopSummary] = Field(default_factory=list)


class HpBrandCatalogResult(BaseModel):
    """Top-level output schema for HP brand scraping, stored as a standalone JSON."""
    brand: str = "HP"
    official_catalog_url: str = "https://www.hp.com/emea_middle_east-en/products/laptops/view-all-laptops-and-2-in-1s.html?is_channeladvisor=yes"
    scrape_mode: str = "level2"  # "level1" or "level2"
    until_model: str | None = None
    latest_pointers: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    total_laptops: int = 0
    total_configurations: int = 0
    scraped_at: str = Field(default_factory=utcnow_str)
    laptops: list[LaptopDetail | LaptopSummary] = Field(default_factory=list)



# =============================================================================
# Retailer Normalized Products & Matches (Multi-Store Layer)
# =============================================================================

class RetailerProduct(BaseModel):
    """Normalized product extracted from a retailer website prior to matching."""
    store_name: str
    store_key: str
    store_domain: str
    title: str
    product_url: str
    retailer_product_id: str | None = None
    retailer_sku: str | None = None
    mpn: str | None = None  # Manufacturer Part Number (e.g. 90NB16J1-M00410)
    model_code: str | None = None  # Extracted full SKU if available (e.g. S3407CA-LY065W)
    sub_model: str | None = None  # Sub-model (e.g. S3407CA)
    base_model: str | None = None  # Base chassis (e.g. S3407)
    price_egp: float | None = None
    price_str: str | None = None
    in_stock: bool = True
    thumbnail_url: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    raw_description: str | None = None
    scraped_at: str = Field(default_factory=utcnow_str)


class StoreCatalogResult(BaseModel):
    """Top-level output schema for a retailer store crawl."""
    store_name: str
    store_key: str
    store_domain: str
    scrape_mode: str = "level2"
    until_model: str | None = None
    total_products: int = 0
    scraped_at: str = Field(default_factory=utcnow_str)
    products: list[RetailerProduct] = Field(default_factory=list)


class RetailOffer(BaseModel):
    """Retailer offer verified and attached to an exact official configuration."""
    store_name: str
    store_key: str
    store_domain: str
    title: str
    price_egp: float | None = None
    price_str: str | None = None
    in_stock: bool = True
    product_url: str
    thumbnail_url: str | None = None
    retailer_sku: str | None = None
    retailer_mpn: str | None = None
    match_status: MatchStatus = MatchStatus.UNKNOWN
    match_method: MatchMethod = MatchMethod.NONE
    match_confidence: float = 0.0
    match_reason: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    raw_description: str | None = None
    scraped_at: str = Field(default_factory=utcnow_str)


# Alias StoreOffer to RetailOffer for backward compatibility
StoreOffer = RetailOffer


# =============================================================================
# Hierarchical Aggregated Output Models:
# Brand -> ModelFamily -> Configuration / Exact SKU -> RetailOffer
# =============================================================================

class ConfigurationItem(BaseModel):
    """An exact physical configuration / SKU represented on the official catalog."""
    model: str  # Full SKU (e.g. 'S3407AA-SF117W') or sub-model series (e.g. 'S5452MA')
    model_series: str | None = None  # Sub-model code (e.g. 'S3407AA', 'S3407CA')
    base_model: str | None = None  # Base chassis model (e.g. 'S3407')
    mpn: str | None = None  # Official manufacturer part number if exposed
    official_specs: dict[str, str] = Field(default_factory=dict)
    stores: list[RetailOffer] = Field(default_factory=list)


class ModelFamily(BaseModel):
    """A product family line (e.g. 'ASUS Vivobook S14 (S3407)')."""
    name: str
    family: str | None = None
    base_model: str | None = None
    product_url: str
    specs_url: str | None = None
    thumbnail_url: str | None = None
    configurations: list[ConfigurationItem] = Field(default_factory=list)


class BrandStoreCatalog(BaseModel):
    """Top-level nested response: Brand -> Model Families -> Configurations -> Retail Offers."""
    brand: str
    official_catalog_url: str
    scraped_at: str = Field(default_factory=utcnow_str)
    total_families: int = 0
    total_configurations: int = 0
    total_store_offers: int = 0
    model_families: list[ModelFamily] = Field(default_factory=list)


# Alias LaptopWithStores to ModelFamily for backwards compatibility where needed
LaptopWithStores = ModelFamily
