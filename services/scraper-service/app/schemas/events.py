"""Event & Command Message Schemas for RabbitMQ Inter-Service Messaging.

Defines standardized envelopes, command payloads, and domain event payloads
for catalog discovery, price verification, and review scraping workflows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
import uuid

from pydantic import BaseModel, Field

from app.price_monitor.models import PriceCheckItem, PriceCheckItemResult


# ─── Event Routing Keys / Types ─────────────────────────────────────────────


class EventType(StrEnum):
    """Routing keys and classification types for inter-service messages."""

    # Flow 1: Full Catalog Scraping
    CATALOG_SCRAPE_COMMAND = "catalog.scrape.command"
    CATALOG_READY_EVENT = "catalog.ready.event"
    CATALOG_SCRAPE_FAILED_EVENT = "catalog.scrape.failed"

    # Flow 2: Price & Availability Monitoring
    PRICES_CHECK_COMMAND = "prices.check.command"
    PRICES_CHECKED_EVENT = "prices.checked.event"

    # Flow 3: Community Reviews Scraping (Phase 2)
    REVIEWS_SCRAPE_COMMAND = "reviews.scrape.command"
    REVIEWS_READY_EVENT = "reviews.ready.event"


# ─── Standard Message Envelope ──────────────────────────────────────────────


class BaseEvent(BaseModel):
    """Standard envelope metadata wrapping every message across the broker."""

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this specific message instance",
    )
    event_type: str = Field(description="Event classification / routing key")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC timestamp when the message was emitted",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Correlation ID for distributed tracing across services",
    )


# ─── Flow 1: Full Catalog Scraping ──────────────────────────────────────────


class ScrapeCatalogPayload(BaseModel):
    """Payload instructing the scraper service to crawl laptop catalogs."""

    batch_id: str = Field(description="Unique batch log UUID managed by catalog service")
    targets: list[str] = Field(
        default_factory=lambda: ["all"],
        description="List of target store slugs (e.g. ['compumarts', 'elbadr', 'sigma']) or ['all']",
    )
    level: int = Field(
        default=2,
        ge=1,
        le=2,
        description="Scraping depth: 1 = summary cards, 2 = deep PDP specifications",
    )
    until_models: list[str] | None = Field(
        default=None,
        description="Watermark model names/codes to stop scraping when encountered",
    )
    force_full_crawl: bool = Field(
        default=False,
        description="If True, bypasses watermark pointers and crawls the entire catalog",
    )
    upload_to_bucket: bool = Field(
        default=True,
        description="Whether to upload the consolidated catalog JSON to S3",
    )
    send_email: bool = Field(
        default=True,
        description="Whether to send email report after completion",
    )


class ScrapeCatalogCommand(BaseEvent):
    """Command sent by catalog-service to initiate full catalog discovery."""

    event_type: str = EventType.CATALOG_SCRAPE_COMMAND
    payload: ScrapeCatalogPayload


class CatalogReadyPayload(BaseModel):
    """Payload emitted when scraper finishes discovery and uploads catalog to S3."""

    batch_id: str = Field(description="Associated batch log UUID")
    s3_bucket: str = Field(description="S3 bucket containing the combined catalog artifact")
    s3_key: str = Field(description="S3 object key pointing to the catalog.json file")
    total_laptops: int = Field(description="Total number of consolidated laptops in the catalog")
    pointers_found: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Latest model pointers per store discovered in this batch",
    )
    duration_seconds: float = Field(default=0.0, description="Total crawl duration in seconds")


class CatalogReadyEvent(BaseEvent):
    """Event emitted when a consolidated catalog is ready for database seeding."""

    event_type: str = EventType.CATALOG_READY_EVENT
    payload: CatalogReadyPayload


class CatalogScrapeFailedPayload(BaseModel):
    """Payload emitted when catalog discovery encounters a fatal error."""

    batch_id: str = Field(description="Associated batch log UUID")
    error_message: str = Field(description="Description of the fatal failure")
    details: dict[str, Any] | None = Field(default=None, description="Optional diagnostic details")


class CatalogScrapeFailedEvent(BaseEvent):
    """Event emitted when catalog scraping fails fatally."""

    event_type: str = EventType.CATALOG_SCRAPE_FAILED_EVENT
    payload: CatalogScrapeFailedPayload


# ─── Flow 2: Price & Availability Monitoring ────────────────────────────────


class CheckPricesPayload(BaseModel):
    """Payload instructing the scraper to verify live prices for a batch of offers."""

    batch_id: str = Field(description="Price check batch identifier")
    store_key: str = Field(description="Store slug (e.g. compumarts, sigma, elbadr)")
    store_name: str | None = Field(default=None, description="Human-friendly store name")
    items: list[PriceCheckItem] = Field(description="List of target offers to verify")


class CheckPricesCommand(BaseEvent):
    """Command sent by catalog-service price sync cron to verify product offers."""

    event_type: str = EventType.PRICES_CHECK_COMMAND
    payload: CheckPricesPayload


class PricesCheckedPayload(BaseModel):
    """Payload containing live price check results for a batch of offers."""

    batch_id: str = Field(description="Price check batch identifier")
    store_key: str = Field(description="Store slug")
    total_items: int = Field(default=0, description="Total offers verified")
    changed_items_count: int = Field(default=0, description="Offers with price or stock changes")
    price_drops_count: int = Field(default=0, description="Offers with price decreases")
    price_hikes_count: int = Field(default=0, description="Offers with price increases")
    out_of_stock_count: int = Field(default=0, description="Offers found out of stock")
    errors_count: int = Field(default=0, description="Offers that failed extraction")
    duration_seconds: float = Field(default=0.0, description="Duration of batch check in seconds")
    results: list[PriceCheckItemResult] = Field(
        default_factory=list,
        description="Individual offer verification records",
    )


class PricesCheckedEvent(BaseEvent):
    """Event emitted when live price verification finishes."""

    event_type: str = EventType.PRICES_CHECKED_EVENT
    payload: PricesCheckedPayload


# ─── Flow 3: Community Reviews Scraping (Phase 2) ───────────────────────────


class LaptopReviewTarget(BaseModel):
    """Target laptop to search YouTube reviews for."""

    laptop_id: str = Field(description="Laptop configuration UUID from catalog database")
    canonical_id: str = Field(description="Laptop canonical slug identifier")
    title: str | None = Field(default=None, description="Full retail or catalog product title")
    brand: str | None = Field(default=None, description="Brand name, e.g. ASUS")
    laptop_family: str | None = Field(default=None, description="Product family, e.g. Vivobook")
    laptop_model: str | None = Field(default=None, description="Model name, e.g. Vivobook 16")
    mpn: str | None = Field(default=None, description="Manufacturer part number")
    manufacturer_part_number: str | None = Field(
        default=None,
        description="Canonical manufacturer part number",
    )
    retailer_sku: str | None = Field(default=None, description="Retailer-specific SKU")
    skus: list[str] = Field(
        default_factory=list,
        description="Additional SKU or model-code candidates",
    )
    mpns: list[str] = Field(
        default_factory=list,
        description="Additional manufacturer part number candidates",
    )
    product_urls: list[str] = Field(
        default_factory=list,
        description="Known product page URLs for additional identity context",
    )
    thumbnail_url: str | None = Field(default=None, description="Product thumbnail URL")
    screen_size: float | None = Field(default=None, description="Display size in inches e.g. 15.6, 16.0")
    matched_laptop_ids: list[str] = Field(
        default_factory=list,
        description="All laptop UUIDs belonging to this chassis group",
    )
    matched_canonical_ids: list[str] = Field(
        default_factory=list,
        description="All canonical slugs belonging to this chassis group",
    )


class ScrapeReviewsPayload(BaseModel):
    """Payload instructing the scraper to search YouTube for review candidates.

    Carries the full resolved chassis batch (e.g. 70-100 targets) in a single
    payload; there is deliberately no per-message target cap.
    """

    job_id: str = Field(description="User recommendation session / Phase 2 job ID")
    targets: list[LaptopReviewTarget] = Field(
        description="Full batch of resolved chassis targets to scrape reviews for",
    )


class ScrapeReviewsCommand(BaseEvent):
    """Command triggered by user requesting Phase 2 community review analysis."""

    event_type: str = EventType.REVIEWS_SCRAPE_COMMAND
    payload: ScrapeReviewsPayload


class LaptopReviewSnippet(BaseModel):
    """A single community review snippet or opinion extract."""

    source: str = Field(description="Source platform: 'reddit', 'youtube', or 'web'")
    title: str | None = Field(default=None, description="Post, thread, or video title")
    url: str | None = Field(default=None, description="Direct URL to source")
    snippet_text: str = Field(description="Cleaned text content or transcript excerpt")
    score_or_upvotes: int | None = Field(default=None, description="Upvotes, likes, or upvote score")


class LaptopReviewsResult(BaseModel):
    """Aggregated reviews for a single candidate laptop."""

    laptop_id: str
    canonical_id: str
    snippets: list[LaptopReviewSnippet] = Field(default_factory=list)


class ReviewsReadyPayload(BaseModel):
    """Payload containing extracted community reviews for the candidate laptops."""

    job_id: str = Field(description="User recommendation session / Phase 2 job ID")
    total_laptops: int = Field(description="Number of laptops processed")
    total_snippets: int = Field(description="Total review snippets collected")
    results: list[LaptopReviewsResult] = Field(
        default_factory=list,
        description="Extracted review snippets grouped by laptop",
    )
    s3_key: str | None = Field(
        default=None,
        description="Object storage key for the raw reviews JSON file",
    )
    total_chassis: int = Field(
        default=0,
        description="Total unique chassis targets processed",
    )


class ReviewsReadyEvent(BaseEvent):
    """Event emitted when community review scraping is complete."""

    event_type: str = EventType.REVIEWS_READY_EVENT
    payload: ReviewsReadyPayload
