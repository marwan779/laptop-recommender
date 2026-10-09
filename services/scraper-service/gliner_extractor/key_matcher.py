"""Direct Table Key Matcher & Value Normalizer.

Maps raw scraped table keys to catalog-service schema columns
deterministically, while isolating compound fields for GLiNER extraction.
"""

from __future__ import annotations

import re
from typing import Any


class DirectKeyMatcher:
    """Deterministic matcher for table specifications."""

    # Canonical alias dictionary mapping lowercase scraped keys to (section, field)
    DIRECT_KEY_MAP: dict[str, tuple[str, str]] = {
        # Processor
        "processor manufacturer": ("cpu", "manufacturer"),
        "processor type": ("cpu", "line"),
        "processor series": ("cpu", "series"),
        "processor model": ("cpu", "model"),
        "processor speed": ("cpu", "clock_speed"),
        "processor core": ("cpu", "cores"),
        "processor threads": ("cpu", "threads"),
        "cpu": ("cpu", "full_name"),
        "processor": ("cpu", "full_name"),
        "processor cpu": ("cpu", "full_name"),
        "cpu type": ("cpu", "full_name"),
        "cpu model": ("cpu", "model"),
        "processor family": ("cpu", "line"),

        # Graphics
        "graphics controller manufacturer": ("gpu", "manufacturer"),
        "graphics controller model": ("gpu", "model"),
        "graphics manufacturer": ("gpu", "manufacturer"),
        "graphics model": ("gpu", "model"),
        "graphics card": ("gpu", "model"),
        "video graphics": ("gpu", "model"),
        "video card": ("gpu", "model"),
        "graphics processor": ("gpu", "model"),
        "graphics memory capacity": ("gpu", "vram_gb"),
        "graphics memory": ("gpu", "vram_gb"),
        "video memory": ("gpu", "vram_gb"),
        "graphics memory accessibility": ("gpu", "accessibility"),
        "graphics memory technology": ("gpu", "memory_technology"),
        "maximum graphics power": ("gpu", "tdp_w"),
        "maximum graphics power tgp": ("gpu", "tdp_w"),
        "gpu boost clock": ("gpu", "boost_clock"),
        "gpu tgp": ("gpu", "tdp_w"),
        "gpu power": ("gpu", "tdp_w"),
        "graphics": ("gpu", "model"),
        "gpu": ("gpu", "model"),
        "integrated gpu": ("gpu", "model"),
        "intergrated gpu": ("gpu", "model"),

        # Display
        "screen size": ("display", "size_inches"),
        "display screen type": ("display", "panel_type"),
        "display screen technology": ("display", "panel_technology"),
        "touchscreen": ("display", "touchscreen"),
        "screen resolution": ("display", "resolution"),
        "standard refresh rate": ("display", "refresh_rate_hz"),
        "refresh rate": ("display", "refresh_rate_hz"),
        "aspect ratio": ("display", "aspect_ratio"),
        "resolution": ("display", "resolution"),
        "display": ("display", "summary"),
        "screen": ("display", "summary"),
        "size": ("display", "size_inches"),
        "panel size": ("display", "size_inches"),

        # Memory / RAM
        "standard memory": ("memory", "capacity_gb"),
        "memory": ("memory", "capacity_gb"),
        "ram": ("memory", "capacity_gb"),
        "ram memory": ("memory", "capacity_gb"),
        "memory ram": ("memory", "capacity_gb"),
        "installed memory": ("memory", "capacity_gb"),
        "system memory": ("memory", "capacity_gb"),
        "maximum supported system memory": ("memory", "max_supported_gb"),
        "maximum memory supported": ("memory", "max_supported_gb"),
        "system memory technology": ("memory", "memory_type"),
        "memory technology": ("memory", "memory_type"),
        "system memory speed mt s": ("memory", "speed"),
        "system memory speed": ("memory", "speed"),
        "memory speed": ("memory", "speed"),
        "memory slots": ("memory", "slot_count"),
        "ram slots": ("memory", "slot_count"),

        # Storage
        "total solid state drive capacity": ("storage", "capacity_gb"),
        "solid state drive interface": ("storage", "interface"),
        "ssd form factor": ("storage", "form_factor"),
        "storage": ("storage", "summary"),
        "internal storage": ("storage", "summary"),
        "hard drive": ("storage", "summary"),
        "hard disk ssd": ("storage", "summary"),
        "storage capacity": ("storage", "capacity_gb"),
        "storage size": ("storage", "capacity_gb"),
        "hard disk capacity": ("storage", "summary"),
        "hard disk size": ("storage", "capacity_gb"),
        "hard drive capacity gb": ("storage", "capacity_gb"),
        "storage interface": ("storage", "interface"),
        "storage type": ("storage", "storage_type"),
        "hard drive type": ("storage", "storage_type"),
        "storage slots": ("storage", "slot_count"),
        "storage slot": ("storage", "slot_count"),

        # Battery & Power
        "battery energy": ("power_battery", "battery_capacity_wh"),
        "battery capacity": ("power_battery", "battery_capacity_wh"),
        "maximum power supply wattage": ("power_battery", "power_adapter_w"),
        "power adapter": ("power_battery", "power_adapter_w"),
        "number of cells": ("power_battery", "battery_cells"),
        "battery chemistry": ("power_battery", "battery_chemistry"),
        "battery": ("power_battery", "summary"),

        # Operating System
        "operating system": ("operating_system", "name"),
        "os": ("operating_system", "name"),

        # Physical
        "product color": ("physical", "color"),
        "color": ("physical", "color"),
        "weight (approximate)": ("physical", "weight_kg"),
        "weight": ("physical", "weight_kg"),
        "width": ("physical", "width_mm"),
        "depth": ("physical", "depth_mm"),
        "height": ("physical", "height_mm"),

        # Build & Peripherals
        "finger print reader": ("build", "has_fingerprint"),
        "keyboard backlight": ("build", "has_backlit_keyboard"),
        "pointing device type": ("build", "pointing_device"),
        "security features": ("build", "security_features"),

        # Audio & Webcam
        "number of speakers": ("audio", "speaker_count"),
        "microphone": ("audio", "microphone"),
        "camera": ("webcam", "resolution"),
        "webcam": ("webcam", "resolution"),

        # Battery run time
        "maximum battery run time": ("power_battery", "max_run_time_hours"),

        # Identity
        "model": ("identity", "laptop_model"),
        "brand": ("identity", "brand"),
        "acer part number": ("identity", "manufacturer_part_number"),
        "part number": ("identity", "manufacturer_part_number"),
        "mpn": ("identity", "manufacturer_part_number"),
        "sku": ("identity", "manufacturer_part_number"),
    }

    # Value Parsers
    @staticmethod
    def parse_inches(val: str | None) -> float | None:
        if not val:
            return None
        # Check for 16", 15.6", 13.3″, 16-inch, 14 inch, etc.
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:["″”\'\u2033\u201c\u201d]|\s*-?inch|\s*-?in\b)', val, re.IGNORECASE)
        if m:
            num = float(m.group(1))
            if 10.0 <= num <= 22.0:
                return num
        # Check inside parentheses like 40.6 cm (16") or (15.6")
        m2 = re.search(r'\((\d+(?:\.\d+)?)\s*(?:["″”\'\u2033\u201c\u201d]|\s*inch)?\)', val)
        if m2:
            num = float(m2.group(1))
            if 10.0 <= num <= 22.0:
                return num
        # Plain float fallback if in reasonable laptop screen range (10 to 22 inches)
        m3 = re.search(r'\b(1[0-9](?:\.\d+)?)\b', val)
        if m3:
            num = float(m3.group(1))
            if 10.0 <= num <= 22.0:
                return num
        return None

    @staticmethod
    def parse_resolution(val: str | None) -> tuple[int | None, int | None]:
        if not val:
            return None, None
        m = re.search(r'(\d{3,4})\s*[xX*×]\s*(\d{3,4})', val)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    @staticmethod
    def parse_capacity_gb(val: str | None, ignore_up_to: bool = False) -> int | None:
        if not val:
            return None
        # If ignore_up_to is True and string only specifies an expansion limit, skip
        if ignore_up_to and re.search(r'^\s*up\s+to\b', val, re.IGNORECASE):
            return None

        # Clean "up to" clauses when ignore_up_to is requested
        clean_val = val
        if ignore_up_to:
            clean_val = re.sub(r'\bup\s+to\s+\d+\s*(?:TB|GB|T|G)?\b', '', val, flags=re.IGNORECASE)
            clean_val = re.sub(r'\bsupports?\s+up\s+to\s+\d+\s*(?:TB|GB|T|G)?\b', '', clean_val, flags=re.IGNORECASE)

        # Handle multi-module like "1x 16GB", "2 x 8GB", "2x 12GB" (avoid LPDDR5X collision)
        m_multi = re.search(r'\b([1-4])\s*[xX*×]\s*(\d+)\s*(TB|GB|T|G)?\b', clean_val, re.IGNORECASE)
        if m_multi:
            qty = int(m_multi.group(1))
            size = int(m_multi.group(2))
            unit = (m_multi.group(3) or "GB").upper()
            total = qty * size
            return total * 1024 if "T" in unit else total

        # Handle direct "16GB", "512 GB", "1 TB", "128GB LPDDR5X"
        m = re.search(r'(\d+)\s*(TB|GB|T|G)\b', clean_val, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            unit = m.group(2).upper()
            return num * 1024 if "T" in unit else num

        # If ignore_up_to was False, try full string fallback
        if not ignore_up_to:
            m_full = re.search(r'(\d+)\s*(TB|GB|T|G)\b', val, re.IGNORECASE)
            if m_full:
                num = int(m_full.group(1))
                unit = m_full.group(2).upper()
                return num * 1024 if "T" in unit else num

        # Fallback to plain number (e.g. "512", "16")
        m_fallback = re.match(r'^\s*(\d+)\s*$', val)
        return int(m_fallback.group(1)) if m_fallback else None

    @staticmethod
    def parse_cores(val: str | None) -> int | None:
        if not val:
            return None
        # e.g. "Tetradeca-core (14 Core)" or "8 Core" or "14"
        m = re.search(r'\((\d+)\s*Core', val, re.IGNORECASE)
        if m:
            return int(m.group(1))
        m2 = re.search(r'(\d+)\s*(?:Core|cores)', val, re.IGNORECASE)
        if m2:
            return int(m2.group(1))
        m3 = re.search(r'(\d+)', val)
        return int(m3.group(1)) if m3 else None

    @staticmethod
    def parse_num(val: str | None) -> float | None:
        if not val:
            return None
        m = re.search(r'(\d+(?:\.\d+)?)', val)
        return float(m.group(1)) if m else None

    @staticmethod
    def parse_int(val: str | None) -> int | None:
        if not val:
            return None
        m = re.search(r'(\d+)', val)
        return int(m.group(1)) if m else None

    @staticmethod
    def parse_bool(val: str | None) -> bool | None:
        if not val:
            return None
        v = val.strip().lower()
        if v in ("yes", "true", "1", "touchscreen", "touch"):
            return True
        if v in ("no", "false", "0", "non-touch"):
            return False
        return None

    @classmethod
    def match_specs(cls, raw_specs: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
        """Process raw specs dictionary.

        Returns:
            Tuple of:
            - structured: Initial structured dictionary populated with direct matches.
            - compound_rows: List of (row_key, row_value) that need AI / GLiNER extraction.
        """
        structured: dict[str, Any] = {
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
            },
            "gpu": {
                "manufacturer": None,
                "model": None,
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
            },
            "display": {
                "size_inches": None,
                "resolution": None,
                "resolution_width": None,
                "resolution_height": None,
                "panel_type": None,
                "refresh_rate_hz": None,
                "touchscreen": False,
            },
            "power_battery": {
                "battery_capacity_wh": None,
                "battery_cells": None,
                "power_adapter_w": None,
            },
            "connectivity": {
                "wifi": None,
                "bluetooth": None,
                "ports": [],
            },
            "operating_system": {
                "name": None,
            },
            "physical": {
                "color": None,
                "weight_kg": None,
                "width_mm": None,
                "depth_mm": None,
                "height_mm": None,
            },
            "build": {
                "has_fingerprint": None,
                "has_backlit_keyboard": None,
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
        }

        compound_rows: list[tuple[str, str]] = []
        collected_ports: list[str] = []

        for raw_k, raw_v in raw_specs.items():
            if not raw_v or not str(raw_v).strip():
                continue
            v_str = str(raw_v).strip()
            k_clean = raw_k.strip().lower()
            k_norm = re.sub(r'[^a-z0-9]+', ' ', k_clean).strip()

            # Detect direct port rows
            if re.search(r'\b(?:ports?|hdmi|usb|type-c|thunderbolt)\b', k_clean) and "supported" not in k_clean:
                if v_str.lower() not in ("no", "0"):
                    collected_ports.append(f"{raw_k}: {v_str}")
                continue

            # Detect wireless / bluetooth
            if "wireless" in k_clean or "lan standard" in k_clean:
                structured["connectivity"]["wifi"] = v_str
                continue
            if "bluetooth" in k_clean:
                structured["connectivity"]["bluetooth"] = v_str
                continue

            # Check if key is directly mapped (check exact clean key or normalized alphanumeric key)
            key_mapping = cls.DIRECT_KEY_MAP.get(k_clean) or cls.DIRECT_KEY_MAP.get(k_norm)
            if key_mapping:
                sec, field = key_mapping

                # Section-specific value parsers
                if field == "size_inches":
                    structured[sec][field] = cls.parse_inches(v_str)
                elif field == "resolution":
                    w, h = cls.parse_resolution(v_str)
                    structured[sec]["resolution"] = v_str
                    structured[sec]["resolution_width"] = w
                    structured[sec]["resolution_height"] = h
                elif field in ("capacity_gb", "max_supported_gb", "vram_gb"):
                    structured[sec][field] = cls.parse_capacity_gb(v_str)
                elif field == "cores":
                    structured[sec][field] = cls.parse_cores(v_str)
                elif field in ("threads", "refresh_rate_hz", "battery_cells", "slot_count", "tdp_w", "speaker_count"):
                    structured[sec][field] = cls.parse_int(v_str)
                elif field in ("battery_capacity_wh", "power_adapter_w", "weight_kg", "width_mm", "depth_mm", "height_mm", "max_run_time_hours"):
                    structured[sec][field] = cls.parse_num(v_str)
                elif field in ("touchscreen", "has_fingerprint", "has_backlit_keyboard"):
                    structured[sec][field] = cls.parse_bool(v_str)
                else:
                    structured[sec][field] = v_str

                # Section-specific auto-extractions
                if sec == "storage":
                    if structured[sec].get("capacity_gb") is None:
                        cap = cls.parse_capacity_gb(v_str, ignore_up_to=True)
                        if cap:
                            structured[sec]["capacity_gb"] = cap
                    m_max = re.search(r'\bup\s+to\s+(\d+)\s*(TB|GB)\b', v_str, re.IGNORECASE)
                    if m_max and structured[sec].get("max_supported_gb") is None:
                        sz = int(m_max.group(1))
                        structured[sec]["max_supported_gb"] = sz * 1024 if "T" in m_max.group(2).upper() else sz

                elif sec == "display":
                    if structured[sec].get("size_inches") is None:
                        inch = cls.parse_inches(v_str)
                        if inch:
                            structured[sec]["size_inches"] = inch
                    if structured[sec].get("resolution") is None and re.search(r'\d{3,4}\s*[xX*×]\s*\d{3,4}', v_str):
                        w, h = cls.parse_resolution(v_str)
                        if w and h:
                            structured[sec]["resolution"] = f"{w} x {h}"
                            structured[sec]["resolution_width"] = w
                            structured[sec]["resolution_height"] = h

                elif sec == "gpu":
                    m_gpu = re.search(
                        r'\b(GeForce\s+RTX\s+[0-9]{4}(?:\s*Ti|\s*Laptop\s+GPU)?|'
                        r'RTX\s+[0-9]{4}(?:\s*Ti|\s*Laptop\s+GPU)?|'
                        r'Radeon\s+(?:RX\s+)?[0-9A-Za-z]+|'
                        r'GeForce\s+MX[0-9]{3}|'
                        r'Intel\s+Arc\s+\w+)\b',
                        v_str,
                        re.IGNORECASE,
                    )
                    if m_gpu:
                        structured["gpu"]["model"] = m_gpu.group(1).strip()
                        up = m_gpu.group(1).upper()
                        if "RTX" in up or "GEFORCE" in up or "MX" in up:
                            structured["gpu"]["manufacturer"] = "NVIDIA"
                        elif "RADEON" in up:
                            structured["gpu"]["manufacturer"] = "AMD"
                        elif "ARC" in up or "INTEL" in up:
                            structured["gpu"]["manufacturer"] = "Intel"
                        structured["gpu"]["integrated"] = False
                    else:
                        v_clean_gpu = re.sub(r'[®™]', '', v_str).strip()
                        m_int = re.search(
                            r'\b(Adreno(?:\s+GPU)?|'
                            r'Radeon(?:\s+Graphics)?|'
                            r'Intel\s+(?:Iris\s+X[ee]|UHD|Graphics)|'
                            r'Iris\s+X[ee]|UHD\s+Graphics)\b',
                            v_clean_gpu,
                            re.IGNORECASE,
                        )
                        if m_int:
                            int_model = m_int.group(1).strip()
                            if int_model.lower() == "adreno":
                                int_model = "Adreno GPU"
                            elif int_model.lower() == "radeon":
                                int_model = "Radeon Graphics"
                            structured["gpu"]["model"] = int_model
                            up_int = v_clean_gpu.upper()
                            if "QUALCOMM" in up_int or "ADRENO" in up_int:
                                structured["gpu"]["manufacturer"] = "Qualcomm"
                            elif "AMD" in up_int or "RADEON" in up_int:
                                structured["gpu"]["manufacturer"] = "AMD"
                            elif "INTEL" in up_int:
                                structured["gpu"]["manufacturer"] = "Intel"
                            structured["gpu"]["integrated"] = True

                    if structured["gpu"].get("vram_gb") is None:
                        m_vram = re.search(r'\b([2468]|12|16|24)\s*GB\b', v_str, re.IGNORECASE)
                        if m_vram:
                            structured["gpu"]["vram_gb"] = int(m_vram.group(1))

                elif sec == "memory":
                    m_max_ram = re.search(r'\b(?:up\s+to|supports?\s+up\s+to)\s+(\d+)\s*(?:GB|G)\b', v_str, re.IGNORECASE)
                    if m_max_ram and structured["memory"].get("max_supported_gb") is None:
                        structured["memory"]["max_supported_gb"] = int(m_max_ram.group(1))
                    if structured["memory"].get("capacity_gb") is None:
                        ram_cap = cls.parse_capacity_gb(v_str, ignore_up_to=True)
                        if ram_cap:
                            structured["memory"]["capacity_gb"] = ram_cap
            else:
                # Key not directly mapped: send to compound/AI review
                compound_rows.append((raw_k, v_str))

        # Check integrated GPU status
        gpu_model = structured["gpu"].get("model") or ""
        accessibility = raw_specs.get("Graphics Memory Accessibility", "").lower()
        if "shared" in accessibility or any(k in gpu_model.lower() for k in ["intel", "radeon", "integrated", "iris"]):
            structured["gpu"]["integrated"] = True

        # Parse / Synthesize CPU full_name and subfields
        cpu_fn = structured["cpu"].get("full_name") or ""
        if cpu_fn:
            cpu_fn_clean = cpu_fn.replace('®', '').replace('™', '').strip()
            if not structured["cpu"].get("manufacturer"):
                if re.search(r'\bIntel\b', cpu_fn_clean, re.I):
                    structured["cpu"]["manufacturer"] = "Intel"
                elif re.search(r'\bAMD\b', cpu_fn_clean, re.I):
                    structured["cpu"]["manufacturer"] = "AMD"
                elif re.search(r'\b(?:Snapdragon|Qualcomm)\b', cpu_fn_clean, re.I):
                    structured["cpu"]["manufacturer"] = "Qualcomm"
            if not structured["cpu"].get("line"):
                m_line = re.search(r'\b(Core\s+Ultra\s+[3579]|Ultra\s+[3579]|Core\s+i[3579]|Core\s+[3579]|Ryzen\s+AI\s+(?:MAX\+?\s+)?[0-9]+|Ryzen\s+[3579]|Snapdragon\s+X(?:\s+Plus|\s+Elite)?)\b', cpu_fn_clean, re.I)
                if m_line:
                    line_val = m_line.group(1)
                    if line_val.lower().startswith("ultra"):
                        line_val = f"Core {line_val}"
                    structured["cpu"]["line"] = line_val
            if not structured["cpu"].get("model"):
                m_mod = re.search(r'\b([0-9]{3,5}[A-Z]{1,3}|[0-9]{3,4}|X1-[0-9]{2}-[0-9]{3}|[0-9]{4,5}[A-Z0-9]*)\b', cpu_fn_clean)
                if m_mod:
                    structured["cpu"]["model"] = m_mod.group(1)
        else:
            cpu_parts = [
                structured["cpu"].get("manufacturer"),
                structured["cpu"].get("line"),
                structured["cpu"].get("model"),
            ]
            valid_cpu = [p for p in cpu_parts if p and str(p).strip()]
            if valid_cpu:
                structured["cpu"]["full_name"] = " ".join(valid_cpu)

        if collected_ports:
            structured["connectivity"]["ports"] = collected_ports

        return structured, compound_rows
