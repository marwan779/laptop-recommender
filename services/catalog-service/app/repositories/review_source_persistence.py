"""Shared conversion helpers for persisting canonical laptop review sources.

Keeps payload coercion in one place so both the seeder and the review
intelligence repository replace review-source rows identically.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any
import uuid

from app.models.review_source import LaptopReviewSource


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    """Coerce dicts, Pydantic models, and dataclasses into a mapping."""
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, Mapping) else None
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    try:
        attributes = vars(value)
    except TypeError:
        return None
    return attributes if isinstance(attributes, Mapping) else None


def _text(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_length is not None:
        return text[:max_length]
    return text


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def normalize_review_source_url(url: Any) -> str | None:
    """Return the canonical dedupe key for a review source URL."""
    return _text(url)


def build_review_sources(
    laptop_configuration_id: uuid.UUID,
    raw_sources: Any,
) -> list[LaptopReviewSource]:
    """Build deduplicated ORM rows from a mixed list of dicts/DTOs/dataclasses."""
    if not raw_sources:
        return []

    if isinstance(raw_sources, (str, bytes, Mapping)):
        candidates = [raw_sources]
    else:
        try:
            candidates = list(raw_sources)
        except TypeError:
            return []

    rows: list[LaptopReviewSource] = []
    seen_urls: set[str] = set()

    for candidate in candidates:
        source = _as_mapping(candidate)
        if source is None:
            continue

        url = normalize_review_source_url(source.get("url"))
        source_type = _text(source.get("source_type"), max_length=30)
        platform = _text(source.get("platform"), max_length=50)
        title = _text(source.get("title"))

        if not url or not source_type or not platform or not title or url in seen_urls:
            continue

        seen_urls.add(url)
        rows.append(
            LaptopReviewSource(
                laptop_configuration_id=laptop_configuration_id,
                source_type=source_type,
                platform=platform,
                title=title,
                url=url,
                author_or_channel=_text(source.get("author_or_channel"), max_length=150),
                channel_url=_text(source.get("channel_url")),
                rating=_optional_float(source.get("rating")),
                score_or_views=_optional_int(source.get("score_or_views")),
                published_at=_optional_datetime(source.get("published_at")),
            )
        )

    return rows


__all__ = ["build_review_sources", "normalize_review_source_url"]
