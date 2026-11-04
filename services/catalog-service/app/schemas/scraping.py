from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ScrapeTriggerRequest(BaseModel):
    """Admin request to trigger a store scraping workflow."""

    store_key: str | Literal["all"] = Field(
        default="all",
        description="Target store key ('compumarts', 'elbadr', 'sigma') or 'all'",
    )
    level: int = Field(
        default=2,
        ge=1,
        le=2,
        description="Scraping depth: 1 = fast cards, 2 = full 35+ spec PDP crawl",
    )
    force_full_crawl: bool = Field(
        default=False,
        description="If True, ignores existing watermark pointers and runs a full catalog crawl",
    )
    send_email: bool = Field(
        default=False,
        description="Whether to dispatch summary email notification upon completion",
    )


class ScrapeTriggerResponse(BaseModel):
    """Acknowledgment response for a triggered scrape job."""

    job_id: str
    status: str = "QUEUED"
    message: str
    stores_targeted: list[str] = Field(default_factory=list)
    pointers_used: dict[str, list[str]] = Field(default_factory=dict)


class StorePointerResponse(BaseModel):
    """Live scraping watermark and checkpoint for a store."""

    store_key: str
    store_name: str
    store_domain: str | None = None
    latest_pointers: list[str] = Field(default_factory=list)
    last_scraped_at: datetime | None = None
    total_active_offers: int = 0
    scrape_interval_hours: int = 24
    is_active: bool = True
