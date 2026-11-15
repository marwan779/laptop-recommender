"""Event and messaging contract schemas for ai-recommender-service."""

from app.schemas.events import (
    BaseEvent,
    EventType,
    ReviewsEnrichedEvent,
    ReviewsEnrichedPayload,
    ReviewsEnrichFailedEvent,
    ReviewsEnrichFailedPayload,
    ReviewsReadyEvent,
    ReviewsReadyPayload,
)

__all__ = [
    "BaseEvent",
    "EventType",
    "ReviewsEnrichFailedEvent",
    "ReviewsEnrichFailedPayload",
    "ReviewsEnrichedEvent",
    "ReviewsEnrichedPayload",
    "ReviewsReadyEvent",
    "ReviewsReadyPayload",
]
