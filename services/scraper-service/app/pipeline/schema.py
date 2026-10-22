"""Canonical schema definitions for the scraping and extraction pipeline.

Defines the data structures for:
- Canonical laptop specification model (35+ fields across all hardware categories).
- Raw scraped payload and section storage.
- Extraction envelopes (for handing unresolved fields to AI fallback).
- AI extraction results and audit traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass
class ExtractionEnvelope:
    """An envelope containing context and requirements for an unresolved field.

    Sent to the AI fallback layer when deterministic extraction fails or is incomplete.
    """

    field_path: str  # e.g., 'gpu.vram_gb', 'display.refresh_rate_hz'
    field_description: str  # Human-readable prompt for AI (e.g., 'Discrete GPU VRAM capacity in GB')
    raw_context: str  # Section-level sanitized text context
    failure_reason: str  # 'missing_key' | 'regex_failed' | 'validation_failed'
    expected_type: str  # 'int' | 'float' | 'str' | 'bool' | 'list[str]'
    allowed_values: list[str] | None = None  # Optional enum candidates (e.g., ['IPS', 'OLED', 'TN'])
    cpu_context: dict[str, Any] | None = None  # CPU constraints to assist resolution
    section_name: str | None = None  # Name of the section (e.g., 'Display', 'Graphics')


@dataclass
class EnvelopeResult:
    """The result produced by an AI fallback extractor for a single envelope."""

    field_path: str
    extracted_value: Any
    raw_span: str | None = None
    confidence: float = 1.0
    model_name: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentEnvelope:
    """An envelope containing a complete component sub-schema and raw context for AI extraction.

    Groups all fields of a hardware subsystem (e.g., 'display', 'memory', 'power_battery')
    with pre-filled Layer 4 validated values and None for missing fields.
    """

    component_name: str  # 'display', 'memory', 'power_battery', etc.
    raw_spec: str  # Full section/table text for this component
    sub_schema: dict[str, Any]  # Dict of field_name -> value (pre-filled or None)
    locked_fields: set[str]  # Immutable fields already validated in L4
    field_descriptions: dict[str, str] = field(default_factory=dict)  # Field descriptions / hints
    enum_constraints: dict[str, list[str]] = field(default_factory=dict)  # Allowed enums
    cpu_context: dict[str, Any] | None = None  # Hardware constraints


@dataclass
class ComponentEnvelopeResult:
    """The result produced by an AI fallback extractor for a component envelope."""

    component_name: str
    extracted_fields: dict[str, Any]  # Dict of field_name -> extracted value
    model_name: str = "unknown"
    confidence: float = 1.0
    raw_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawScrapedProduct:
    """Raw scrape artifact captured from the retailer page."""

    url: str
    store: str
    title: str
    raw_html: str
    raw_tables: dict[str, dict[str, str]] = field(default_factory=dict)
    raw_sections: dict[str, str] = field(default_factory=dict)
    price: float | None = None
    currency: str | None = "EGP"
    in_stock: bool = True
    retailer_sku: str | None = None
    mpn: str | None = None
    scraped_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def empty_laptop_specifications() -> dict[str, Any]:
    """Return the empty canonical structured laptop dictionary skeleton.

    Covers all 35+ specification dimensions required for catalog ingestion and live audit.
    """
    return {
        "identity": {
            "brand": None,
            "laptop_family": None,
            "laptop_model": None,
            "manufacturer_part_number": None,
            "retailer_sku": None,
            "color": None,
            "is_bundle": False,
            "warranty": None,
            "warranty_years": None,
            "condition": None,
            "raw_spec": None,
        },
        "cpu": {
            "manufacturer": None,
            "line": None,
            "model": None,
            "series": None,
            "full_name": None,
            "cores": None,
            "threads": None,
            "clock_base_ghz": None,
            "clock_boost_ghz": None,
            "cache_mb": None,
            "microarchitecture": None,
            "microarchitecture_code": None,
            "low_power_cores": None,
            "performance_cores": None,
            "efficient_cores": None,
            "npu_tops": None,
            "base_power_w": None,
            "raw_spec": None,
        },
        "gpu": {
            "manufacturer": None,
            "model": None,
            "variant": None,
            "vram_gb": None,
            "tdp_w": None,
            "boost_clock_mhz": None,
            "ai_tops": None,
            "integrated": False,
            "raw_spec": None,
        },
        "memory": {
            "capacity_gb": None,
            "memory_type": None,
            "speed": None,
            "slot_count": None,
            "max_supported_gb": None,
            "is_soldered": None,
            "raw_spec": None,
        },
        "storage": {
            "capacity_gb": None,
            "storage_type": "SSD",
            "interface": None,
            "form_factor": None,
            "slot_count": None,
            "max_supported_gb": None,
            "raw_spec": None,
        },
        "display": {
            "size_inches": None,
            "resolution": None,
            "resolution_width": None,
            "resolution_height": None,
            "panel_type": None,
            "refresh_rate_hz": None,
            "aspect_ratio": None,
            "touchscreen": False,
            "brightness_nits": None,
            "color_gamut": None,
            "response_time_ms": None,
            "surface_treatment": None,
            "hdr": None,
            "raw_spec": None,
        },
        "power_battery": {
            "battery_capacity_wh": None,
            "battery_cells": None,
            "power_adapter_w": None,
            "fast_charging": None,
            "raw_spec": None,
        },
        "physical": {
            "weight_kg": None,
            "width_mm": None,
            "depth_mm": None,
            "height_mm": None,
            "raw_spec": None,
        },
        "build_security": {
            "has_backlit_keyboard": False,
            "keyboard_backlight_type": None,
            "has_fingerprint": False,
            "has_numpad": None,
            "pointing_device": None,
            "chassis_material": None,
            "security_features": [],
            "raw_spec": None,
        },
        "audio_webcam": {
            "speaker_count": None,
            "microphone": None,
            "webcam_resolution": None,
            "has_privacy_shutter": None,
            "has_ir_camera": None,
            "raw_spec": None,
        },
        "connectivity": {
            "wifi": None,
            "bluetooth": None,
            "ethernet": None,
            "ports": [],
            "has_card_reader": None,
            "card_reader_type": None,
            "thunderbolt_version": None,
            "raw_spec": None,
        },
        "operating_system": {
            "name": None,
            "raw_spec": None,
        },
    }
