"""Deterministic Key Normalization & Hardware DNA Fingerprinting.

Extracts:
  - Normalized MPN (Tier 1 Match Key)
  - Canonical Silicon & Chassis Fingerprint Slug (Tier 2 Match Key)
"""

from __future__ import annotations

import re
from typing import Any

# Common placeholder/noise tokens that retailers mistakenly put in MPN fields
INVALID_MPN_TOKENS = {
    "NONE",
    "N/A",
    "NA",
    "UNKNOWN",
    "LAPTOP",
    "MODEL",
    "NOTEBOOK",
    "GAMING",
    "BLACK",
    "GREY",
    "SILVER",
    "DOS",
    "WIN11",
}


def slugify(text: str | None) -> str:
    """Normalize text into an alphanumeric slug with single underscores."""
    if not text:
        return ""
    s = text.strip().lower()
    # Remove registered trademark symbols, degrees, quotes
    s = re.sub(r"[®™©\u200e\u200f\u200b\xa0'\"`]", "", s)
    # Replace non-alphanumeric with underscores
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def normalize_mpn(raw_mpn: str | None) -> str | None:
    """Sanitize and normalize a Manufacturer Part Number.

    Examples:
      - "83DV01HSED#ABV" -> "83DV01HSED"
      - "90NR0MC1-M008A0" -> "90NR0MC1M008A0"
      - "ANV15-52-78UM" -> "ANV155278UM"
    """
    if not raw_mpn:
        return None

    cleaned = str(raw_mpn).strip()
    # Strip country / bundle packaging suffixes after # or /
    cleaned = re.sub(r"[#\/].*$", "", cleaned)
    # Strip punctuation, whitespace, dashes
    cleaned = re.sub(r"[\s\-_.]+", "", cleaned).upper()

    # Reject noisy values
    if len(cleaned) < 5 or cleaned in INVALID_MPN_TOKENS:
        return None

    # Reject purely generic descriptions that got parsed into MPN
    if cleaned.startswith("LAPTOP") or cleaned.startswith("NOTEBOOK"):
        return None

    return cleaned


def generate_hardware_fingerprint(
    brand: str,
    family: str | None,
    specs: dict[str, Any],
) -> str:
    """Generate a deterministic silicon & chassis fingerprint string.

    Combines the physical hardware dimensions that uniquely identify a laptop configuration:
      brand | family | cpu_model | gpu_model | ram_gb | storage_gb | screen_size | refresh_rate
    """
    brand_slug = slugify(brand) or "unknown"
    family_slug = slugify(family) or "base"

    # CPU identification
    cpu = specs.get("cpu", {})
    cpu_model = cpu.get("model") or cpu.get("full_name") or specs.get("cpu_key") or "unknown_cpu"
    # Simplify CPU name (e.g. "Intel Core i7-13645HX" -> "i7_13645hx")
    cpu_slug = slugify(str(cpu_model))
    cpu_slug = re.sub(r"^(?:intel_)?core_|^(?:amd_)?ryzen_|^(?:qualcomm_)?snapdragon_", "", cpu_slug)

    # GPU identification
    gpu = specs.get("gpu", {})
    gpu_model = gpu.get("model") or "integrated"
    gpu_slug = slugify(str(gpu_model))
    gpu_slug = re.sub(r"^(?:nvidia_)?geforce_|^(?:amd_)?radeon_|^intel_graphics_|^intel_", "", gpu_slug)

    # Memory capacity
    mem = specs.get("memory", {})
    ram_gb = mem.get("capacity_gb")
    ram_str = f"{ram_gb}gb" if ram_gb else "0gb"

    # Storage capacity
    storage = specs.get("storage", {})
    storage_gb = storage.get("capacity_gb")
    storage_str = f"{storage_gb}gb" if storage_gb else "0gb"

    # Display size and refresh rate
    display = specs.get("display", {})
    size_in = display.get("size_inches")
    size_str = f"{float(size_in):.1f}in" if size_in else "0in"

    refresh_hz = display.get("refresh_rate_hz")
    refresh_str = f"{int(refresh_hz)}hz" if refresh_hz else "defhz"

    # Assemble fingerprint tokens
    tokens = [
        brand_slug,
        family_slug,
        cpu_slug,
        gpu_slug,
        ram_str,
        storage_str,
        size_str,
        refresh_str,
    ]
    return "|".join(tokens)
