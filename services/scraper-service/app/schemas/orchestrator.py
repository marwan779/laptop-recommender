"""DTOs for the Scrape Orchestrator — the unified abstraction layer.

These models are the contract between any caller (CLI, FastAPI controller,
catalog-service cron job) and the ScrapeOrchestrator.
"""

from __future__ import annotations

from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.laptop import BrandCatalogResult, StoreCatalogResult, utcnow_str


# ─── Request DTO ────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    """Describes *what* to scrape and *how*.

    Attributes:
        target_type: ``"brand"`` to scrape official brand portals (ASUS, HP, …),
                     ``"store"`` to scrape Egyptian retail stores (Compumarts, Sigma, 2B, …),
                     or ``"both"`` to scrape both brands and stores.
        targets:     A list of specific keys (e.g. ``["asus", "hp"]`` or
                     ``["compumarts", "sigma"]``) or the literal ``"all"``
                     to scrape every registered target of that type.
        level:       1 = fast catalog-card summaries, 2 = deep PDP spec crawl.
        until_model: Optional watermark pointer(s).  When the scraper
                     encounters a matching model it stops immediately.
                     ``None`` means scrape the entire catalog.
        max_pages:   Optional pagination safety ceiling.
                     ``None`` or <= 0 means scrape all pages until exhaustion.
        limit:       Optional maximum number of items to collect per target.
                     ``None`` or <= 0 means unlimited.
        output_dir:  Optional directory path.  When set the orchestrator
                     saves one JSON file **per target** inside this directory
                     (e.g. ``output_dir/brand_asus.json``,
                     ``output_dir/store_compumarts.json``).
        send_email:  Whether to dispatch an email report after each scraper
                     finishes (defaults to True for API triggers).
    """

    target_type: Literal["brand", "store", "both"] = Field(
        default="brand",
        description="Target category: 'brand', 'store', or 'both'",
        examples=["brand"],
    )
    targets: list[str] | Literal["all"] = Field(
        default="all",
        description="List of target keys (e.g. ['gigabyte', 'asus']) or 'all'",
        examples=["all"],
    )

    # Scraping parameters
    level: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Extraction level: 1 (Summary cards) or 2 (Deep PDP specs)",
        examples=[1],
    )
    until_model: str | list[str] | None = Field(
        default=None,
        description="Watermark model name or code to stop scraping at (leave null for full catalog)",
        examples=[None],
    )
    max_pages: int | None = Field(
        default=None,
        description="Maximum catalog pages to scan (leave null or <=0 for all pages)",
        examples=[None],
    )
    limit: int | None = Field(
        default=None,
        description="Maximum laptops to collect (leave null or <=0 for unlimited)",
        examples=[None],
    )

    # Output
    output_dir: str | None = Field(
        default=None,
        description="Directory to save JSON output files locally (bypassed when upload_to_bucket=True to conserve server disk space)",
        examples=["scraping-results"],
    )

    # Email notifications
    send_email: bool = Field(
        default=True,
        description="Send email status notification after each scraper completes",
        examples=[True],
    )

    # Object storage upload
    upload_to_bucket: bool = Field(
        default=False,
        description="Upload scraped JSON output files to the configured object storage bucket",
        examples=[False],
    )

    @field_validator("targets", mode="before")
    @classmethod
    def normalize_targets(cls, v: Any) -> list[str] | Literal["all"]:
        """Filter out Swagger dummy placeholder 'string' and normalize to clean list or 'all'."""
        if v is None:
            return "all"
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if not cleaned or cleaned in ("all", "string"):
                return "all"
            return [cleaned]
        if isinstance(v, list):
            cleaned_list = [
                s.strip().lower() for s in v
                if isinstance(s, str) and s.strip() and s.strip().lower() not in ("string", "none", "null")
            ]
            return cleaned_list if cleaned_list else "all"
        return v

    @field_validator("max_pages", "limit", mode="before")
    @classmethod
    def normalize_positive_ints(cls, v: Any) -> int | None:
        """Convert 0 or negative integers (common Swagger defaults) to None (unlimited)."""
        if v is None:
            return None
        try:
            val = int(v)
            return val if val > 0 else None
        except (ValueError, TypeError):
            return None

    @field_validator("until_model", mode="before")
    @classmethod
    def normalize_until_model(cls, v: Any) -> str | list[str] | None:
        """Filter out Swagger default placeholder 'string' or empty strings."""
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned or cleaned.lower() in ("string", "none", "null"):
                return None
            return cleaned
        if isinstance(v, list):
            cleaned_list = [
                s.strip() for s in v
                if isinstance(s, str) and s.strip() and s.strip().lower() not in ("string", "none", "null")
            ]
            return cleaned_list or None
        return v

    @field_validator("output_dir", mode="before")
    @classmethod
    def normalize_output_dir(cls, v: Any) -> str | None:
        """Filter out Swagger default placeholder 'string' or empty strings."""
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned or cleaned.lower() in ("string", "none", "null"):
                return None
            return cleaned
        return v


# ─── Per-target result ──────────────────────────────────────────────────────

class ScrapeTargetResult(BaseModel):
    """Result produced for a single scraping target (one brand or one store)."""

    target_type: Literal["brand", "store"]
    target_key: str
    target_name: str
    level: int
    items_scraped: int
    output_file: str | None = None
    storage_key: str | None = None
    error: str | None = None

    # The actual catalog payload — exactly one of these will be populated.
    brand_result: BrandCatalogResult | None = None
    store_result: StoreCatalogResult | None = None


# ─── Aggregate response ────────────────────────────────────────────────────

class ScrapeResponse(BaseModel):
    """Aggregate result returned by the orchestrator after all targets finish."""

    results: list[ScrapeTargetResult] = Field(default_factory=list)
    total_targets: int = 0
    total_items_scraped: int = 0
    started_at: str = Field(default_factory=utcnow_str)
    finished_at: str | None = None


# ─── Endpoint Trigger Response ──────────────────────────────────────────────

class ScrapeJobResponse(BaseModel):
    """Immediate HTTP acknowledgment returned when the scraping job is queued."""

    status: str = "accepted"
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str = "Scraping job queued successfully in background"
    request: ScrapeRequest
    queued_at: str = Field(default_factory=utcnow_str)
