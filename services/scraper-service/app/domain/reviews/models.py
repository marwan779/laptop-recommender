"""Immutable domain models for the YouTube review collection feature."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewTargetInput:
    """Normalized input for one laptop review target.

    The event schema flattens database identifiers and identity fields into
    this shape. All identifiers remain optional here so the feature can be
    exercised standalone before the RabbitMQ handler is wired.
    """

    laptop_id: str | None = None
    canonical_id: str | None = None
    title: str | None = None
    brand: str | None = None
    laptop_family: str | None = None
    laptop_model: str | None = None
    mpn: str | None = None
    manufacturer_part_number: str | None = None
    retailer_sku: str | None = None
    skus: tuple[str, ...] = ()
    mpns: tuple[str, ...] = ()
    product_urls: tuple[str, ...] = ()
    thumbnail_url: str | None = None
    search_queries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewIdentity:
    """Resolved identity used by query building and relevance matching."""

    target_key: str
    laptop_id: str | None
    canonical_id: str | None
    brand: str | None
    family: str | None
    model: str | None
    title: str
    title_core: str
    full_sku: str | None
    sub_model: str | None
    base_model: str | None
    mpn: str | None
    mpn_compact: str | None
    sku_candidates: tuple[str, ...]
    mpn_candidates: tuple[str, ...]
    cpu_hint: str | None
    product_urls: tuple[str, ...]
    thumbnail_url: str | None
    language_hint: str
    warnings: tuple[str, ...]
