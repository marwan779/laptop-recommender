"""Layers 5 & 7: Physical Validation Layer.

Applies hardware physics constraints and CPU-specific constraints to
validate both deterministically extracted specs and AI fallback candidates.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Valid standard laptop RAM capacities (GB)
VALID_RAM_CAPACITIES: Set[int] = {4, 8, 12, 16, 20, 24, 32, 36, 40, 48, 64, 96, 128, 192}

# Valid display panel types
VALID_PANEL_TYPES: Set[str] = {
    "IPS", "OLED", "AMOLED", "TN", "VA", "Mini-LED", "Liquid Retina", "Retina", "WVA"
}

# Standard refresh rates (Hz)
VALID_REFRESH_RATES: Set[int] = {60, 75, 90, 120, 144, 165, 240, 300, 360, 480}


class PhysicalValidator:
    """Enforces hardware physics rules and CPU-specific bounds."""

    @classmethod
    def validate_memory_capacity(
        cls, value: Any, cpu_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate RAM capacity in GB against hardware norms and CPU max memory."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if val not in VALID_RAM_CAPACITIES:
            return False, None, f"invalid_ram_capacity_{val}gb"

        if cpu_context and cpu_context.get("max_memory_gb"):
            max_allowed = cpu_context["max_memory_gb"]
            if val > max_allowed:
                return False, None, f"exceeds_cpu_max_{max_allowed}gb"

        return True, val, None

    @classmethod
    def validate_memory_type(
        cls, value: Any, cpu_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate RAM generation (DDR4, DDR5, LPDDR5X) against CPU supported memory."""
        if not value or not isinstance(value, str):
            return False, None, "type_error"

        val_norm = value.strip().upper()
        # Canonicalize
        type_mapping = {
            "DDR4": "DDR4",
            "DDR 4": "DDR4",
            "DDR5": "DDR5",
            "DDR 5": "DDR5",
            "LPDDR4": "LPDDR4",
            "LPDDR4X": "LPDDR4X",
            "LPDDR5": "LPDDR5",
            "LPDDR5X": "LPDDR5X",
            "UNIFIED MEMORY": "Unified Memory",
            "UNIFIED": "Unified Memory",
        }
        canonical_type = type_mapping.get(val_norm)
        if not canonical_type:
            return False, None, f"unknown_memory_type_{value}"

        if cpu_context and cpu_context.get("supported_memory"):
            supported = [m.upper() for m in cpu_context["supported_memory"]]
            # Check family compatibility: e.g. DDR5 matches DDR5 / LPDDR5 / LPDDR5X
            is_supported = False
            for s in supported:
                if s in canonical_type.upper() or canonical_type.upper() in s:
                    is_supported = True
                    break
            if not is_supported and "Unified Memory" not in canonical_type:
                return False, None, f"memory_type_{canonical_type}_incompatible_with_cpu_{supported}"

        return True, canonical_type, None

    @classmethod
    def validate_display_size(
        cls, value: Any
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate screen size in inches (standard laptops: 10.0\" to 18.5\")."""
        try:
            val = round(float(value), 1)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if 10.0 <= val <= 18.5:
            return True, val, None
        return False, None, f"display_size_{val}_out_of_bounds"

    @classmethod
    def validate_refresh_rate(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate display refresh rate (60Hz to 480Hz)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if 60 <= val <= 480:
            return True, val, None
        return False, None, f"refresh_rate_{val}hz_out_of_bounds"

    @classmethod
    def validate_battery_capacity(
        cls, value: Any
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate battery capacity in Wh (strictly 25.0Wh to 99.9Wh FAA limit)."""
        try:
            val = round(float(value), 1)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if 25.0 <= val <= 99.9:
            return True, val, None
        return False, None, f"battery_{val}wh_out_of_bounds"

    @classmethod
    def validate_power_adapter(
        cls, value: Any, cpu_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate AC power adapter wattage (30W to 350W)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if 30 <= val <= 350:
            if cpu_context and cpu_context.get("base_power_w"):
                # Power adapter must at least meet CPU base power
                cpu_pwr = cpu_context["base_power_w"]
                if val < cpu_pwr:
                    return False, None, f"adapter_{val}w_insufficient_for_cpu_{cpu_pwr}w"
            return True, val, None
        return False, None, f"adapter_{val}w_out_of_bounds"

    @classmethod
    def validate_weight(
        cls, value: Any
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate laptop weight in kg (0.7kg to 5.5kg)."""
        try:
            val = round(float(value), 2)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if 0.7 <= val <= 5.5:
            return True, val, None
        return False, None, f"weight_{val}kg_out_of_bounds"

    @classmethod
    def validate_gpu_vram(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate discrete GPU VRAM capacity in GB (2GB to 24GB)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if val in {2, 4, 6, 8, 10, 12, 16, 24}:
            return True, val, None
        return False, None, f"gpu_vram_{val}gb_out_of_bounds"

    @classmethod
    def validate_mpn(
        cls, value: Any
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate manufacturer part number / SKU against hardware specs and generic words."""
        if not value or not isinstance(value, str):
            return False, None, "type_error"
        val = value.strip()
        val_upper = val.upper()
        # Reject hardware specs keywords
        if any(term in val_upper for term in ["RAM", "SSD", "HDD", "RTX", "GTX", "GEFORCE", "INTEL", "RYZEN", "WINDOWS", "FREEDOS"]):
            return False, None, "mpn_contains_specs_keyword"
        # Reject generic words
        if val_upper in {"NONE", "N/A", "LAPTOP", "GAMING LAPTOP", "NOTEBOOK"}:
            return False, None, "generic_word_rejected"
        if len(val) < 3 or len(val) > 40:
            return False, None, "mpn_invalid_length"
        return True, val, None

    @classmethod
    def validate_family(
        cls, value: Any
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate laptop family / series against specs words and generic nouns."""
        if not value or not isinstance(value, str):
            return False, None, "type_error"
        val = value.strip()
        val_upper = val.upper()
        if any(term in val_upper for term in ["RAM", "SSD", "RTX", "GTX", "INTEL", "RYZEN"]):
            return False, None, "family_contains_specs_keyword"
        if val_upper in {"NONE", "N/A", "LAPTOP", "GAMING LAPTOP"}:
            return False, None, "generic_word_rejected"
        return True, val.title(), None

    @classmethod
    def normalize_dimensions(
        cls, w: Any, d: Any, h: Any
    ) -> Tuple[bool, Optional[float], Optional[float], Optional[float], Optional[str]]:
        """Normalize and validate chassis dimensions in metric mm, ensuring width >= depth >= height."""
        vals = []
        for dim in [w, d, h]:
            if dim is not None:
                try:
                    vals.append(float(dim))
                except (ValueError, TypeError):
                    pass

        if len(vals) < 3:
            return False, None, None, None, "insufficient_dimensions"

        v1, v2, v3 = vals[0], vals[1], vals[2]

        # Detect cm: if all three values < 60 and the smallest < 4.5
        if all(x < 60 for x in [v1, v2, v3]) and min(v1, v2, v3) < 4.5:
            v1 *= 10.0
            v2 *= 10.0
            v3 *= 10.0

        # Sort descending: width >= depth >= height
        sorted_dims = sorted([v1, v2, v3], reverse=True)
        norm_w, norm_d, norm_h = sorted_dims[0], sorted_dims[1], sorted_dims[2]

        # Plausible laptop ranges (mm): width 250-460, depth 170-320, height 8-40
        if not (250.0 <= norm_w <= 460.0 and 170.0 <= norm_d <= 320.0 and 8.0 <= norm_h <= 40.0):
            return False, None, None, None, f"dimensions_out_of_bounds_{norm_w}x{norm_d}x{norm_h}"

        return True, round(norm_w, 1), round(norm_d, 1), round(norm_h, 1), None

    @classmethod
    def validate_dimension(
        cls, value: Any, dim_type: str = "width"
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate individual chassis dimension in metric mm, converting cm if detected."""
        if value is None:
            return True, None, None
        try:
            val = float(value)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if dim_type == "height":
            if 0.5 <= val < 6.0:
                val *= 10.0
            if 6.0 <= val <= 60.0:
                return True, round(val, 2), None
            return False, None, f"height_out_of_bounds_{val}"
        elif dim_type == "width":
            if 15.0 <= val < 60.0:
                val *= 10.0
            if 180.0 <= val <= 500.0:
                return True, round(val, 2), None
            return False, None, f"width_out_of_bounds_{val}"
        elif dim_type == "depth":
            if 10.0 <= val < 45.0:
                val *= 10.0
            if 140.0 <= val <= 400.0:
                return True, round(val, 2), None
            return False, None, f"depth_out_of_bounds_{val}"

        return True, round(val, 2), None

    @classmethod
    def validate_panel_type(
        cls, value: Any
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate display panel technology (IPS, OLED, AMOLED, TN, VA, Mini-LED)."""
        if not value or not isinstance(value, str):
            return False, None, "type_error"
        val = value.strip().upper()
        valid_map = {
            "IPS": "IPS",
            "IPS-LEVEL": "IPS",
            "IPS LEVEL": "IPS",
            "OLED": "OLED",
            "AMOLED": "AMOLED",
            "TN": "TN",
            "VA": "VA",
            "WVA": "WVA",
            "MINI-LED": "Mini-LED",
            "MINI LED": "Mini-LED",
            "MINILED": "Mini-LED",
        }
        for k, v in valid_map.items():
            if re.search(r"\b" + re.escape(k) + r"\b", val):
                return True, v, None
        return False, None, f"invalid_panel_type_{value}"

    @classmethod
    def validate_webcam(
        cls, value: Any
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate webcam resolution string."""
        if not value or not isinstance(value, str):
            return False, None, "type_error"
        val = value.strip()
        m = re.search(r"\b(\d{3,4}\s*p|HD|FHD|QHD|\d+(?:\.\d+)?\s*(?:MP|M\b))\b", val, re.I)
        if m:
            return True, val, None
        return False, None, f"webcam_unrecognized_{val}"

    @classmethod
    def validate_speaker_count(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate speaker count (standard laptops: 1 to 8 speakers)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"

        if 1 <= val <= 8:
            return True, val, None
        return False, None, f"speaker_count_{val}_out_of_bounds"

    @classmethod
    def validate_brightness(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate display brightness in nits (standard laptops: 150 to 3000 nits)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"
        if 150 <= val <= 3000:
            return True, val, None
        return False, None, f"brightness_{val}_out_of_bounds"

    @classmethod
    def validate_response_time(
        cls, value: Any
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate display response time in ms (gaming/creator laptops: 0.1 to 35.0 ms)."""
        try:
            val = float(value)
        except (ValueError, TypeError):
            return False, None, "type_error"
        if 0.1 <= val <= 35.0:
            return True, round(val, 2), None
        return False, None, f"response_time_{val}_out_of_bounds"

    @classmethod
    def validate_npu_tops(
        cls, value: Any
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate AI NPU TOPS (modern laptop silicon: 5 to 150 TOPS)."""
        try:
            val = float(value)
        except (ValueError, TypeError):
            return False, None, "type_error"
        if 5.0 <= val <= 150.0:
            return True, round(val, 1), None
        return False, None, f"npu_tops_{val}_out_of_bounds"

    @classmethod
    def validate_gpu_boost(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate GPU boost clock in MHz (laptop discrete GPUs: 500 to 3200 MHz)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"
        if 500 <= val <= 3200:
            return True, val, None
        return False, None, f"gpu_boost_{val}_out_of_bounds"

    @classmethod
    def validate_gpu_power(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate GPU TGP / power in watts (laptop discrete GPUs: 20 to 250 W)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"
        if 20 <= val <= 250:
            return True, val, None
        return False, None, f"gpu_power_{val}w_out_of_bounds"

    @classmethod
    def validate_bluetooth(
        cls, value: Any
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate Bluetooth version specification."""
        if not value or not isinstance(value, str):
            return False, None, "type_error"
        val = value.strip()
        m = re.search(r"\b(?:Bluetooth|BT)?\s*v?([4-6](?:\.[0-4])?)\b", val, re.I)
        if m:
            ver = m.group(1)
            if "." not in ver:
                ver = f"{ver}.0"
            return True, f"Bluetooth {ver}", None
        return False, None, f"bluetooth_unrecognized_{val}"

    @classmethod
    def validate_warranty_years(
        cls, value: Any
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Validate warranty duration in years (typically 1 to 5 years)."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, None, "type_error"
        if 1 <= val <= 5:
            return True, val, None
        return False, None, f"warranty_years_{val}_out_of_bounds"

    @classmethod
    def validate_field(
        cls,
        field_path: str,
        value: Any,
        cpu_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Any, Optional[str]]:
        """Dispatch validation for any specific canonical field path."""
        if value is None:
            return True, None, None

        if field_path == "memory.capacity_gb":
            return cls.validate_memory_capacity(value, cpu_context)
        elif field_path == "memory.memory_type":
            return cls.validate_memory_type(value, cpu_context)
        elif field_path == "display.size_inches":
            return cls.validate_display_size(value)
        elif field_path == "display.refresh_rate_hz":
            return cls.validate_refresh_rate(value)
        elif field_path == "display.panel_type":
            return cls.validate_panel_type(value)
        elif field_path == "display.brightness_nits":
            return cls.validate_brightness(value)
        elif field_path == "display.response_time_ms":
            return cls.validate_response_time(value)
        elif field_path == "cpu.npu_tops":
            return cls.validate_npu_tops(value)
        elif field_path == "gpu.boost_clock_mhz":
            return cls.validate_gpu_boost(value)
        elif field_path == "gpu.tdp_w":
            return cls.validate_gpu_power(value)
        elif field_path == "power_battery.battery_capacity_wh":
            return cls.validate_battery_capacity(value)
        elif field_path == "power_battery.power_adapter_w":
            return cls.validate_power_adapter(value, cpu_context)
        elif field_path == "physical.weight_kg":
            return cls.validate_weight(value)
        elif field_path == "physical.width_mm":
            return cls.validate_dimension(value, "width")
        elif field_path == "physical.depth_mm":
            return cls.validate_dimension(value, "depth")
        elif field_path == "physical.height_mm":
            return cls.validate_dimension(value, "height")
        elif field_path == "gpu.vram_gb":
            return cls.validate_gpu_vram(value)
        elif field_path == "identity.manufacturer_part_number":
            return cls.validate_mpn(value)
        elif field_path == "identity.laptop_family":
            return cls.validate_family(value)
        elif field_path == "identity.warranty_years":
            return cls.validate_warranty_years(value)
        elif field_path == "audio_webcam.webcam_resolution":
            return cls.validate_webcam(value)
        elif field_path == "audio_webcam.speaker_count":
            return cls.validate_speaker_count(value)
        elif field_path == "connectivity.bluetooth":
            return cls.validate_bluetooth(value)
        elif field_path in (
            "connectivity.has_card_reader",
            "build_security.has_backlit_keyboard",
            "build_security.has_fingerprint",
            "build_security.has_numpad",
            "display.touchscreen",
            "audio_webcam.has_privacy_shutter",
            "audio_webcam.has_ir_camera",
            "memory.is_soldered",
        ):
            if isinstance(value, bool):
                return True, value, None
            if str(value).lower() in ("true", "yes", "1"):
                return True, True, None
            if str(value).lower() in ("false", "no", "0"):
                return True, False, None
            return False, None, "invalid_boolean"
        elif field_path == "connectivity.card_reader_type":
            if not value or not isinstance(value, str):
                return False, None, "type_error"
            v = value.strip()
            if any(term in v.lower() for term in ["sd", "microsd", "card reader"]):
                return True, v, None
            return False, None, f"invalid_card_reader_type_{v}"
        elif field_path == "connectivity.wifi":
            if not value or not isinstance(value, str):
                return False, None, "type_error"
            v = value.strip()
            m = re.search(r"\bwi-?fi\s*([67](?:e)?)\b", v, re.I)
            if m:
                return True, f"Wi-Fi {m.group(1).upper()}", None
            if any(t in v.lower() for t in ["wi-fi", "wifi", "802.11"]):
                return True, v, None
            return False, None, f"invalid_wifi_{v}"
        elif field_path == "operating_system.name":
            if not value or not isinstance(value, str):
                return False, None, "type_error"
            v = value.strip()
            if any(term in v.lower() for term in ["windows", "dos", "freedos", "linux", "ubuntu", "macos", "chrome"]):
                return True, v, None
            return False, None, f"invalid_os_{v}"

        # Default pass-through for other fields
        return True, value, None


