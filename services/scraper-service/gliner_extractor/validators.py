"""Pure validator and sanitizer functions for laptop specifications.

Single source of truth for hardware sanity gates and field validation.
Every validator function has the signature:
    validate_x(value, context=None) -> tuple[clean_value | None, rule_name_if_rejected | None]
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# =============================================================================
# Placeholder & Noise Sanitizer
# =============================================================================

PLACEHOLDER_WORDS: set[str] = {
    "tbd",
    "n/a",
    "na",
    "-",
    "--",
    "estimated",
    "expected",
    "approx",
    "approximate",
    "varies",
    "depending on model",
    "none",
    "unknown",
    "null",
    "not specified",
    "optional",
    "default",
}


def clean_text(s: Any) -> str:
    """Clean footnote numbers, trademark symbols, and invisible characters."""
    if s is None:
        return ""
    text = str(s)
    # Remove unicode marks and trademarks
    text = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", text)
    # Remove HP/OEM trailing footnote clusters (e.g., " 1 2", "( 8)", " 10 11 12 13", " 14 15")
    text = re.sub(r"\(\s*\d+\s*\)", " ", text)
    text = re.sub(r"\b(?:\d{1,2}\s+){1,4}\d{1,2}$", "", text.strip())
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_placeholder(s: Any) -> bool:
    """Check if a string represents an unpopulated placeholder."""
    if s is None:
        return True
    cleaned = clean_text(s).lower()
    if not cleaned or cleaned in PLACEHOLDER_WORDS:
        return True
    if re.search(r"\b(?:estimated|tbd|expected|varies|depending\s+on\s+model)\b", cleaned):
        return True
    return False


# =============================================================================
# 1. Identity Validators
# =============================================================================

CANONICAL_BRANDS: dict[str, str] = {
    "asus": "ASUS",
    "acer": "Acer",
    "dell": "Dell",
    "hp": "HP",
    "lenovo": "Lenovo",
    "msi": "MSI",
    "gigabyte": "Gigabyte",
    "apple": "Apple",
    "razer": "Razer",
    "samsung": "Samsung",
    "huawei": "Huawei",
    "microsoft": "Microsoft",
}

SUB_BRAND_TO_PARENT: dict[str, str] = {
    # ASUS
    "rog": "ASUS",
    "rog strix": "ASUS",
    "rog zephyrus": "ASUS",
    "rog flow": "ASUS",
    "tuf": "ASUS",
    "tuf gaming": "ASUS",
    "zenbook": "ASUS",
    "vivobook": "ASUS",
    "proart": "ASUS",
    "expertbook": "ASUS",
    # Dell
    "alienware": "Dell",
    "xps": "Dell",
    "inspiron": "Dell",
    "vostro": "Dell",
    "latitude": "Dell",
    "precision": "Dell",
    "g15": "Dell",
    "g16": "Dell",
    # Lenovo
    "legion": "Lenovo",
    "loq": "Lenovo",
    "ideapad": "Lenovo",
    "thinkpad": "Lenovo",
    "thinkbook": "Lenovo",
    "yoga": "Lenovo",
    # Acer
    "predator": "Acer",
    "helios": "Acer",
    "nitro": "Acer",
    "aspire": "Acer",
    "swift": "Acer",
    "travelmate": "Acer",
    "extensa": "Acer",
    # HP
    "omen": "HP",
    "victus": "HP",
    "pavilion": "HP",
    "envy": "HP",
    "spectre": "HP",
    "probook": "HP",
    "elitebook": "HP",
    "zbook": "HP",
    # Gigabyte
    "aorus": "Gigabyte",
    "aero": "Gigabyte",
    # MSI
    "katana": "MSI",
    "sword": "MSI",
    "cyborg": "MSI",
    "vector": "MSI",
    "stealth": "MSI",
    "raider": "MSI",
    "titan": "MSI",
    "thin": "MSI",
    "crosshair": "MSI",
    "modern": "MSI",
    "prestige": "MSI",
}

MPN_BLACKLIST_WORDS: set[str] = {
    "dos", "freedos", "windows", "intel", "amd", "nvidia", "core", "ryzen",
    "rtx", "gtx", "black", "silver", "gray", "grey", "blue", "white",
    "oled", "ips", "fhd", "qhd", "wuxga", "wqxga", "ram", "ssd", "ddr4", "ddr5",
}


def validate_brand(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate and canonicalize laptop brand."""
    if is_placeholder(value):
        return None, "brand_placeholder"
    val = clean_text(value).strip()
    val_low = val.lower()

    if val_low in CANONICAL_BRANDS:
        return CANONICAL_BRANDS[val_low], None

    if val_low in SUB_BRAND_TO_PARENT:
        return SUB_BRAND_TO_PARENT[val_low], None

    # Check if value contains known brand or sub-brand word
    for b_low, b_can in CANONICAL_BRANDS.items():
        if re.search(rf"\b{re.escape(b_low)}\b", val_low):
            return b_can, None

    for sub_low, parent in SUB_BRAND_TO_PARENT.items():
        if re.search(rf"\b{re.escape(sub_low)}\b", val_low):
            return parent, None

    # Reject if containing digits or longer than 12 chars
    if any(c.isdigit() for c in val) or len(val) > 12:
        return None, "brand_invalid_token"

    return val.capitalize(), None


def validate_mpn(
    value: Any,
    context: dict | None = None,
    title: str | None = None,
    brand: str | None = None,
) -> tuple[str | None, str | None]:
    """Validate manufacturer part number / SKU."""
    if is_placeholder(value):
        return None, "mpn_placeholder"
    val = clean_text(value).strip()

    # Rule: Barcode rejection (12-13 digit all-numeric barcodes e.g. EAN/UPC)
    if val.isdigit() and len(val) in (12, 13, 14):
        return None, "mpn_barcode_not_allowed"

    # Rule: URL slug rejection (e.g. acer-nitro-v-15-rtx-5050-egypt)
    slug_parts = val.split("-")
    if len(slug_parts) >= 4 and all((p.islower() or p.isdigit()) for p in slug_parts):
        return None, "mpn_url_slug_rejected"
    if re.search(r"-(?:egypt|laptop|gaming|intel|rtx|geforce|black|gray|silver)\b", val.lower()):
        return None, "mpn_url_slug_rejected"

    # Rule: 5-30 chars
    if len(val) < 5 or len(val) > 30:
        return None, "mpn_length_out_of_range"

    # Rule: must contain at least one digit and at least one letter
    has_digit = any(c.isdigit() for c in val)
    has_alpha = any(c.isalpha() for c in val)
    if not (has_digit and has_alpha):
        return None, "mpn_missing_alphanumeric"

    # Rule: no spaces except around a single '#'
    if " " in val:
        if not re.match(r"^[A-Z0-9_\-\./]+\s*#\s*[A-Z0-9_\-\./]+$", val, re.I):
            return None, "mpn_invalid_whitespace"

    # Rule: does not match hardware units (e.g. 16GB, 1TB, 15.6", 14 Cores)
    if re.search(r"^\d+(?:\.\d+)?\s*(?:GB|TB|Hz|W|Wh|MHz|GHz|inch|\"|″|-inch)\b", val, re.I):
        return None, "mpn_hardware_spec_token"

    if re.search(r"\b\d+\s*Cores?\b", val, re.I):
        return None, "mpn_cpu_core_token"

    # Rule: blacklist single known terms
    tokens = [t.lower() for t in re.split(r"[\s\-_]+", val)]
    if any(t in MPN_BLACKLIST_WORDS for t in tokens if len(tokens) <= 2):
        return None, "mpn_blacklisted_keyword"

    if re.search(r"\b(?:Core\s+i\d|Ryzen\s+\d|RTX\s*\d{4}|GTX\s*\d{4})\b", val, re.I):
        return None, "mpn_cpu_gpu_name"

    # Rule: Brand consistency check
    resolved_brand = brand or (context.get("brand") if context else None)
    if not resolved_brand and title:
        t_low = title.lower()
        for b_cand, b_canon in CANONICAL_BRANDS.items():
            if re.search(rf"\b{b_cand}\b", t_low):
                resolved_brand = b_canon
                break

    if resolved_brand:
        b_upper = resolved_brand.upper()
        # Acer part numbers (NH.xxxxx.xxx, NX.xxxxx.xxx, ANVxx-xx-xxxx)
        if (re.match(r"^N[HX]\.[A-Z0-9]{5}\.[A-Z0-9]{3}$", val, re.I) or re.match(r"^AN[A-Z0-9\-]+$", val, re.I)) and b_upper != "ACER":
            return None, "mpn_brand_mismatch"
        # Lenovo part numbers (80-84 or 20-21 + 8 alphanumeric)
        if re.match(r"^(?:8[0-4]|2[01])[A-Z0-9]{8}$", val, re.I) and b_upper != "LENOVO":
            return None, "mpn_brand_mismatch"
        # HP part numbers with #
        if "#" in val and b_upper not in ("HP", "HEWLETT PACKARD"):
            return None, "mpn_brand_mismatch"
        # MSI part numbers (9S7-xxxxxx-xxx)
        if re.match(r"^9S7-[A-Z0-9]{6}-[A-Z0-9]{3,4}$", val, re.I) and b_upper != "MSI":
            return None, "mpn_brand_mismatch"
        # ASUS part numbers (90Nxxxx-Mxxxxx)
        if re.match(r"^90N[A-Z0-9]{3,5}-M[A-Z0-9]{5,6}$", val, re.I) and b_upper != "ASUS":
            return None, "mpn_brand_mismatch"

        # Fix letter-O / zero typo for ASUS MPNs (e.g. 90NRON06-MOOJBO -> 90NR0N06-M00JB0)
        if b_upper == "ASUS" and re.match(r"^90N", val, re.I):
            val = re.sub(r"^90NR[oO]", "90NR0", val)
            val = re.sub(r"-M[oO]{2}", "-M00", val)

    return val, None


