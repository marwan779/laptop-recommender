"""Shared chassis identity helpers.

The chassis key must be derived identically everywhere it is used (YouTube
collector, communities collector, orchestrator) so platform mappings keyed by
``chassis_key`` always line up with the assembled review items.

Kept free of I/O so it is trivially unit-testable.
"""

from __future__ import annotations

import re

from app.schemas.events import LaptopReviewTarget

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_key_part(value: str | None) -> str | None:
    """Lowercase and collapse non-alphanumerics to single hyphens."""
    if not value:
        return None
    cleaned = _NON_ALNUM_RE.sub("-", str(value).strip().lower()).strip("-")
    return cleaned or None


def build_chassis_key(target: LaptopReviewTarget) -> str:
    """Derive or preserve a stable ``brand:family:sub_model`` chassis key.

    When ``catalog-service`` already resolved ``target.chassis_key`` (using its
    chassis-code extractor), honor it directly so both services stay 100%
    aligned. Otherwise fall back to normalizing ``brand:family:model`` after
    stripping a repeated family prefix.

    Falls back to the canonical id when identity fields are absent so the key is
    never blank.
    """
    explicit = str(getattr(target, "chassis_key", None) or "").strip()
    if explicit:
        return explicit

    brand = normalize_key_part(target.brand)
    family = normalize_key_part(target.laptop_family)
    model = normalize_key_part(target.laptop_model)

    if model and family:
        family_prefix = f"{family}-"
        if model.startswith(family_prefix):
            model = model[len(family_prefix) :]

    parts = [part for part in (brand, family, model) if part]
    if parts:
        return ":".join(parts)
    return str(target.canonical_id).strip().lower()


__all__ = ["build_chassis_key", "normalize_key_part"]
