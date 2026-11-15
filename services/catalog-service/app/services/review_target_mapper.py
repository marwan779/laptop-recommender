"""Shared projection helpers mapping catalog ORM rows to review scraping DTOs and events.

Centralizes construction of ``LaptopInputDto``, ``LaptopReviewTarget``, and the
sealed ``specs`` envelope so both ``CatalogIngestionService`` and
``ReviewIntelligenceService`` produce identical RabbitMQ review commands.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.reviews import LaptopInputDto, ResolvedReviewTarget
from app.models.laptop import LaptopConfiguration
from app.schemas.events import LaptopReviewTarget

_SRGB_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*srgb", re.IGNORECASE)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_srgb_percent(gamut: str | None) -> float | None:
    if not gamut:
        return None
    match = _SRGB_PCT_RE.search(gamut)
    if match:
        return float(match.group(1))
    return None


def build_review_specs_envelope(laptop: LaptopConfiguration | Any) -> dict[str, Any] | None:
    """Build a compact, JSON-safe hardware specs envelope for downstream review enrichment.

    Uses ``getattr`` safely so lightweight mock objects in unit tests remain supported;
    returns ``None`` when no hardware specification or metric fields are populated.
    """
    metrics = getattr(laptop, "metrics", None)

    cpu_full_name = getattr(laptop, "cpu_full_name", None)
    cpu_model = getattr(laptop, "cpu_model", None)
    cpu_base_power_w = getattr(laptop, "cpu_base_power_w", None)

    gpu_model = getattr(laptop, "gpu_model", None)
    gpu_tdp_w = getattr(laptop, "gpu_tdp_w", None)
    gpu_integrated = getattr(laptop, "gpu_integrated", None)

    ram_capacity_gb = getattr(laptop, "ram_capacity_gb", None)
    ram_is_soldered = getattr(laptop, "ram_is_soldered", None)
    ram_max_supported_gb = getattr(laptop, "ram_max_supported_gb", None)

    storage_capacity_gb = getattr(laptop, "storage_capacity_gb", None)
    storage_slot_count = getattr(laptop, "storage_slot_count", None)

    display_size_inches = _to_float(getattr(laptop, "display_size_inches", None))
    display_panel_type = getattr(laptop, "display_panel_type", None)
    display_refresh_rate_hz = getattr(laptop, "display_refresh_rate_hz", None)
    display_brightness_nits = getattr(laptop, "display_brightness_nits", None)
    display_color_gamut = getattr(laptop, "display_color_gamut", None)

    battery_whr = _to_float(getattr(laptop, "battery_capacity_wh", None))
    weight_kg = _to_float(getattr(laptop, "weight_kg", None))
    category = getattr(laptop, "market_positioning", None)

    estimated_battery_hours = _to_float(getattr(metrics, "estimated_battery_hours", None)) if metrics else None
    display_tier = getattr(metrics, "display_tier", None) if metrics else None

    has_hardware_context = any(
        val is not None
        for val in (
            category,
            cpu_full_name,
            cpu_model,
            cpu_base_power_w,
            gpu_model,
            gpu_tdp_w,
            ram_capacity_gb,
            storage_capacity_gb,
            display_panel_type,
            display_refresh_rate_hz,
            display_brightness_nits,
            display_color_gamut,
            battery_whr,
            weight_kg,
            estimated_battery_hours,
        )
    )
    if not has_hardware_context:
        return None

    return {
        "identity": {
            "primary_category": category,
        },
        "cpu": {
            "raw": cpu_full_name or cpu_model,
            "model": cpu_model,
            "base_power_w": cpu_base_power_w,
        },
        "gpu": {
            "raw": gpu_model,
            "model": gpu_model,
            "tgp_watts": gpu_tdp_w,
            "integrated": bool(gpu_integrated) if gpu_integrated is not None else None,
        },
        "memory": {
            "capacity_gb": ram_capacity_gb,
            "upgradeable": (not bool(ram_is_soldered)) if ram_is_soldered is not None else None,
            "max_supported_gb": ram_max_supported_gb,
        },
        "storage": {
            "capacity_gb": storage_capacity_gb,
            "slot_count": storage_slot_count,
        },
        "display": {
            "size_inches": display_size_inches,
            "panel_type": display_panel_type,
            "refresh_rate_hz": display_refresh_rate_hz,
            "brightness_nits": display_brightness_nits,
            "srgb_percent": _parse_srgb_percent(display_color_gamut),
            "color_gamut": display_color_gamut,
        },
        "battery": {
            "capacity_whr": battery_whr,
        },
        "derived_metrics": {
            "silicon": {
                "inferred_tgp_w": float(gpu_tdp_w) if gpu_tdp_w is not None else None,
            },
            "display": {
                "color_gamut_tier": display_color_gamut or display_tier,
            },
            "mobility": {
                "weight_kg": weight_kg,
                "battery_whr": battery_whr,
                "battery_hours_estimate": estimated_battery_hours,
            },
            "longevity": {
                "total_m2_slots": storage_slot_count,
                "max_ram_gb": ram_max_supported_gb or ram_capacity_gb,
            },
        },
    }


def to_review_input(laptop: LaptopConfiguration | Any) -> LaptopInputDto:
    """Project a ``LaptopConfiguration`` ORM row into a pure domain ``LaptopInputDto``."""
    offers = list(getattr(laptop, "offers", None) or [])
    product_urls = tuple(
        dict.fromkeys(
            offer.product_url.strip() for offer in offers if offer.product_url and offer.product_url.strip()
        )
    )
    retailer_skus = tuple(
        dict.fromkeys(
            offer.retailer_sku.strip() for offer in offers if offer.retailer_sku and offer.retailer_sku.strip()
        )
    )
    screen_size = getattr(laptop, "display_size_inches", None)
    return LaptopInputDto(
        laptop_id=str(laptop.id),
        canonical_id=laptop.canonical_id,
        title=laptop.title,
        brand=laptop.brand,
        laptop_family=laptop.laptop_family,
        laptop_model=laptop.laptop_model,
        mpn=laptop.mpn,
        thumbnail_url=laptop.thumbnail_url,
        screen_size=float(screen_size) if screen_size is not None else None,
        retailer_skus=retailer_skus,
        product_urls=product_urls,
        specs=build_review_specs_envelope(laptop),
    )


def to_review_target(target: ResolvedReviewTarget | Any) -> LaptopReviewTarget:
    """Map a resolved domain chassis target onto the RabbitMQ ``LaptopReviewTarget`` schema."""
    return LaptopReviewTarget(
        laptop_id=target.laptop_id,
        canonical_id=target.canonical_id,
        chassis_key=getattr(target, "chassis_key", None),
        title=target.title,
        brand=target.brand,
        laptop_family=target.laptop_family,
        laptop_model=target.laptop_model,
        mpn=target.mpn,
        manufacturer_part_number=target.manufacturer_part_number,
        retailer_sku=target.retailer_sku,
        skus=list(target.skus),
        mpns=list(target.mpns),
        product_urls=list(target.product_urls),
        thumbnail_url=target.thumbnail_url,
        screen_size=target.screen_size,
        matched_laptop_ids=list(target.matched_laptop_ids),
        matched_canonical_ids=list(target.matched_canonical_ids),
        specs=getattr(target, "specs", None),
    )


__all__ = [
    "build_review_specs_envelope",
    "to_review_input",
    "to_review_target",
]
