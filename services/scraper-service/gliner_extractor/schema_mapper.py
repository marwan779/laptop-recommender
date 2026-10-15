"""Schema Mapper for GLiNER Entities.

Maps extracted GLiNER entity spans and table metadata into
the catalog-service database schema models.
"""

from __future__ import annotations

import re
from typing import Any

# High-precision target entity labels for GLiNER
DEFAULT_LABELS: list[str] = [
    # Identity
    "brand",
    "laptop family",
    "laptop model",
    "part number",
    # Processor (CPU)
    "processor manufacturer",
    "processor line",
    "processor model",
    "cpu core count",
    "cpu thread count",
    "cpu clock speed",
    # Graphics (GPU)
    "graphics manufacturer",
    "graphics model",
    "graphics vram",
    "graphics power wattage",
    # Memory (RAM)
    "ram capacity",
    "ram type",
    "ram speed",
    "max ram capacity",
    # Storage
    "storage capacity",
    "storage type",
    "storage interface",
    "storage form factor",
    # Display
    "screen size",
    "screen resolution",
    "display panel type",
    "display refresh rate",
    "touchscreen",
    # Power & Battery
    "battery capacity",
    "battery cells",
    "power adapter wattage",
    # Connectivity & Ports
    "wifi standard",
    "bluetooth version",
    "port",
    # OS & Physical
    "operating system",
    "color",
    "weight",
]


class LaptopSchemaMapper:
    """Converts raw GLiNER entity spans into structured catalog-service data."""

    @staticmethod
    def map_entities(
        entities: list[dict[str, Any]],
        title: str = "",
        raw_specs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Aggregate spans and organize into catalog-service schema.

        Args:
            entities: List of GLiNER span dictionaries (text, label, score).
            title: Product title (for fallback/context).
            raw_specs: Optional dictionary of raw scraped specs.

        Returns:
            Dictionary structured into catalog-service database components.
        """
        # Bucket spans by label with their highest score
        label_spans: dict[str, list[dict[str, Any]]] = {}
        for ent in entities:
            label = ent.get("label", "")
            label_spans.setdefault(label, []).append(ent)

        # Helper to get the highest confidence span for a label
        def get_best(lbl: str) -> str | None:
            spans = label_spans.get(lbl, [])
            if not spans:
                return None
            best = max(spans, key=lambda x: x.get("score", 0.0))
            return best.get("text", "").strip() or None

        # Helper to get all unique spans for multi-value entities (like ports)
        def get_all(lbl: str) -> list[str]:
            spans = label_spans.get(lbl, [])
            seen: set[str] = set()
            res: list[str] = []
            for s in spans:
                t = s.get("text", "").strip()
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    res.append(t)
            return res

        # Numeric Parsers
        def parse_num(val: str | None) -> float | None:
            if not val:
                return None
            m = re.search(r"(\d+(?:\.\d+)?)", val)
            return float(m.group(1)) if m else None

        def parse_int(val: str | None) -> int | None:
            if not val:
                return None
            m = re.search(r"(\d+)", val)
            return int(m.group(1)) if m else None

        def parse_storage_gb(val: str | None) -> int | None:
            if not val:
                return None
            m = re.search(r"(\d+)\s*(TB|GB|T|G)", val, re.IGNORECASE)
            if m:
                num = int(m.group(1))
                unit = m.group(2).upper()
                return num * 1024 if "T" in unit else num
            return parse_int(val)

        # Resolution Parser
        res_str = get_best("screen resolution")
        res_w, res_h = None, None
        if res_str:
            res_m = re.search(r"(\d{3,4})\s*[xX*×]\s*(\d{3,4})", res_str)
            if res_m:
                res_w = int(res_m.group(1))
                res_h = int(res_m.group(2))

        # Build Structured Output
        cpu_mfg = get_best("processor manufacturer")
        cpu_line = get_best("processor line")
        cpu_model = get_best("processor model")
        cpu_full_name = " ".join(p for p in [cpu_mfg, cpu_line, cpu_model] if p) or None

        gpu_mfg = get_best("graphics manufacturer")
        gpu_model = get_best("graphics model")
        gpu_full_name = " ".join(p for p in [gpu_mfg, gpu_model] if p and p not in (gpu_model or "")) or gpu_model

        is_integrated = False
        if gpu_full_name:
            integrated_keywords = ["intel graphics", "intel iris", "intel uhd", "radeon graphics", "shared"]
            is_integrated = any(k in gpu_full_name.lower() for k in integrated_keywords)

        structured: dict[str, Any] = {
            "identity": {
                "brand": get_best("brand"),
                "laptop_family": get_best("laptop family"),
                "laptop_model": get_best("laptop model"),
                "manufacturer_part_number": get_best("part number"),
            },
            "cpu": {
                "manufacturer": cpu_mfg,
                "line": cpu_line,
                "model": cpu_model,
                "full_name": cpu_full_name,
                "cores": parse_int(get_best("cpu core count")),
                "threads": parse_int(get_best("cpu thread count")),
                "clock_speed": get_best("cpu clock speed"),
            },
            "gpu": {
                "manufacturer": gpu_mfg,
                "model": gpu_model,
                "full_name": gpu_full_name,
                "vram_gb": parse_int(get_best("graphics vram")),
                "tdp_w": parse_int(get_best("graphics power wattage")),
                "integrated": is_integrated,
            },
            "memory": {
                "capacity_gb": parse_int(get_best("ram capacity")),
                "memory_type": get_best("ram type"),
                "speed": get_best("ram speed"),
                "max_supported_gb": parse_int(get_best("max ram capacity")),
            },
            "storage": {
                "capacity_gb": parse_storage_gb(get_best("storage capacity")),
                "storage_type": get_best("storage type"),
                "interface": get_best("storage interface"),
                "form_factor": get_best("storage form factor"),
            },
            "display": {
                "size_inches": parse_num(get_best("screen size")),
                "resolution": res_str,
                "resolution_width": res_w,
                "resolution_height": res_h,
                "panel_type": get_best("display panel type"),
                "refresh_rate_hz": parse_int(get_best("display refresh rate")),
                "touchscreen": (
                    True
                    if get_best("touchscreen") and "touch" in get_best("touchscreen").lower() and "non" not in get_best("touchscreen").lower()
                    else False
                ),
            },
            "power_battery": {
                "battery_capacity_wh": parse_num(get_best("battery capacity")),
                "battery_cells": parse_int(get_best("battery cells")),
                "power_adapter_w": parse_num(get_best("power adapter wattage")),
            },
            "connectivity": {
                "wifi": get_best("wifi standard"),
                "bluetooth": get_best("bluetooth version"),
                "ports": get_all("port"),
            },
            "operating_system": {
                "name": get_best("operating system"),
            },
            "physical": {
                "color": get_best("color"),
                "weight": get_best("weight"),
            },
            "raw_entity_count": len(entities),
            "raw_entities": entities,
        }

        return structured

