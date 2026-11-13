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
    """Single laptop offer target dispatched for verification."""

    offer_id: str
    laptop_id: str
    product_url: str
    current_price_egp: float
    current_in_stock: bool = True


class PriceCheckBatchRequest(BaseModel):
    """Batch payload dispatched to scraper-service partitioned by store."""

    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_key: str
    store_name: str | None = None
    items: list[PriceCheckItem] = Field(default_factory=list)


class PriceCheckItemResult(BaseModel):
    """Single offer verification result returned from scraper-service."""

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
    """Batch response payload returned from scraper-service."""

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


class PriceSyncSummary(BaseModel):
    """Execution summary returned after applying price monitoring updates in catalog database."""

    batch_id: str
    store_key: str
    total_processed: int = 0
    offers_updated: int = 0
    offers_unchanged: int = 0
    parent_laptops_recalculated: int = 0
    metrics_recalibrated: int = 0
    price_drops_detected: int = 0
    price_hikes_detected: int = 0
    out_of_stock_detected: int = 0
    affected_laptop_ids: list[uuid.UUID] = Field(default_factory=list, exclude=True)
