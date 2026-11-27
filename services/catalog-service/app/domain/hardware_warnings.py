"""Pure domain rules for injecting hardware-level cons (legacy RAM / HDD storage)."""

from __future__ import annotations

import re

_LEGACY_DDR_RE = re.compile(r"\b(?:LP)?DDR([1-4])X?\b", re.IGNORECASE)


def inject_legacy_hardware_cons(
    cons_en: list[str] | None,
    cons_ar: list[str] | None,
    *,
    ram_type: str | None = None,
    storage_type: str | None = None,
) -> tuple[list[str], list[str]]:
    """Append bilingual cons when a laptop uses DDR4 (or older) RAM or HDD storage."""
    clean_en = list(cons_en or [])
    clean_ar = list(cons_ar or [])

    ram_norm = (ram_type or "").strip()
    if ram_norm and _LEGACY_DDR_RE.search(ram_norm):
        already_has_ram_con = any("ddr4" in c.lower() or "ddr3" in c.lower() or "ddr2" in c.lower() for c in clean_en)
        if not already_has_ram_con:
            label = ram_norm.upper()
            clean_en.append(f"Uses older {label} memory instead of DDR5, limiting memory bandwidth")
            clean_ar.append(f"يستخدم ذاكرة {label} الأقدم بدلاً من DDR5 مما يقلل من سرعة الذاكرة")

    storage_norm = (storage_type or "").strip().upper()
    if "HDD" in storage_norm:
        already_has_hdd_con = any("hdd" in c.lower() for c in clean_en)
        if not already_has_hdd_con:
            clean_en.append("Uses slower HDD storage instead of an NVMe SSD, affecting boot and load speeds")
            clean_ar.append("يعتمد على قرص تخزين HDD أبطأ بدلاً من SSD مما يؤثر على سرعة الإقلاع والتطبيقات")

    return clean_en, clean_ar
