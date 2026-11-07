"""Map event/catalog payloads into pure domain review targets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.reviews.models import ReviewTargetInput


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _as_string_tuple(*values: Any) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidates: list[Any] = [value]
        elif isinstance(value, (list, tuple, set)):
            candidates = list(value)
        else:
            continue
        for candidate in candidates:
            text = _as_string(candidate)
            if text and text not in result:
                result.append(text)
    return tuple(result)


def target_from_mapping(data: Mapping[str, Any]) -> ReviewTargetInput:
    """Build a ``ReviewTargetInput`` from a catalog row or event target.

    ``specs.identity`` takes precedence over top-level identity fields, which
    matches the catalog payload shape and keeps the mapping deterministic.
    """

    specs = _as_mapping(data.get("specs"))
    identity = _as_mapping(specs.get("identity"))

    def pick(*keys: str) -> str | None:
        for source in (identity, data):
            for key in keys:
                value = _as_string(source.get(key))
                if value:
                    return value
        return None

    return ReviewTargetInput(
        laptop_id=_as_string(data.get("laptop_id")),
        canonical_id=_as_string(data.get("canonical_id")) or _as_string(data.get("canonical_slug")),
        title=_as_string(data.get("title")),
        brand=pick("brand"),
        laptop_family=pick("laptop_family"),
        laptop_model=pick("laptop_model"),
        mpn=_as_string(data.get("mpn")) or _as_string(identity.get("mpn")),
        manufacturer_part_number=(
            _as_string(identity.get("manufacturer_part_number"))
            or _as_string(data.get("manufacturer_part_number"))
        ),
        retailer_sku=pick("retailer_sku"),
        skus=_as_string_tuple(data.get("skus"), identity.get("skus")),
        mpns=_as_string_tuple(data.get("mpns"), identity.get("mpns")),
        product_urls=_as_string_tuple(
            data.get("product_urls"),
            data.get("product_url"),
            data.get("url"),
            identity.get("product_urls"),
            identity.get("product_url"),
            identity.get("url"),
        ),
        thumbnail_url=_as_string(data.get("thumbnail_url")) or _as_string(identity.get("thumbnail_url")),
        search_queries=_as_string_tuple(data.get("search_queries")),
    )


def targets_from_payload(payload: Mapping[str, Any]) -> tuple[ReviewTargetInput, ...]:
    """Map a batched command payload into domain targets."""

    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, (list, tuple)):
        return ()
    return tuple(
        target_from_mapping(target)
        for target in raw_targets
        if isinstance(target, Mapping)
    )
