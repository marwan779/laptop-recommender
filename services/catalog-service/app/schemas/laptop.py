import uuid
from pydantic import BaseModel, ConfigDict


class LaptopOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    store_name: str
    retailer_sku: str | None = None
    price_egp: float
    in_stock: bool
    offer_url: str | None = None


class LaptopCategoryScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usage_category_id: uuid.UUID
    score: float
    raw_percentile: float | None = None
    confidence: float | None = None
    notes: str | None = None


class LaptopConfigurationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_id: str | None = None
    manufacturer_part_number: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    min_price_egp: float | None = None
    max_price_egp: float | None = None
    cheapest_store: str | None = None
    price_spread_egp: float | None = None
    stores_count: int = 1
    hardware_score: float | None = None
    portability_score: float | None = None
    battery_hours_estimate: float | None = None
    upgradeability_score: float | None = None


class LaptopConfigurationDetail(LaptopConfigurationSummary):
    offers: list[LaptopOfferRead] = []
    category_scores: list[LaptopCategoryScoreRead] = []

