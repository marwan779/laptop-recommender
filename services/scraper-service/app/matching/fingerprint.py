"""Deterministic Key Normalization & Hardware DNA Fingerprinting.

Extracts:
  - Normalized MPN (Tier 1 Match Key)
  - Canonical Silicon & Chassis Fingerprint Slug (Tier 2 Match Key)
  - Hardware & Display Compatibility Guards
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
      brand | family | cpu_model | gpu_model_with_vram | ram_gb | storage_gb | screen_size

    Note:
      Refresh rate is intentionally excluded from the primary DNA hash to prevent
      false negatives when retailers omit refresh rates (e.g. 144Hz vs omitted).
      Refresh rate conflicts are resolved via `are_hardware_compatible`.
    """
    brand_slug = slugify(brand) or "unknown"
    family_slug = slugify(family) or "base"

    # CPU identification
    cpu = specs.get("cpu", {})
    cpu_model = cpu.get("model") or cpu.get("full_name") or specs.get("cpu_key") or "unknown_cpu"
    # Simplify CPU name (e.g. "Intel Core i7-13645HX" -> "i7_13645hx")
    cpu_slug = slugify(str(cpu_model))
    cpu_slug = re.sub(r"^(?:intel_)?core_|^(?:amd_)?ryzen_|^(?:qualcomm_)?snapdragon_", "", cpu_slug)

    # GPU identification (including VRAM to separate variants like RTX 3050 4GB vs 6GB)
    gpu = specs.get("gpu", {})
    gpu_model = gpu.get("model") or "integrated"
    gpu_slug = slugify(str(gpu_model))
    gpu_slug = re.sub(r"^(?:nvidia_)?geforce_|^(?:amd_)?radeon_|^intel_graphics_|^intel_", "", gpu_slug)
    gpu_vram = gpu.get("vram_gb")
    if gpu_vram:
        gpu_slug = f"{gpu_slug}_{int(gpu_vram)}gb"

    # Memory capacity
    mem = specs.get("memory", {})
    ram_gb = mem.get("capacity_gb")
    ram_str = f"{ram_gb}gb" if ram_gb else "0gb"

    # Storage capacity
    storage = specs.get("storage", {})
    storage_gb = storage.get("capacity_gb")
    storage_str = f"{storage_gb}gb" if storage_gb else "0gb"

    # Display size
    display = specs.get("display", {})
    size_in = display.get("size_inches")
    size_str = f"{float(size_in):.1f}in" if size_in else "0in"

    # Assemble fingerprint tokens
    tokens = [
        brand_slug,
        family_slug,
        cpu_slug,
        gpu_slug,
        ram_str,
        storage_str,
        size_str,
    ]
    return "|".join(tokens)


def are_hardware_compatible(item_a: dict[str, Any], item_b: dict[str, Any]) -> bool:
    """Evaluate whether two laptop listings are physically and architecturally compatible.

    Acts as an explicit sanity guard against:
      - Edge Case A: Conflicting display refresh rates (e.g. 60Hz vs 144Hz, or 144Hz vs 240Hz)
      - Edge Case B: Store RAM/SSD upgrades under identical base MPNs
      - Edge Case D: Differing GPU silicon or VRAM variants (e.g. RTX 3050 4GB vs 6GB)
      - CPU generational or tier mismatches (e.g. i5 vs i7)
    """
    # 1. RAM capacity guard (Exact match required if both specified)
    ram_a = item_a.get("ram_gb")
    ram_b = item_b.get("ram_gb")
    if ram_a and ram_b and ram_a != ram_b:
        return False

    # 2. Storage capacity guard (Tolerates minor drive formatting rounding like 1000 vs 1024)
    ssd_a = item_a.get("storage_gb")
    ssd_b = item_b.get("storage_gb")
    if ssd_a and ssd_b and abs(ssd_a - ssd_b) > 64:
        return False

    # 3. GPU VRAM capacity guard (e.g. 4GB vs 6GB)
    vram_a = item_a.get("vram_gb")
    vram_b = item_b.get("vram_gb")
    if vram_a and vram_b and vram_a != vram_b:
        return False

    # 4. Display Refresh Rate Veto (Tolerates missing refresh rates, vetos hard conflicts)
    hz_a = item_a.get("refresh_hz")
    hz_b = item_b.get("refresh_hz")
    if hz_a and hz_b and abs(hz_a - hz_b) > 10:
        return False

    # 5. CPU Tier Compatibility Guard
    cpu_a = slugify(item_a.get("cpu_model") or "")
    cpu_b = slugify(item_b.get("cpu_model") or "")
    if cpu_a and cpu_b and cpu_a != cpu_b and cpu_a not in cpu_b and cpu_b not in cpu_a:
        tiers = [
            "i3",
            "i5",
            "i7",
            "i9",
            "ultra_5",
            "ultra_7",
            "ultra_9",
            "ryzen_3",
            "ryzen_5",
            "ryzen_7",
            "ryzen_9",
        ]
        for tier in tiers:
            if (tier in cpu_a) and any(other in cpu_b for other in tiers if other != tier):
                return False

    # 6. GPU Model Number Compatibility Guard
    gpu_a = slugify(item_a.get("gpu_model") or "")
    gpu_b = slugify(item_b.get("gpu_model") or "")
    if gpu_a and gpu_b and gpu_a != gpu_b and gpu_a not in gpu_b and gpu_b not in gpu_a:
        gpu_numbers = [
            "2050",
            "3050",
            "3060",
            "3070",
            "3080",
            "4050",
            "4060",
            "4070",
            "4080",
            "4090",
            "5050",
            "5060",
            "5070",
            "5080",
            "5090",
        ]
        for num in gpu_numbers:
            if (num in gpu_a) and any(other in gpu_b for other in gpu_numbers if other != num):
                return False

    return True
