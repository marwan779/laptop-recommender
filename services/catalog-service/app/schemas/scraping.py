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


class ReviewsTriggerRequest(BaseModel):
    """Admin request to dispatch Stage 2 community review scraping."""

    force_all: bool = Field(
        default=False,
        description=("If True, resolves all catalog laptops into chassis targets even if has_reviews is already True."),
    )


class ReviewsTriggerResponse(BaseModel):
    """Acknowledgment returned when a review scraping batch is queued."""

    job_id: str
    status: str
    chassis_targets_queued: int = 0
    laptops_matched: int = 0
    message: str


class ReviewsIngestRequest(BaseModel):
    """Request to ingest an enriched chassis reviews artifact into ChromaDB and PostgreSQL."""

    source_path: str | None = Field(
        default=None,
        description=(
            "Optional local file path or S3 key; defaults to data/cleaned_and_enriched_chassis_reviews_v6.json."
        ),
    )
    from_s3: bool = Field(
        default=False,
        description="If True, read source_path from S3 object storage.",
    )


class ReviewsIngestResponse(BaseModel):
    """Result summary of a review intelligence ingestion run."""

    status: str
    chassis_processed: int = 0
    chroma_documents_upserted: int = 0
    sql_laptops_updated: int = 0
    duration_seconds: float = 0.0