def is_brand_mpn(code: str | None, brand: str | None) -> bool:
    """Return True if code matches the authoritative manufacturer part number pattern."""
    if not code or not brand:
        return False
    c = str(code).strip()
    b = brand.strip().upper()
    if b == "ASUS":
        return bool(re.match(r"^90N[A-Z0-9]{3,5}-M[A-Z0-9]{5,6}$", c, re.I))
    if b == "ACER":
        return bool(re.match(r"^N[HX]\.[A-Z0-9]{5}\.[A-Z0-9]{3}$", c, re.I))
    if b == "LENOVO":
        return bool(re.match(r"^(?:8[0-4]|2[01])[A-Z0-9]{8}$", c, re.I))
    if b in ("HP", "HEWLETT PACKARD"):
        return bool(re.match(r"^[A-Z0-9]{5,7}#[A-Z0-9]{3}$", c, re.I))
    if b == "MSI":
        return bool(re.match(r"^9S7-[A-Z0-9]{6}-[A-Z0-9]{3,4}$", c, re.I))
    return False


def is_retailer_sku(code: str | None) -> bool:
    """Return True if code looks like an internal retailer SKU rather than an OEM MPN."""
    if not code:
        return False
    c = str(code).strip()
    if re.search(r"XXDXX|NAFAMZ|^TBC|^GGU|^DE014|16GXDX|8GXDX|[A-Z0-9]{15,}", c, re.I):
        return True
    return False


# =============================================================================
# 2. CPU / Processor Validators
# =============================================================================

def validate_cpu_cores_threads(
    cores: Any, threads: Any, context: dict | None = None
) -> tuple[int | None, int | None, str | None]:
    """Validate core and thread count plausibility and sanity."""
    c_val = None
    t_val = None

    if cores is not None and not is_placeholder(cores):
        try:
            c_val = int(cores)
        except (ValueError, TypeError):
            pass

    if threads is not None and not is_placeholder(threads):
        try:
            t_val = int(threads)
        except (ValueError, TypeError):
            pass

    # Plausible laptop cores: 2 to 32
    if c_val is not None:
        if c_val < 2 or c_val > 32:
            return None, t_val, "cpu_cores_out_of_range"

    # Plausible laptop threads: 2 to 48
    if t_val is not None:
        if t_val < 2 or t_val > 48:
            return c_val, None, "cpu_threads_out_of_range"

    # Rule: threads >= cores
    if c_val is not None and t_val is not None:
        if t_val < c_val:
            return c_val, None, "cpu_threads_less_than_cores"

    return c_val, t_val, None


def normalize_cpu_line(line_str: Any) -> str | None:
    """Normalize CPU family line string removing noisy trademarks and generation text."""
    if is_placeholder(line_str):
        return None
    val = clean_text(line_str)
    # Strip generation fluff: "13th Generation Intel Core i7 processor" -> "Core i7"
    val = re.sub(r"\b\d+(?:th|nd|rd|st)\s+(?:Generation|Gen)\b", "", val, flags=re.I)
    val = re.sub(r"\b(?:processor|laptop|cpu)\b", "", val, flags=re.I)
    val = re.sub(r"\bIntel\b", "", val, flags=re.I)
    val = re.sub(r"\s+", " ", val).strip()

    # Canonical prefixes
    m = re.search(r"\b(Core\s+Ultra\s+[3579]|Core\s+i[3579]|Core\s+[3579]|Ryzen\s+AI\s+(?:MAX\+?\s+)?[0-9]+|Ryzen\s+[3579]|Snapdragon\s+X(?:\s+Plus|\s+Elite)?|Apple\s+M[1-4](?:\s+Pro|\s+Max|\s+Ultra)?)\b", val, re.I)
    if m:
        return m.group(1).strip()
    return val or None


