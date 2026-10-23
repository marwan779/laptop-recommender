"""Data Models for Catalog Consolidation & Multi-Store Deduplication.

Defines schemas for:
  - StoreOffer: Individual retailer listing / pricing offer.
  - CanonicalLaptop: Deduplicated unified laptop entity with fused specs and offers.
  - UnifiedCatalog: Master multi-store consolidated catalog artifact.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def utcnow_str() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class StoreOffer(BaseModel):
    """An individual store's listing, price, and availability for a laptop."""

    store_key: str = Field(description="Unique store key (e.g. 'compumarts', 'elbadr', 'sigma')")
    store_name: str = Field(description="Display name of the retailer")
    store_domain: str | None = Field(default=None, description="Domain of the retailer")
    product_url: str = Field(description="Direct product page link")
    title: str = Field(description="Title of the product as displayed by the store")
    price_egp: float = Field(description="Price in Egyptian Pounds")
    price_str: str | None = Field(default=None, description="Formatted price string")
    in_stock: bool = Field(default=True, description="Whether the item is currently in stock")
    retailer_sku: str | None = Field(default=None, description="Retailer internal SKU or part number")
    mpn: str | None = Field(default=None, description="Extracted manufacturer part number")
    thumbnail_url: str | None = Field(default=None, description="Product image thumbnail URL")
    scraped_at: str = Field(default_factory=utcnow_str, description="Timestamp of when the offer was scraped")
    is_valid_price: bool = Field(
        default=True,
        description="False for placeholder/call-for-price amounts (e.g. <= 1000 EGP)",
    )


class CanonicalLaptop(BaseModel):
    """Consolidated, deduplicated laptop entity across multiple retail stores."""

    canonical_id: str = Field(description="Deterministic unique slug for this laptop configuration")
    mpn: str | None = Field(default=None, description="Manufacturer part number (e.g. 83DV01HSED)")
    brand: str = Field(description="Brand name (e.g. Lenovo, ASUS, HP, Acer)")
    laptop_family: str | None = Field(default=None, description="Laptop product family (e.g. LOQ, Legion, ROG)")
    laptop_model: str = Field(description="Canonical model code or name (e.g. LOQ 15IRX9)")
    title: str = Field(description="Clean primary display title")
    thumbnail_url: str | None = Field(default=None, description="Primary product image URL")

    # The richest, 12-category non-destructive specification dictionary
    specs: dict[str, Any] = Field(default_factory=dict, description="Consolidated 35+ specification fields")

    # Multi-store pricing and availability aggregation
    available_stores: list[str] = Field(
        default_factory=list,
        description="List of store keys offering this laptop (e.g. ['compumarts', 'sigma'])",
    )
    stores_count: int = Field(default=0, description="Total number of stores carrying this laptop")
    min_price_egp: float | None = Field(default=None, description="Cheapest available credible price in EGP")
    max_price_egp: float | None = Field(default=None, description="Highest available credible price in EGP")
    cheapest_store: str | None = Field(default=None, description="Store key providing the lowest price")
    price_spread_egp: float = Field(
        default=0.0,
        description="Price variance (max - min) in EGP across stores",
    )
    prices_by_store: dict[str, float] = Field(
        default_factory=dict,
        description="Direct mapping of store_key -> price_egp for rapid filtering",
    )
    offers: list[StoreOffer] = Field(
        default_factory=list,
        description="All individual store offers sorted from lowest price to highest",
    )

    created_at: str = Field(default_factory=utcnow_str, description="Timestamp of first ingestion")
    updated_at: str = Field(default_factory=utcnow_str, description="Timestamp of last consolidation")


class UnifiedCatalog(BaseModel):
    """Unified multi-store catalog artifact."""

    title: str = Field(default="Unified Multi-Store Laptop Catalog", description="Catalog title")
    generated_at: str = Field(default_factory=utcnow_str, description="Generation timestamp in UTC")
    stores_included: list[str] = Field(default_factory=list, description="Stores included in this aggregation")
    total_raw_listings: int = Field(default=0, description="Total raw store listings ingested across all files")
    total_unique_laptops: int = Field(default=0, description="Total deduplicated unique laptop entities")
    multi_store_laptops_count: int = Field(
        default=0,
        description="Number of laptops available in 2 or more stores simultaneously",
    )
    overlap_rate_pct: float = Field(
        default=0.0,
        description="Percentage of unique laptops found across multiple stores",
    )
    laptops: list[CanonicalLaptop] = Field(
        default_factory=list,
        description="Consolidated list of all canonical laptops",
    )

    def save_json(self, path: Path | str) -> Path:
        """Persist the unified catalog to disk as formatted JSON."""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
        return out_path
