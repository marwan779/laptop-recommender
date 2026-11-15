"""Event message schemas for RabbitMQ inter-service messaging.

Matches the exact JSON envelope and routing keys shared with
`scraper-service` and `catalog-service`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Routing keys and classification types for review workflow messages."""

    REVIEWS_READY_EVENT = "reviews.ready.event"
    REVIEWS_ENRICHED_EVENT = "reviews.enriched.event"
    REVIEWS_ENRICH_FAILED_EVENT = "reviews.enrich.failed"


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


class ReviewsReadyPayload(BaseModel):
    """Inbound payload emitted by scraper-service when raw reviews land in S3."""

    job_id: str = Field(description="Phase 2 review scraping job ID")
    total_laptops: int = Field(default=0, description="Number of laptops processed")
    total_snippets: int = Field(default=0, description="Total review snippets collected")
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional inline snippets when artifact is not stored in S3",
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
    """Event emitted by scraper-service when raw community reviews are ready."""

    event_type: str = EventType.REVIEWS_READY_EVENT
    payload: ReviewsReadyPayload


class ReviewsEnrichedPayload(BaseModel):
    """Outbound payload emitted after enriching, indexing, and uploading reviews to S3."""

    job_id: str = Field(description="Review enrichment job ID")
    s3_key: str | None = Field(
        default=None,
        description="Object storage key for the enriched Format B1/B2 reviews JSON",
    )
    s3_bucket: str | None = Field(
        default=None,
        description="Optional S3 bucket name carrying the enriched artifact",
    )
    total_chassis: int = Field(default=0, description="Number of chassis processed")
    total_laptops: int = Field(default=0, description="Number of matched catalog laptops")


class ReviewsEnrichedEvent(BaseEvent):
    """Event emitted when ai-recommender-service finishes enrichment & ChromaDB indexing."""

    event_type: str = EventType.REVIEWS_ENRICHED_EVENT
    payload: ReviewsEnrichedPayload


class ReviewsEnrichFailedPayload(BaseModel):
    """Outbound payload emitted when review enrichment fails fatally."""

    job_id: str = Field(description="Associated review enrichment job ID")
    error_message: str = Field(description="Description of the fatal enrichment failure")
    s3_key: str | None = Field(
        default=None,
        description="Optional raw reviews S3 key that triggered the failed enrichment",
    )
    details: dict[str, Any] | None = Field(default=None, description="Optional diagnostic details")


class ReviewsEnrichFailedEvent(BaseEvent):
    """Event emitted when community review enrichment fails fatally."""

    event_type: str = EventType.REVIEWS_ENRICH_FAILED_EVENT
    payload: ReviewsEnrichFailedPayload