def validate_cpu_cache(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate and normalize CPU cache capacity in Megabytes (MB).

    Accepts:
        - int / float: 24 -> 24
        - str: "24MB", "24 MB", "36MB Intel Smart Cache", "24M Cache", "24"
    Rejects:
        - Out of sane bounds (valid: 1 to 128 MB for laptop CPUs)
        - Values in GB or KB (e.g. "24GB" is RAM/VRAM, "512KB" is L1/L2)
    """
    if is_placeholder(value):
        return None, None

    val_str = clean_text(str(value))

    # Guard: If explicit GB unit, reject as likely RAM or storage contamination
    if re.search(r"\b\d+\s*GB\b", val_str, re.I):
        return None, "cache_in_gb_rejected"

    # Match number preceding MB or M Cache or standalone number
    m = re.search(r"\b(\d{1,3})\s*(?:MB|M\b|\s*Megabytes?)\b", val_str, re.I)
    if not m:
        # Check for standalone integer if input is short or pure number
        m_pure = re.match(r"^(\d{1,3})$", val_str.strip())
        if m_pure:
            m = m_pure
        else:
            # Check pattern like "Cache: 24" or "Smart Cache 24"
            m_c = re.search(r"cache\D*(\d{1,3})\b", val_str, re.I)
            if m_c:
                m = m_c

    if not m:
        return None, "no_valid_cache_digits"

    cache_num = int(m.group(1))

    # Sane range check for laptop CPUs: 1 MB to 128 MB
    if cache_num < 1 or cache_num > 128:
        return None, f"cache_out_of_bounds_{cache_num}mb"

    return cache_num, None


# =============================================================================
# 3. GPU / Graphics Validators
# =============================================================================

VALID_VRAM_GB: set[int] = {1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32}

INTEGRATED_GPU_PATTERNS = re.compile(
    r"\b(intel\s*(?:uhd|iris\s*xe|arc(?:\s*graphics)?|arc\s*(?:1[1-4]0v|[0-9]core)|graphics)|"
    r"arc\s*graphics|iris\s*xe|uhd\s*graphics|"
    r"radeon\s*(?:graphics|6[68]0m|7[68]0m|8[89]0m|8060s|vega)|"
    r"adreno(?:\s*gpu)?|apple\s*gpu)\b",
    re.I,
)

DISCRETE_GPU_PATTERNS = re.compile(
    r"\b(geforce\s*rtx|geforce\s*gtx|geforce\s*mx|rtx\s*[0-9]{4}|gtx\s*[0-9]{4}|"
    r"quadro|rtx\s*a[0-9]{4}|radeon\s*rx|radeon\s*pro)\b",
    re.I,
)


def validate_gpu_integrated(model_name: Any, context: dict | None = None) -> tuple[bool, str | None]:
    """Determine whether GPU is integrated based on model naming."""
    if not model_name:
        return True, None
    m_str = clean_text(model_name)
    if DISCRETE_GPU_PATTERNS.search(m_str):
        return False, None
    if INTEGRATED_GPU_PATTERNS.search(m_str):
        return True, None
    return False, None


def validate_gpu_vram(
    value: Any, is_integrated: bool = False, context: dict | None = None
) -> tuple[int | None, str | None]:
    """Validate discrete GPU dedicated VRAM capacity."""
    if is_integrated:
        return None, "integrated_gpu_vram_disallowed"
    if is_placeholder(value):
        return None, "vram_placeholder"
    try:
        val = int(value)
        if val in VALID_VRAM_GB:
            return val, None
        return None, "vram_not_in_whitelist"
    except (ValueError, TypeError):
        m = re.search(r"\b(\d{1,2})\s*GB\b", str(value), re.I)
        if m:
            val = int(m.group(1))
            if val in VALID_VRAM_GB:
                return val, None
        return None, "vram_invalid_format"


# =============================================================================
# 4. Memory (RAM) Validators
# =============================================================================

VALID_RAM_SPEEDS: set[int] = {
    1600, 2133, 2400, 2666, 2933, 3200, 3733, 4266,
    4800, 5200, 5600, 6000, 6400, 7467, 7500, 8000, 8533,
}

VALID_RAM_CAPACITIES: set[int] = {
    4, 6, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256,
}

VALID_RAM_TYPES: set[str] = {
    "DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR4X", "LPDDR5", "LPDDR5X",
}


def validate_ram_speed(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate RAM frequency speed strictly against hardware whitelist."""
    if is_placeholder(value):
        return None, "ram_speed_placeholder"
    try:
        val = int(value)
        if val in VALID_RAM_SPEEDS:
            return val, None
        return None, "ram_speed_not_in_whitelist"
    except (ValueError, TypeError):
        m = re.search(r"\b(\d{4})\s*(?:MHz|MT/s)\b", str(value), re.I)
        if m:
            val = int(m.group(1))
            if val in VALID_RAM_SPEEDS:
                return val, None
        return None, "ram_speed_invalid_format"


def validate_ram_capacity(
    value: Any,
    context: dict | None = None,
    is_max: bool = False,
) -> tuple[int | None, str | None]:
    """Validate installed or maximum system memory capacity."""
    if is_placeholder(value):
        return None, "ram_capacity_placeholder"
    try:
        val = int(value)
        if is_max:
            if val in VALID_RAM_CAPACITIES and val >= 8:
                return val, None
            return None, "max_ram_capacity_not_in_whitelist"
        if val in VALID_RAM_CAPACITIES:
            return val, None
        return None, "ram_capacity_not_in_whitelist"
    except (ValueError, TypeError):
        m = re.search(r"\b(\d{1,3})\s*(?:GB|G)\b", str(value), re.I)
        if m:
            val = int(m.group(1))
            if is_max:
                if val in VALID_RAM_CAPACITIES and val >= 8:
                    return val, None
                return None, "max_ram_capacity_not_in_whitelist"
            if val in VALID_RAM_CAPACITIES:
                return val, None
        return None, "ram_capacity_invalid_format"


def validate_max_ram_capacity(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate maximum supported RAM capacity."""
    return validate_ram_capacity(value, context=context, is_max=True)


def validate_ram_type(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate memory generation type."""
    if is_placeholder(value):
        return None, "ram_type_placeholder"
    val = clean_text(value).upper()
    m = re.search(r"\b(LPDDR5X|LPDDR5|DDR5|LPDDR4X|LPDDR4|DDR4|DDR3)\b", val)
    if m:
        canon = m.group(1)
        if canon in VALID_RAM_TYPES:
            return canon, None
    return None, "ram_type_invalid"


def validate_ram_slots(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate RAM slot count (1-4)."""
    if is_placeholder(value):
        return None, "ram_slots_placeholder"
    try:
        val = int(value)
        if 1 <= val <= 4:
            return val, None
        return None, "ram_slots_out_of_range"
    except (ValueError, TypeError):
        m = re.search(r"\b([1-4])\s*(?:x|slots?|SODIMM|SO-DIMM)\b", str(value), re.I)
        if m:
            return int(m.group(1)), None
        return None, "ram_slots_invalid"


# =============================================================================
# 5. Storage Validators
# =============================================================================

VALID_STORAGE_CAPACITIES: set[int] = {
    128, 256, 512, 1024, 2048, 4096, 8192,
}


def validate_storage_capacity(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate internal SSD/HDD storage capacity in GB."""
    if is_placeholder(value):
        return None, "storage_capacity_placeholder"
    try:
        val = int(value)
        if val in VALID_STORAGE_CAPACITIES:
            return val, None
        return None, "storage_capacity_not_in_whitelist"
    except (ValueError, TypeError):
        m = re.search(r"\b(\d{1,4})\s*(TB|GB)\b", str(value), re.I)
        if m:
            num = int(m.group(1))
            unit = m.group(2).upper()
            val = num * 1024 if unit == "TB" else num
            if val in VALID_STORAGE_CAPACITIES:
                return val, None
        return None, "storage_capacity_invalid_format"


def validate_storage_interface(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate internal drive interface bus (NVMe, PCIe 4.0, SATA)."""
    if is_placeholder(value):
        return None, "storage_interface_placeholder"
    val = clean_text(value)
    # Reject noise tokens like FreeDOS, WUXGA, Intel UHD
    if any(bad in val.lower() for bad in ["freedos", "wuxga", "intel", "uhd", "display", "os"]):
        return None, "storage_interface_noise_rejected"

    m = re.search(r"\b(PCIe\s*[3-5](?:\.0)?(?:\s*x[24])?(?:\s*NVMe)?|NVMe|SATA(?:\s*III)?|PCIe\s*NVMe|M\.2\s*NVMe)\b", val, re.I)
    if m:
        return m.group(1).strip(), None
    return None, "storage_interface_unrecognized"


def validate_storage_form_factor(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate drive form factor (M.2 2280, 2.5)."""
    if is_placeholder(value):
        return None, "storage_form_factor_placeholder"
    val = clean_text(value)
    # Reject memory tokens like DDR5
    if any(bad in val.upper() for bad in ["DDR", "RAM", "GDDR"]):
        return None, "storage_form_factor_ram_leakage"
    m = re.search(r"\b(M\.2(?:\s*22(?:30|42|80))?|2\.5(?:-inch|\")?)\b", val, re.I)
    if m:
        return m.group(1).strip(), None
    return None, "storage_form_factor_unrecognized"


# =============================================================================
# 6. Display Validators
# =============================================================================

NAMED_RESOLUTIONS: dict[str, str] = {
    "fhd": "1920 x 1080",
    "full hd": "1920 x 1080",
    "fhd+": "1920 x 1200",
    "wuxga": "1920 x 1200",
    "qhd": "2560 x 1440",
    "wqhd": "2560 x 1440",
    "2k": "2560 x 1440",
    "2.5k": "2560 x 1600",
    "wqxga": "2560 x 1600",
    "qhd+": "2560 x 1600",
    "3k": "2880 x 1800",
    "3.2k": "3200 x 2000",
    "uhd": "3840 x 2160",
    "4k": "3840 x 2160",
    "4k+": "3840 x 2400",
}

VALID_REFRESH_RATES: set[int] = {30, 48, 60, 90, 120, 144, 165, 180, 240, 300, 360, 480}

VALID_PANEL_TYPES: set[str] = {"IPS", "OLED", "AMOLED", "Mini-LED", "VA", "TN", "WVA"}


def validate_display_size(value: Any, context: dict | None = None) -> tuple[float | None, str | None]:
    """Validate screen diagonal size in inches (10.0 to 18.5)."""
    if is_placeholder(value):
        return None, "display_size_placeholder"
    try:
        val = float(value)
        if 10.0 <= val <= 18.5:
            return round(val, 1), None
        return None, "display_size_out_of_range"
    except (ValueError, TypeError):
        m = re.search(r"\b(1[0-8](?:\.[0-9])?)\s*(?:\"|″|inch|-inch)\b", str(value), re.I)
        if m:
            val = float(m.group(1))
            if 10.0 <= val <= 18.5:
                return round(val, 1), None
        return None, "display_size_invalid_format"


def validate_resolution(
    value: Any, context: dict | None = None
) -> tuple[str | None, int | None, int | None, str | None]:
    """Validate resolution and return (resolution_str, width, height, rule_if_rejected)."""
    if is_placeholder(value):
        return None, None, None, "resolution_placeholder"
    val = clean_text(value).strip()

    # Reject raw size strings ("16 Inches", "11 Inch", "15.6-inch")
    if re.search(r"^\d{1,2}(?:\.\d)?\s*(?:inch|\"|inches|-inch)", val, re.I):
        return None, None, None, "resolution_size_string_rejected"

    # Match W x H
    m = re.search(r"\b(\d{3,4})\s*[xX*×]\s*(\d{3,4})\b", val)
    if m:
        w = int(m.group(1))
        h = int(m.group(2))
        if 1280 <= w <= 4096 and 720 <= h <= 2560:
            return f"{w} x {h}", w, h, None
        return None, None, None, "resolution_dimensions_out_of_range"

    # Lookup named resolution
    val_low = val.lower()
    for name, res_str in NAMED_RESOLUTIONS.items():
        if re.search(rf"\b{re.escape(name)}\b", val_low):
            parts = res_str.split(" x ")
            return res_str, int(parts[0]), int(parts[1]), None

    return None, None, None, "resolution_unrecognized"


def compute_aspect_ratio(width: int | None, height: int | None) -> str | None:
    """Compute standard aspect ratio from pixel dimensions."""
    if not width or not height or width <= 0 or height <= 0:
        return None
    ratio = width / height
    if math.isclose(ratio, 16 / 9, rel_tol=0.03):
        return "16:9"
    elif math.isclose(ratio, 16 / 10, rel_tol=0.03):
        return "16:10"
    elif math.isclose(ratio, 3 / 2, rel_tol=0.03):
        return "3:2"
    elif math.isclose(ratio, 4 / 3, rel_tol=0.03):
        return "4:3"
    return None


def validate_refresh_rate(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate screen refresh rate in Hz."""
    if is_placeholder(value):
        return None, "refresh_rate_placeholder"
    # Never extract from sRGB or G-SYNC text
    val_str = str(value)
    if "srgb" in val_str.lower() or "g-sync" in val_str.lower():
        return None, "refresh_rate_gamut_rejected"
    try:
        val = int(value)
        if val in VALID_REFRESH_RATES:
            return val, None
        return None, "refresh_rate_not_in_whitelist"
    except (ValueError, TypeError):
        m = re.search(r"\b(30|48|60|90|120|144|165|180|240|300|360|480)\s*Hz\b", val_str, re.I)
        if m:
            return int(m.group(1)), None
        return None, "refresh_rate_invalid_format"


def validate_panel_type(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate display panel technology."""
    if is_placeholder(value):
        return None, "panel_type_placeholder"
    val = clean_text(value).strip()
    # Reject memory leakage (e.g. "16GB")
    if any(bad in val.upper() for bad in ["GB", "RAM", "TB", "DDR"]):
        return None, "panel_type_ram_leakage"
    m = re.search(r"\b(IPS|OLED|AMOLED|MINI[- ]?LED|VA|TN|WVA)\b", val, re.I)
    if m:
        norm = m.group(1).upper()
        if "MINI" in norm:
            return "Mini-LED", None
        elif norm in VALID_PANEL_TYPES:
            return norm, None
        return norm, None
    return None, "panel_type_unrecognized"


# =============================================================================
# 7. Power & Battery Validators
# =============================================================================

def validate_battery_capacity(value: Any, context: dict | None = None) -> tuple[float | None, str | None]:
    """Validate battery energy capacity in Watt-hours (20.0 to 140.0 Wh)."""
    if is_placeholder(value):
        return None, "battery_wh_placeholder"
    val_str = str(value).strip()
    if re.search(r"\b(?:estimated|approx|expected|depending|tbd|varies)\b", val_str, re.I) or re.search(r"\d+\s*[-–~]\s*\d+", val_str):
        return None, "battery_wh_range_or_estimate_rejected"
    try:
        val = float(value)
        if 20.0 <= val <= 140.0:
            return round(val, 1), None
        return None, "battery_wh_out_of_range"
    except (ValueError, TypeError):
        m = re.search(r"\b(\d{2,3}(?:\.\d+)?)\s*Wh\b", val_str, re.I)
        if m:
            val = float(m.group(1))
            if 20.0 <= val <= 140.0:
                return round(val, 1), None
        return None, "battery_wh_invalid_format"


def validate_power_adapter(
    value: Any, battery_wh: float | None = None, source_key: str | None = None
) -> tuple[int | None, str | None]:
    """Validate external charger power adapter in Watts (30 to 400 W)."""
    if is_placeholder(value):
        return None, "adapter_w_placeholder"
    try:
        val = int(value)
    except (ValueError, TypeError):
        m = re.search(r"\b(\d{2,3})\s*W\b", str(value), re.I)
        val = int(m.group(1)) if m else None

    if val is None or val < 30 or val > 400:
        return None, "adapter_w_out_of_range"

    # Reject if it equals battery Wh unless explicitly in an adapter key
    if battery_wh and math.isclose(val, battery_wh, abs_tol=1.0):
        if not source_key or not any(k in source_key.lower() for k in ["adapter", "charger", "power supply"]):
            return None, "adapter_w_battery_duplicate_rejected"

    return val, None


def validate_battery_cells(value: Any, context: dict | None = None) -> tuple[int | None, str | None]:
    """Validate battery cell count (2-8 cells)."""
    if is_placeholder(value):
        return None, "battery_cells_placeholder"
    val_str = str(value).strip()
    if re.search(r"\/|\bto\b|\bor\b|\b[-–]\b", val_str):
        return None, "battery_cells_ambiguous_range"
    try:
        val = int(value)
        if 2 <= val <= 8:
            return val, None
        return None, "battery_cells_out_of_range"
    except (ValueError, TypeError):
        m = re.search(r"\b([2-8])\s*-?cells?\b", val_str, re.I)
        if m:
            return int(m.group(1)), None
        return None, "battery_cells_invalid_format"


# =============================================================================
# 8. Physical Chassis & Dimensions Validators
# =============================================================================

KNOWN_COLORS: set[str] = {
    "black", "white", "silver", "gray", "grey", "dark shadow gray",
    "eclipse black", "mica silver", "platinum", "blue", "luna grey",
    "mecha gray", "cosmos gray", "abyssal black", "obsidian black",
    "arctic grey", "storm grey", "shadow black",
}


def validate_color(value: Any, model_name: str | None = None) -> tuple[str | None, str | None]:
    """Validate chassis external color name."""
    if is_placeholder(value):
        return None, "color_placeholder"
    val = clean_text(value).strip()

    # Reject if too long
    if len(val) >= 30:
        return None, "color_too_long"

    # Reject display gamut or panel strings
    if re.search(r"\b(srgb|ntsc|dci-p3|gamut|ips|fhd|qhd|oled)\b", val, re.I):
        return None, "color_display_token_rejected"

    # Reject if equals model name or title
    if model_name and val.lower() == model_name.strip().lower():
        return None, "color_equals_model_name"

    # Check for presence of recognized color word
    val_low = val.lower()
    if any(c in val_low for c in KNOWN_COLORS):
        return val, None

    return None, "color_unrecognized"


def validate_weight(value: Any, context: dict | None = None) -> tuple[float | None, str | None]:
    """Validate laptop weight in kg (0.7 to 4.5 kg)."""
    if is_placeholder(value):
        return None, "weight_placeholder"
    try:
        val = float(value)
        if 0.7 <= val <= 4.5:
            return round(val, 2), None
        return None, "weight_out_of_range"
    except (ValueError, TypeError):
        # Convert lb or g
        val_str = str(value)
        m_kg = re.search(r"\b(\d+(?:\.\d+)?)\s*kg\b", val_str, re.I)
        if m_kg:
            val = float(m_kg.group(1))
            if 0.7 <= val <= 4.5:
                return round(val, 2), None
            return None, "weight_out_of_range"

        m_lb = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:lb|lbs|pound)\b", val_str, re.I)
        if m_lb:
            val = round(float(m_lb.group(1)) * 0.45359237, 2)
            if 0.7 <= val <= 4.5:
                return val, None
            return None, "weight_out_of_range"

        m_g = re.search(r"\b(\d{3,4})\s*g\b", val_str, re.I)
        if m_g:
            val = round(float(m_g.group(1)) / 1000.0, 2)
            if 0.7 <= val <= 4.5:
                return val, None

        return None, "weight_invalid_format"


def normalize_dimensions(
    w: Any, d: Any, h: Any, weight_hint: float | None = None
) -> tuple[float | None, float | None, float | None]:
    """Normalize laptop chassis dimensions ensuring metric mm and width >= depth >= height."""
    vals = []
    for dim in [w, d, h]:
        if dim is not None and not is_placeholder(dim):
            try:
                vals.append(float(dim))
            except (ValueError, TypeError):
                pass

    if len(vals) < 3:
        # If partial dimensions provided, validate individual bounds
        w_res = float(w) if w and not is_placeholder(w) and 250 <= float(w) <= 460 else None
        d_res = float(d) if d and not is_placeholder(d) and 170 <= float(d) <= 320 else None
        h_res = float(h) if h and not is_placeholder(h) and 8 <= float(h) <= 40 else None
        return w_res, d_res, h_res

    v1, v2, v3 = vals[0], vals[1], vals[2]

    # Detect cm: if all three values < 60 and the smallest < 4.5 (thickness in cm)
    if all(x < 60 for x in [v1, v2, v3]) and min(v1, v2, v3) < 4.5:
        v1 *= 10.0
        v2 *= 10.0
        v3 *= 10.0

    # Ensure axis order: width >= depth >= height
    sorted_dims = sorted([v1, v2, v3], reverse=True)
    norm_w, norm_d, norm_h = sorted_dims[0], sorted_dims[1], sorted_dims[2]

    # Plausible laptop ranges (mm): width 250-460, depth 170-320, height 8-40
    if not (250 <= norm_w <= 460 and 170 <= norm_d <= 320 and 8 <= norm_h <= 40):
        return None, None, None

    return round(norm_w, 1), round(norm_d, 1), round(norm_h, 1)


# =============================================================================
# 9. Connectivity Validators
# =============================================================================

def validate_wifi(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate Wi-Fi standard naming."""
    if is_placeholder(value):
        return None, "wifi_placeholder"
    val = clean_text(value)
    # Reject memory, GPU, or port noise
    if any(bad in val.upper() for bad in ["DDR", "RAM", "MX330", "TYPE-C", "USB-A", "DOS", "WUXGA", "PCIE"]):
        return None, "wifi_noise_rejected"
    m = re.search(r"\b(Wi-?Fi\s*[67][E]?|802\.11[a-z/]+|IEEE\s*802\.11\w*)\b", val, re.I)
    if m:
        return m.group(0).strip(), None
    return None, "wifi_unrecognized"


def validate_bluetooth(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate Bluetooth version specification."""
    if is_placeholder(value):
        return None, "bluetooth_placeholder"
    val = clean_text(value)
    m = re.search(r"\b(?:Bluetooth|BT)\s*v?([4-6]\.[0-4])\b", val, re.I)
    if m:
        return f"Bluetooth {m.group(1)}", None
    m_bare = re.search(r"\b([4-6]\.[0-4])\b", val)
    if m_bare and 4.0 <= float(m_bare.group(1)) <= 6.0:
        return f"Bluetooth {m_bare.group(1)}", None
    return None, "bluetooth_unrecognized"


def validate_ethernet(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate wired Ethernet capability."""
    if is_placeholder(value):
        return None, "ethernet_placeholder"
    val = clean_text(value)
    if re.search(r"\b(?:no|n/a|none|without)\b", val, re.I):
        return None, "ethernet_explicitly_absent"
    m = re.search(r"\b(\d+(?:\.\d+)?\s*Gigabit(?:\s*LAN|\s*Ethernet)?|Gigabit(?:\s*LAN|\s*Ethernet)?|GbE|RJ-?45|10/100/1000(?:\s*Mbps)?|Ethernet)\b", val, re.I)
    if m:
        return m.group(0).strip(), None
    return None, "ethernet_unrecognized"


def parse_ethernet_speed(text: str | None) -> str | None:
    """Parse canonical ethernet speed (100M|1G|2.5G|5G|10G|null) from connectivity text."""
    if not text:
        return None
    t = str(text).lower()
    if re.search(r"\b10\s*g(?:igabit)?\b", t):
        return "10G"
    if re.search(r"(?<![\d\.])5\s*g(?:igabit)?\b", t):
        return "5G"
    if re.search(r"\b2\.5\s*g(?:igabit)?\b", t):
        return "2.5G"
    if re.search(r"\b(?:1\s*g(?:igabit)?|gigabit|1000m|10\/100\/1000|100\/1000m|rj-?45|gbe)\b", t):
        return "1G"
    if re.search(r"\b(?:100m|10\/100|fast\s+ethernet)\b", t):
        return "100M"
    return None


def clean_ports_list(ports: list[str]) -> list[str]:
    """Clean footnote numbers, whitespace, marketing sentences, and duplicates from ports."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for p in ports:
        if not p:
            continue
        s = str(p)
        # Remove footnote clusters (e.g., " 14 15", " 7 8", "( 14)")
        s = re.sub(r"\(\s*\d+\s*\)", "", s)
        s = re.sub(r"\b(?:\d{1,2}\s+){1,4}\d{1,2}$", "", s.strip())
        # Remove marketing sentences
        if any(bad in s.lower() for bad in ["all the ports you need", "built to dominate", "connect with ease", "versatile connectivity", "let's duo it"]):
            continue
        # Remove placeholders like (TBD)
        s = re.sub(r"\(TBD\)", "", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip()
        if not s or s.lower() in ("no", "0", "none"):
            continue
        s_norm = s.lower()
        if s_norm not in seen:
            seen.add(s_norm)
            cleaned.append(s)
    return cleaned


def parse_ports_summary(all_ports_text: str | None) -> dict[str, Any]:
    """Parse ports_summary ({usb_a, usb_c, thunderbolt, hdmi, ethernet, sd_card, audio_jack})."""
    if not all_ports_text:
        return {
            "usb_a": 0,
            "usb_c": 0,
            "thunderbolt": False,
            "hdmi": False,
            "ethernet": False,
            "sd_card": False,
            "audio_jack": False,
        }
    t = str(all_ports_text).lower()
    m_usba = re.findall(r"(\d+)\s*(?:x|[×*])?\s*(?:usb\s*3|usb-a|type-a|usb\s*type-a)", t)
    usb_a = sum(int(x) for x in m_usba) if m_usba else (1 if ("type-a" in t or "usb-a" in t) else 0)

    m_usbc = re.findall(r"(\d+)\s*(?:x|[×*])?\s*(?:usb-c|type-c|usb\s*type-c|thunderbolt)", t)
    usb_c = sum(int(x) for x in m_usbc) if m_usbc else (1 if ("type-c" in t or "usb-c" in t) else 0)

    return {
        "usb_a": usb_a,
        "usb_c": usb_c,
        "thunderbolt": bool(re.search(r"thunderbolt", t)),
        "hdmi": bool(re.search(r"hdmi", t)),
        "ethernet": bool(re.search(r"rj-?45|ethernet|lan", t)),
        "sd_card": bool(re.search(r"sd|card\s*reader|microsd", t)),
        "audio_jack": bool(re.search(r"audio|headphone|3\.5mm|combo\s*jack", t)),
    }


# =============================================================================
# 10. Operating System Validators
# =============================================================================

def validate_os_name(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate and normalize operating system name."""
    if value is None:
        return None, "os_placeholder"
    raw_str = clean_text(value).strip()
    val_low = raw_str.lower()

    if val_low in ("none", "no os", "without os"):
        return "No OS", None
    if any(k in val_low for k in ["freedos", "free dos", "dos"]):
        return "FreeDOS", None

    if is_placeholder(value):
        return None, "os_placeholder"

    # Reject military durability or firmware tokens
    if any(bad in val_low for bad in ["mil-std", "uefi", "shell", "810h"]):
        return None, "os_noise_rejected"

    if re.search(r"\bwin(?:dows)?\s*11\b|\bwindows11\b|\bwin11\b", val_low):
        if "pro" in val_low:
            return "Windows 11 Pro", None
        return "Windows 11 Home", None

    if re.search(r"\bwin(?:dows)?\s*10\b|\bwindows10\b|\bwin10\b", val_low):
        if "pro" in val_low:
            return "Windows 10 Pro", None
        return "Windows 10 Home", None

    if "ubuntu" in val_low or "linux" in val_low:
        return "Ubuntu/Linux", None
    if "macos" in val_low or "mac os" in val_low:
        return "macOS", None

    return None, "os_unrecognized"


# =============================================================================
# 11. Audio & Webcam Validators
# =============================================================================

AUDIO_TECH_BRANDS: tuple[str, ...] = (
    "nahimic",
    "harman",
    "sonicmaster",
    "dolby",
    "dts",
    "bang & olufsen",
    "b&o",
    "waves",
    "maxx",
)


def validate_webcam(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate webcam resolution string."""
    if is_placeholder(value):
        return None, "webcam_placeholder"
    val = clean_text(value)
    # Reject Hz, WQXGA, microphone noise
    if any(bad in val.lower() for bad in ["hz", "wqxga", "microphone", "speaker"]):
        return None, "webcam_noise_rejected"
    m = re.search(r"\b(\d{3,4}\s*p|HD|FHD|QHD|\d+(?:\.\d+)?\s*(?:MP|M\b))\b", val, re.I)
    if m:
        return val, None
    return None, "webcam_unrecognized"


def validate_microphone(value: Any, context: dict | None = None) -> tuple[str | None, str | None]:
    """Validate microphone description."""
    if is_placeholder(value):
        return None, "mic_placeholder"
    val = clean_text(value).strip()
    val_low = val.lower()

    # Reject audio brand names (e.g. Nahimic Audio) as microphone
    if any(b in val_low for b in AUDIO_TECH_BRANDS):
        return None, "mic_audio_brand_rejected"

    # Normalize bare label or booleans to canonical description
    if val_low in ("microphone", "built-in microphone", "yes", "true"):
        return "Built-in Microphone", None

    # Reject speaker noise if not explicitly also mentioning microphone
    if "speaker" in val_low and "mic" not in val_low:
        return None, "mic_speaker_noise"

    mic_keywords = ("mic", "array", "dual", "stereo", "digital", "noise reduction")
    if not any(k in val_low for k in mic_keywords):
        return None, "mic_missing_keyword"

    return val, None


# =============================================================================
# Structural Validator (Post-Extraction Verification)
# =============================================================================

@dataclass
class Violation:
    field: str
    value: Any
    rule: str


def validate_structured(structured: dict[str, Any]) -> list[Violation]:
    """Walk a structured record and verify all populated fields pass validators."""
    violations: list[Violation] = []

    # 1. Identity
    ident = structured.get("identity", {})
    if ident.get("brand"):
        clean_b, err = validate_brand(ident["brand"])
        if err:
            violations.append(Violation("identity.brand", ident["brand"], err))
    if ident.get("manufacturer_part_number"):
        clean_mpn, err = validate_mpn(ident["manufacturer_part_number"])
        if err:
            violations.append(Violation("identity.manufacturer_part_number", ident["manufacturer_part_number"], err))

    # 2. CPU
    cpu = structured.get("cpu", {})
    if cpu.get("cores") is not None or cpu.get("threads") is not None:
        c, t, err = validate_cpu_cores_threads(cpu.get("cores"), cpu.get("threads"))
        if err:
            violations.append(Violation("cpu.cores_threads", (cpu.get("cores"), cpu.get("threads")), err))
    if cpu.get("cache_mb") is not None:
        cache_val, err = validate_cpu_cache(cpu.get("cache_mb"))
        if err:
            violations.append(Violation("cpu.cache_mb", cpu.get("cache_mb"), err))

    # 3. GPU
    gpu = structured.get("gpu", {})
    if gpu.get("vram_gb") is not None:
        v, err = validate_gpu_vram(gpu["vram_gb"], is_integrated=gpu.get("integrated", False))
        if err:
            violations.append(Violation("gpu.vram_gb", gpu["vram_gb"], err))

    # 4. Memory
    mem = structured.get("memory", {})
    if mem.get("speed") is not None:
        sp, err = validate_ram_speed(mem["speed"])
        if err:
            violations.append(Violation("memory.speed", mem["speed"], err))
    if mem.get("capacity_gb") is not None:
        cap, err = validate_ram_capacity(mem["capacity_gb"])
        if err:
            violations.append(Violation("memory.capacity_gb", mem["capacity_gb"], err))
    if mem.get("memory_type"):
        mt, err = validate_ram_type(mem["memory_type"])
        if err:
            violations.append(Violation("memory.memory_type", mem["memory_type"], err))

    # 5. Storage
    st = structured.get("storage", {})
    if st.get("capacity_gb") is not None:
        sc, err = validate_storage_capacity(st["capacity_gb"])
        if err:
            violations.append(Violation("storage.capacity_gb", st["capacity_gb"], err))
    if st.get("interface"):
        s_if, err = validate_storage_interface(st["interface"])
        if err:
            violations.append(Violation("storage.interface", st["interface"], err))
    if st.get("form_factor"):
        s_ff, err = validate_storage_form_factor(st["form_factor"])
        if err:
            violations.append(Violation("storage.form_factor", st["form_factor"], err))

    # 6. Display
    disp = structured.get("display", {})
    if disp.get("size_inches") is not None:
        ds, err = validate_display_size(disp["size_inches"])
        if err:
            violations.append(Violation("display.size_inches", disp["size_inches"], err))
    if disp.get("resolution"):
        r_str, w, h, err = validate_resolution(disp["resolution"])
        if err:
            violations.append(Violation("display.resolution", disp["resolution"], err))
    if disp.get("refresh_rate_hz") is not None:
        hz, err = validate_refresh_rate(disp["refresh_rate_hz"])
        if err:
            violations.append(Violation("display.refresh_rate_hz", disp["refresh_rate_hz"], err))
    if disp.get("panel_type"):
        pt, err = validate_panel_type(disp["panel_type"])
        if err:
            violations.append(Violation("display.panel_type", disp["panel_type"], err))

    # 7. Power
    pwr = structured.get("power_battery", {})
    if pwr.get("battery_capacity_wh") is not None:
        wh, err = validate_battery_capacity(pwr["battery_capacity_wh"])
        if err:
            violations.append(Violation("power_battery.battery_capacity_wh", pwr["battery_capacity_wh"], err))
    if pwr.get("power_adapter_w") is not None:
        pw, err = validate_power_adapter(pwr["power_adapter_w"], battery_wh=pwr.get("battery_capacity_wh"))
        if err:
            violations.append(Violation("power_battery.power_adapter_w", pwr["power_adapter_w"], err))

    # 8. Physical
    phys = structured.get("physical", {})
    if phys.get("weight_kg") is not None:
        wt, err = validate_weight(phys["weight_kg"])
        if err:
            violations.append(Violation("physical.weight_kg", phys["weight_kg"], err))
    if phys.get("color"):
        col, err = validate_color(phys["color"])
        if err:
            violations.append(Violation("physical.color", phys["color"], err))

    # 9. Connectivity
    conn = structured.get("connectivity", {})
    if conn.get("wifi"):
        wf, err = validate_wifi(conn["wifi"])
        if err:
            violations.append(Violation("connectivity.wifi", conn["wifi"], err))

    # 10. OS
    os_info = structured.get("operating_system", {})
    if os_info.get("name"):
        os_n, err = validate_os_name(os_info["name"])
        if err:
            violations.append(Violation("operating_system.name", os_info["name"], err))

    return violations


def validate_price_egp(value: Any) -> tuple[float | None, str | None]:
    """Validate laptop price in EGP (sanity range: 5,000 to 500,000 EGP)."""
    if is_placeholder(value) or value is None:
        return None, "price_missing"
    try:
        val = float(value)
        if 5000.0 <= val <= 500000.0:
            return val, None
        return None, f"price_out_of_sanity_range: {val:.2f} EGP"
    except (ValueError, TypeError):
        return None, "price_invalid_format"


def validate_cpu_full_name(
    value: Any,
    manufacturer: str | None = None,
    line: str | None = None,
    model: str | None = None,
) -> tuple[str | None, str | None]:
    """Validate and clean CPU full name string."""
    if is_placeholder(value) or not value:
        return None, "cpu_full_name_empty"
    val = clean_text(str(value)).strip()

    # Reject prose / architectural descriptions
    if re.search(r"^\s*Cores?\s+\d+\s*Cores?", val, re.I):
        return None, "cpu_full_name_is_core_description"
    if re.search(r"\b(?:Performance|Efficient)[- ]cores?\b", val, re.I):
        return None, "cpu_full_name_is_core_description"
    if re.search(r"\b(?:Raptor|Alder|Meteor|Arrow|Lunar|Tiger|Comet|Ice)\s+Lake\b", val, re.I):
        return None, "cpu_full_name_contains_codename"

    # Must contain recognized CPU identifier or manufacturer
    if not any(w in val.lower() for w in ["intel", "amd", "core", "ryzen", "snapdragon", "ultra", "celeron", "athlon"]):
        return None, "cpu_full_name_missing_cpu_brand"

    return val, None


# =============================================================================
# Title Parsers for Cross-Field & Conflict Reconciliation
# =============================================================================


def extract_title_ram(title: str | None) -> int | None:
    """Extract system RAM capacity in GB from title, avoiding GPU VRAM and screen sizes."""
    if not title:
        return None
    # 1. Remove screen size spans like 16-inch, 16", 15.6", 14-inch
    clean = re.sub(r'\b\d+(\.\d+)?\s*(?:-inch|["″\']|inch)\b', ' ', title, flags=re.I)

    # 2. Remove GPU spans with optional VRAM (ensuring we don't strip if followed by DDR/LPDDR/RAM/Memory)
    clean = re.sub(
        r'\b(?:GeForce\s*)?(?:RTX|GTX|RX|Arc)\s+[0-9A-Za-z]+(?:\s*(?:Ti|Super))?(?:\s*Laptop\s+GPU)?(?:\s*\d{1,2}\s*GB(?!\s*(?:DDR|LPDDR|RAM|Memory|SO-DIMM))(?:\s*GDDR\d*X?)?)?',
        ' ',
        clean,
        flags=re.I,
    )
    # Remove any remaining \d+GB GDDR...
    clean = re.sub(r'\b\d{1,2}\s*GB\s*GDDR\d*X?\b', ' ', clean, flags=re.I)

    # 3. Match explicit RAM: \d+\s*GB followed by DDR|LPDDR|RAM|Memory|on board
    m_exp = re.search(r'\b([48]|12|16|24|32|48|64|96|128)\s*(?:GB|G)\s*(?:RAM|DDR[45]?|LPDDR[45]?X?|Memory|on board)\b', clean, re.I)
    if m_exp:
        return int(m_exp.group(1))

    # 4. Single remaining \d+GB not followed by SSD|NVMe|HDD|TB|ROM
    candidates = re.findall(r'\b([48]|12|16|24|32|48|64|96|128)\s*(?:GB|G)\b(?!\s*(?:SSD|NVMe|PCIe|HDD|TB|ROM))', clean, re.I)
    if len(candidates) == 1:
        return int(candidates[0])
    return None


def extract_title_storage(title: str | None) -> int | None:
    """Extract storage capacity in GB from title, avoiding RAM and GPU VRAM."""
    if not title:
        return None
    # Exclude \d+GB LPDDR/DDR/RAM/Memory
    clean = re.sub(r'\b\d+\s*(?:GB|G)\s*(?:DDR[45]?|LPDDR[45]?X?|RAM|Memory|on board)\b', ' ', title, flags=re.I)
    # Also exclude GPU VRAM
    clean = re.sub(r'\b\d{1,2}\s*GB\s*GDDR\d*X?\b', ' ', clean, flags=re.I)

    # Now find storage: TB first or GB followed by SSD|NVMe|HDD|storage
    m_tb = re.search(r'\b([1248])\s*TB\b(?:\s*(?:SSD|NVMe|HDD|Storage|PCIe))?', clean, re.I)
    m_gb_ssd = re.search(r'\b(128|256|512|1024|2048)\s*(?:GB|G)\s*(?:SSD|NVMe|HDD|PCIe|Storage|EMMC)\b', clean, re.I)

    if m_tb:
        return int(m_tb.group(1)) * 1024
    if m_gb_ssd:
        return int(m_gb_ssd.group(1))

    # Fallback to single remaining storage-like size
    m_any = re.search(r'\b(128|256|512|1024|2048)\s*(?:GB|G)\b', clean, re.I)
    if m_any:
        return int(m_any.group(1))
    return None


# =============================================================================
# Authoritative Spec Databases & Cross-Field Consistency Validator
# =============================================================================

_DATA_DIR = Path(__file__).parent / "data"
_CONSISTENCY_CPU_SPECS: dict[str, dict[str, Any]] = {}
_CONSISTENCY_GPU_SPECS: dict[str, dict[str, Any]] = {}

_cpu_file = _DATA_DIR / "cpu_specs.json"
if _cpu_file.exists():
    try:
        with open(_cpu_file, "r", encoding="utf-8") as _f:
            _CONSISTENCY_CPU_SPECS = json.load(_f)
    except Exception:
        pass

_gpu_file = _DATA_DIR / "gpu_specs.json"
if _gpu_file.exists():
    try:
        with open(_gpu_file, "r", encoding="utf-8") as _f:
            _CONSISTENCY_GPU_SPECS = json.load(_f)
    except Exception:
        pass


def _lookup_gpu_spec(model_name: str | None) -> dict[str, Any] | None:
    if not model_name:
        return None
    m = model_name.strip()
    if m in _CONSISTENCY_GPU_SPECS:
        return _CONSISTENCY_GPU_SPECS[m]
    if not m.lower().startswith("geforce") and f"GeForce {m}" in _CONSISTENCY_GPU_SPECS:
        return _CONSISTENCY_GPU_SPECS[f"GeForce {m}"]
    clean = re.sub(r"\s+Laptop\s+GPU\b", "", m, flags=re.I).strip()
    if clean in _CONSISTENCY_GPU_SPECS:
        return _CONSISTENCY_GPU_SPECS[clean]
    if not clean.lower().startswith("geforce") and f"GeForce {clean}" in _CONSISTENCY_GPU_SPECS:
        return _CONSISTENCY_GPU_SPECS[f"GeForce {clean}"]
    return None


def validate_consistency(structured: dict[str, Any], raw_specs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Validate cross-field consistency across all hardware components.

    Rules that fail null the offending field and append to extraction_meta.rejected with
    rule: "consistency:<name>".
    """
    rejections: list[dict[str, Any]] = []

    # 1. CPU threads >= cores, threads/cores <= 2
    cpu = structured.setdefault("cpu", {})
    cores = cpu.get("cores")
    threads = cpu.get("threads")
    if cores is not None and threads is not None:
        if threads < cores or (cores > 0 and (threads / cores) > 2.0):
            val = threads
            cpu["threads"] = None
            rejections.append({
                "field": "cpu.threads",
                "value": val,
                "rule": "consistency:threads_cores_ratio",
            })

    # 2. CPU manufacturer matches line family
    mfg = cpu.get("manufacturer")
    line = cpu.get("line")
    if mfg and line:
        mfg_lower = mfg.lower()
        line_lower = line.lower()
        mismatch = False
        if "qualcomm" in mfg_lower:
            if not ("snapdragon" in line_lower):
                mismatch = True
        elif "amd" in mfg_lower:
            if any(x in line_lower for x in ["intel", "core", "snapdragon", "ultra", "xeon"]):
                mismatch = True
            elif not any(x in line_lower for x in ["ryzen", "athlon", "threadripper"]):
                mismatch = True
        elif "intel" in mfg_lower:
            if any(x in line_lower for x in ["ryzen", "athlon", "snapdragon", "adreno"]):
                mismatch = True
            elif not any(x in line_lower for x in ["core", "ultra", "celeron", "pentium", "xeon", "atom", "processor", "n-series"]):
                mismatch = True
        if mismatch:
            val = line
            cpu["line"] = None
            rejections.append({
                "field": "cpu.line",
                "value": val,
                "rule": "consistency:cpu_mfg_line_mismatch",
            })

    # 8. Same cpu.model must always give the same cores/threads from spec DB
    model = cpu.get("model")
    if model:
        m_str = str(model).strip()
        spec = _CONSISTENCY_CPU_SPECS.get(m_str)
        if spec:
            db_cores = spec.get("cores")
            db_threads = spec.get("threads")
            if db_cores is not None:
                if cpu.get("cores") is not None and cpu.get("cores") != db_cores:
                    rejections.append({
                        "field": "cpu.cores",
                        "value": cpu.get("cores"),
                        "rule": "consistency:cpu_cores_overridden_by_spec_db",
                    })
                cpu["cores"] = db_cores
            if db_threads is not None:
                if cpu.get("threads") is not None and cpu.get("threads") != db_threads:
                    rejections.append({
                        "field": "cpu.threads",
                        "value": cpu.get("threads"),
                        "rule": "consistency:cpu_threads_overridden_by_spec_db",
                    })
                cpu["threads"] = db_threads

    # 3. aspect_ratio == reduced(width, height); never copied from text
    disp = structured.setdefault("display", {})
    res = disp.get("resolution")
    if res:
        m_res = re.search(r"(\d{3,4})\s*[xX*×]\s*(\d{3,4})", str(res))
        if m_res:
            w, h = int(m_res.group(1)), int(m_res.group(2))
            g = math.gcd(w, h)
            rw, rh = w // g, h // g
            if (rw, rh) == (16, 9) or (rw, rh) == (64, 27) or (rw, rh) == (21, 9):
                reduced_ar = f"{rw}:{rh}"
            elif (rw, rh) in ((8, 5), (16, 10)):
                reduced_ar = "16:10"
            elif (rw, rh) == (3, 2):
                reduced_ar = "3:2"
            elif (rw, rh) == (4, 3):
                reduced_ar = "4:3"
            else:
                ratio = w / h
                if abs(ratio - 16 / 9) < 0.03:
                    reduced_ar = "16:9"
                elif abs(ratio - 16 / 10) < 0.03:
                    reduced_ar = "16:10"
                elif abs(ratio - 3 / 2) < 0.03:
                    reduced_ar = "3:2"
                else:
                    reduced_ar = f"{rw}:{rh}"
            curr_ar = disp.get("aspect_ratio")
            if curr_ar and curr_ar != reduced_ar:
                val = curr_ar
                disp["aspect_ratio"] = reduced_ar
                rejections.append({
                    "field": "display.aspect_ratio",
                    "value": val,
                    "rule": "consistency:aspect_ratio_mismatch",
                })
            elif not curr_ar:
                disp["aspect_ratio"] = reduced_ar

    # 4. Storage form_factor 2.5 incompatible with NVMe/M.2 interface
    stg = structured.setdefault("storage", {})
    ff = stg.get("form_factor")
    if ff and str(ff).strip() == "2.5":
        iface = str(stg.get("interface") or "")
        stg_type = str(stg.get("storage_type") or "")
        if any(kw in iface.upper() or kw in stg_type.upper() for kw in ["NVME", "M.2", "PCIE"]):
            val = ff
            stg["form_factor"] = None
            rejections.append({
                "field": "storage.form_factor",
                "value": val,
                "rule": "consistency:form_factor_nvme_incompatible",
            })

    # 5. iGPU => vram_gb is null; dGPU vram in authoritative table
    gpu = structured.setdefault("gpu", {})
    is_int = gpu.get("integrated") is True
    vram = gpu.get("vram_gb")
    if is_int and vram is not None:
        val = vram
        gpu["vram_gb"] = None
        rejections.append({
            "field": "gpu.vram_gb",
            "value": val,
            "rule": "consistency:igpu_vram_not_allowed",
        })
    elif not is_int and vram is not None:
        model_name = gpu.get("model") or ""
        spec = _lookup_gpu_spec(model_name)
        if spec:
            allowed = spec.get("allowed_vram", [])
            if vram not in allowed:
                val = vram
                if len(allowed) == 1:
                    gpu["vram_gb"] = allowed[0]
                else:
                    gpu["vram_gb"] = None
                rejections.append({
                    "field": "gpu.vram_gb",
                    "value": val,
                    "rule": "consistency:dgpu_vram_invalid_for_model",
                })

    # 6. max_supported_gb >= capacity_gb; if equal and not LPDDR/soldered, treat as unverified
    mem = structured.setdefault("memory", {})
    cap = mem.get("capacity_gb")
    max_ram = mem.get("max_supported_gb")
    m_type = str(mem.get("memory_type") or "").upper()
    is_soldered = "LPDDR" in m_type or "SOLDERED" in m_type or "ON BOARD" in m_type

    if max_ram is not None:
        if cap is not None and max_ram < cap:
            val = max_ram
            mem["max_supported_gb"] = None
            rejections.append({
                "field": "memory.max_supported_gb",
                "value": val,
                "rule": "consistency:max_ram_less_than_capacity",
            })
        elif cap is not None and max_ram == cap:
            if not is_soldered:
                row_has_max = False
                if raw_specs:
                    for k, v in raw_specs.items():
                        if any(w in k.lower() for w in ["max", "maximum", "up to"]) and str(max_ram) in str(v):
                            row_has_max = True
                            break
                if not row_has_max:
                    val = max_ram
                    mem["max_supported_gb"] = None
                    rejections.append({
                        "field": "memory.max_supported_gb",
                        "value": val,
                        "rule": "consistency:max_ram_equals_installed_unverified",
                    })
        elif max_ram > 128:
            val = max_ram
            mem["max_supported_gb"] = None
            rejections.append({
                "field": "memory.max_supported_gb",
                "value": val,
                "rule": "consistency:max_ram_exceeds_platform_limit",
            })

    # 7. battery Wh must not equal adapter W
    pwr = structured.setdefault("power_battery", {})
    adapter = pwr.get("power_adapter_w")
    wh = pwr.get("battery_capacity_wh")
    if adapter is not None and wh is not None:
        if abs(float(adapter) - float(wh)) < 1e-3:
            val = adapter
            pwr["power_adapter_w"] = None
            rejections.append({
                "field": "power_battery.power_adapter_w",
                "value": val,
                "rule": "consistency:adapter_matches_battery_wh",
            })

    # Record all consistency rejections in metadata
    meta = structured.setdefault("extraction_meta", {})
    meta.setdefault("rejected", []).extend(rejections)
    return rejections


