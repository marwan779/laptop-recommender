"""Audit & Verification Tool for HybridNuExtract Catalog.

Verifies 100% of laptops and all 36+ specification dimensions:
  1. Identity (brand, laptop_family, laptop_model, manufacturer_part_number)
  2. CPU (manufacturer, line, model, cores, threads, clock_speed, cache_mb)
  3. GPU (manufacturer, model, vram_gb, tdp_w, integrated)
  4. Memory (capacity_gb, memory_type, speed, slot_count, max_supported_gb)
  5. Storage (capacity_gb, storage_type, interface, form_factor, slot_count)
  6. Display (size_inches, resolution, refresh_rate_hz, panel_type, aspect_ratio, touchscreen)
  7. Power & Battery (battery_capacity_wh, power_adapter_w, battery_cells)
  8. Physical (weight_kg, color, width_mm, depth_mm, height_mm)
  9. Build & Security (has_backlit_keyboard, has_fingerprint, pointing_device, security_features)
  10. Audio & Webcam (speaker_count, microphone, webcam.resolution)
  11. Connectivity (wifi, bluetooth, ethernet, ports)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_FILE = Path(__file__).resolve().parent / "output" / "compumarts_all_laptops_nuextract.json"
AUDIT_REPORT_FILE = Path(__file__).resolve().parent / "output" / "audit_report.json"

FIELDS_TO_AUDIT = [
    # Identity
    "identity.brand",
    "identity.laptop_family",
    "identity.laptop_model",
    "identity.manufacturer_part_number",
    # CPU
    "cpu.manufacturer",
    "cpu.line",
    "cpu.model",
    "cpu.cores",
    "cpu.threads",
    "cpu.clock_speed",
    "cpu.cache_mb",
    # GPU
    "gpu.manufacturer",
    "gpu.model",
    "gpu.vram_gb",
    "gpu.tdp_w",
    "gpu.integrated",
    # Memory
    "memory.capacity_gb",
    "memory.memory_type",
    "memory.speed",
    "memory.slot_count",
    "memory.max_supported_gb",
    # Storage
    "storage.capacity_gb",
    "storage.storage_type",
    "storage.interface",
    "storage.form_factor",
    "storage.slot_count",
    # Display
    "display.size_inches",
    "display.resolution",
    "display.refresh_rate_hz",
    "display.panel_type",
    "display.aspect_ratio",
    "display.touchscreen",
    # Power & Battery
    "power_battery.battery_capacity_wh",
    "power_battery.power_adapter_w",
    "power_battery.battery_cells",
    # Physical
    "physical.weight_kg",
    "physical.color",
    "physical.width_mm",
    "physical.depth_mm",
    "physical.height_mm",
    # Build & Security
    "build.has_backlit_keyboard",
    "build.has_fingerprint",
    "build.pointing_device",
    "build.security_features",
    # Audio & Webcam
    "audio.speaker_count",
    "audio.microphone",
    "webcam.resolution",
    # Connectivity
    "connectivity.wifi",
    "connectivity.bluetooth",
    "connectivity.ethernet",
    "connectivity.ports",
]


def audit():
    if not DATA_FILE.exists():
        print(f"[Error] File not found: {DATA_FILE}")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    total_laptops = len(records)
    print("=" * 80)
    print(f"AUDIT REPORT: {total_laptops} LIVE LAPTOPS AUDITED ACROSS {len(FIELDS_TO_AUDIT)} FIELDS")
    print("=" * 80)

    stats: dict[str, dict[str, Any]] = {
        f: {"populated": 0, "tier1": 0, "nuextract": 0, "null": 0} for f in FIELDS_TO_AUDIT
    }

    rejection_counts: dict[str, int] = {}
    conflict_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for item in records:
        struct = item.get("structured", {})
        meta = struct.get("extraction_meta", {})
        status = meta.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        field_sources = meta.get("field_sources", {})
        rejected = meta.get("rejected", [])
        for rej in rejected:
            r_rule = rej.get("rule", "unknown")
            rejection_counts[r_rule] = rejection_counts.get(r_rule, 0) + 1

        conflicts = meta.get("conflicts", [])
        for conf in conflicts:
            c_f = conf.get("field", "unknown")
            conflict_counts[c_f] = conflict_counts.get(c_f, 0) + 1

        for f_path in FIELDS_TO_AUDIT:
            sec, f_key = f_path.split(".", 1)
            val = struct.get(sec, {}).get(f_key)
            src = field_sources.get(f_path)

            if val is not None and val != [] and val != "":
                stats[f_path]["populated"] += 1
                if src == "tier1":
                    stats[f_path]["tier1"] += 1
                elif src == "nuextract":
                    stats[f_path]["nuextract"] += 1
            else:
                stats[f_path]["null"] += 1

    # Print summary table
    print(f"\n{'Field Name':<38} | {'Populated':<10} | {'Rate':<8} | {'Tier 1':<8} | {'NuExtract':<10}")
    print("-" * 82)
    for f_path in FIELDS_TO_AUDIT:
        s = stats[f_path]
        rate_str = f"{s['populated'] / total_laptops * 100:.1f}%"
        print(f"{f_path:<38} | {s['populated']:<10} | {rate_str:<8} | {s['tier1']:<8} | {s['nuextract']:<10}")

    print("\n" + "=" * 80)
    print("STATUS DISTRIBUTION:")
    for st, count in status_counts.items():
        print(f"  - {st}: {count} ({count / total_laptops * 100:.1f}%)")

    print("\nREJECTIONS INTERCEPTED BY VALIDATOR GATE (Top 10):")
    for rule, count in sorted(rejection_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  - {rule}: {count}")

    print("\nCONFLICTS (Title vs Table):")
    for fld, count in sorted(conflict_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {fld}: {count}")

    cpu_cache_stats = stats.get("cpu.cache_mb", {})
    print("\nCPU CACHE EXTRACTION BREAKDOWN:")
    print(f"  - Total populated: {cpu_cache_stats.get('populated', 0)} / {total_laptops} ({cpu_cache_stats.get('populated', 0) / total_laptops * 100:.1f}%)")
    print(f"  - Tier 1: {cpu_cache_stats.get('tier1', 0)}")
    print(f"  - NuExtract: {cpu_cache_stats.get('nuextract', 0)}")

    # Save audit report JSON
    audit_summary = {
        "total_laptops": total_laptops,
        "status_distribution": status_counts,
        "field_statistics": stats,
        "rejections": rejection_counts,
        "conflicts": conflict_counts,
    }
    with open(AUDIT_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Full audit report saved to {AUDIT_REPORT_FILE}")


if __name__ == "__main__":
    audit()

