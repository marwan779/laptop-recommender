"""Single source of truth for laptop extraction schema.

Defines the complete canonical output structure for catalog-service.
"""

from __future__ import annotations

from typing import Any


def empty_structured() -> dict[str, Any]:
    """Return the complete canonical structured laptop dictionary skeleton.

    All sub-extractors, key matcher, and hybrid flows must initialize
    from this single source of truth to eliminate KeyError risks.
    """
    return {
        "identity": {
            "brand": None,
            "laptop_family": None,
            "laptop_model": None,
            "manufacturer_part_number": None,
        },
        "cpu": {
            "manufacturer": None,
            "line": None,
            "model": None,
            "series": None,
            "full_name": None,
            "cores": None,
            "threads": None,
            "clock_speed": None,
            "clock_base_ghz": None,
            "clock_boost_ghz": None,
        },
        "gpu": {
            "manufacturer": None,
            "model": None,
            "secondary_model": None,
            "full_name": None,
            "vram_gb": None,
            "tdp_w": None,
            "integrated": False,
        },
        "memory": {
            "capacity_gb": None,
            "memory_type": None,
            "speed": None,
            "slot_count": None,
            "max_supported_gb": None,
        },
        "storage": {
            "capacity_gb": None,
            "storage_type": "SSD",
            "interface": None,
            "form_factor": None,
            "slot_count": None,
            "max_supported_gb": None,
            "summary": None,
        },
        "display": {
            "size_inches": None,
            "resolution": None,
            "resolution_width": None,
            "resolution_height": None,
            "panel_type": None,
            "refresh_rate_hz": None,
            "touchscreen": False,
            "aspect_ratio": None,
            "summary": None,
        },
        "power_battery": {
            "battery_capacity_wh": None,
            "battery_cells": None,
            "power_adapter_w": None,
            "summary": None,
        },
        "connectivity": {
            "wifi": None,
            "bluetooth": None,
            "ethernet": None,
            "ports": [],
        },
        "operating_system": {
            "name": None,
        },
        "physical": {
            "weight_kg": None,
            "color": None,
            "width_mm": None,
            "depth_mm": None,
            "height_mm": None,
        },
        "build": {
            "has_backlit_keyboard": None,
            "has_fingerprint": None,
            "pointing_device": None,
            "security_features": None,
        },
        "audio": {
            "speaker_count": None,
            "microphone": None,
        },
        "webcam": {
            "resolution": None,
        },
        # Additive top-level fields
        "product_type": "laptop",
        "condition": "new",
        "price_egp": None,
        "in_stock": True,
        "extraction_meta": {
            "status": "ok",  # "ok" | "partial" | "failed"
            "warnings": [],
            "rejected": [],  # list[{field, value, rule}]
            "conflicts": [],  # list[{field, title_value, table_value, chosen, reason}]
            "field_sources": {},  # {"cpu.model": "tier1"|"tier2"|"title"|"lookup"}
            "tokens": {
                "max": 0,
                "truncations_prevented": 0,
            },
        },
    }
