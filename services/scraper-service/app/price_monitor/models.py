from datetime import datetime, UTC
from enum import StrEnum
import uuid
from pydantic import BaseModel, Field


class PriceChangeType(StrEnum):
    """Classification of the price/stock transition for an offer."""

    PRICE_DROP = "PRICE_DROP"
    PRICE_HIKE = "PRICE_HIKE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    RESTOCKED = "RESTOCKED"
    UNCHANGED = "UNCHANGED"
    ERROR = "ERROR"


class PriceCheckItem(BaseModel):
    """Single laptop offer target to verify."""

    offer_id: str = Field(description="Unique UUID or identifier of the offer in catalog database")
    laptop_id: str = Field(description="Parent laptop configuration UUID")
    product_url: str = Field(description="Direct product page URL")
    current_price_egp: float = Field(description="Currently recorded price in EGP")
    current_in_stock: bool = Field(default=True, description="Currently recorded in-stock state")


class PriceCheckBatchRequest(BaseModel):
    """In-memory or message broker payload containing target offers for a single store partition."""

    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique batch execution ID")
    store_key: str = Field(description="Store slug (e.g. compumarts, sigma, elbadr)")
    store_name: str | None = Field(default=None, description="Human-friendly store name")
    items: list[PriceCheckItem] = Field(default_factory=list, description="Offers to check")


class PriceCheckItemResult(BaseModel):
    """Result of checking a single offer's live price and availability."""

    offer_id: str
    laptop_id: str
    product_url: str
    old_price_egp: float
    new_price_egp: float | None = None
    old_in_stock: bool
    new_in_stock: bool = True
    has_changed: bool = False
    change_type: PriceChangeType = PriceChangeType.UNCHANGED
    price_delta_egp: float = 0.0
    http_status: int | None = None
    error_message: str | None = None
    checked_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class PriceCheckBatchResponse(BaseModel):
    """Summary of batch verification results sent back to catalog service."""

    batch_id: str
    store_key: str
    total_items: int = 0
    changed_items_count: int = 0
    price_drops_count: int = 0
    price_hikes_count: int = 0
    out_of_stock_count: int = 0
    errors_count: int = 0
    duration_seconds: float = 0.0
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    results: list[PriceCheckItemResult] = Field(default_factory=list)
