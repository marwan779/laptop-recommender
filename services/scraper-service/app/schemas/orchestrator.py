"""DTOs for the Scrape Orchestrator — the unified abstraction layer.

These models are the contract between any caller (CLI, FastAPI controller,
catalog-service cron job) and the ScrapeOrchestrator.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.laptop import BrandCatalogResult, StoreCatalogResult, utcnow_str


# ─── Request DTO ────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    """Describes *what* to scrape and *how*.

    Attributes:
        target_type: ``"brand"`` to scrape official brand portals (ASUS, HP, …)
                     or ``"store"`` to scrape Egyptian retail stores
                     (Compumarts, Sigma, 2B, …).
        targets:     A list of specific keys (e.g. ``["asus", "hp"]`` or
                     ``["compumarts", "sigma"]``) or the literal ``"all"``
                     to scrape every registered target of that type.
        level:       1 = fast catalog-card summaries, 2 = deep PDP spec crawl.
        until_model: Optional watermark pointer(s).  When the scraper
                     encounters a matching model it stops immediately.
                     ``None`` means scrape the entire catalog.
        max_pages:   Optional pagination safety ceiling.
                     ``None`` means scrape all pages until exhaustion.
        limit:       Optional maximum number of items to collect per target.
                     ``None`` means unlimited.
        output_dir:  Optional directory path.  When set the orchestrator
                     saves one JSON file **per target** inside this directory
                     (e.g. ``output_dir/brand_asus.json``,
                     ``output_dir/store_compumarts.json``).
    """

    target_type: Literal["brand", "store"]
    targets: list[str] | Literal["all"] = "all"

    # Scraping parameters — all optional for full-catalog ingestion
    level: int = 1
    until_model: str | list[str] | None = None
    max_pages: int | None = None
    limit: int | None = None

    # Output
    output_dir: str | None = None


# ─── Per-target result ──────────────────────────────────────────────────────

class ScrapeTargetResult(BaseModel):
    """Result produced for a single scraping target (one brand or one store)."""

    target_type: Literal["brand", "store"]
    target_key: str
    target_name: str
    level: int
    items_scraped: int
    output_file: str | None = None
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
