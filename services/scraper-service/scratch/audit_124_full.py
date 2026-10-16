import json
import re
from pathlib import Path
from collections import defaultdict

with open("pipeline_results_compumarts.json", encoding="utf-8") as f:
    catalog = json.load(f)

print(f"Loaded {len(catalog)} laptops for audit.")

audit_results = []
summary_counts = defaultdict(int)

for idx, laptop in enumerate(catalog):
    title = laptop.get("title", "")
    url = laptop.get("url", "")
    source_table = laptop.get("source_table", {})
    specs = laptop.get("specs", {})
    rejections = laptop.get("rejections_count", 0)

    # Flatten raw table and title into search strings
    raw_text = " | ".join(f"{k}: {v}" for k, v in source_table.items()) + f" | Title: {title}"

    laptop_issues = []

    # -------------------------------------------------------------
    # 1. IDENTITY AUDIT
    # -------------------------------------------------------------
    raw_brand = source_table.get("Brand") or source_table.get("brand")
    ext_brand = specs.get("identity", {}).get("brand")
    if raw_brand and ext_brand and raw_brand.strip().lower() != ext_brand.strip().lower():
        laptop_issues.append({
            "subsystem": "identity",
            "field": "brand",
            "type": "CONTRADICTION",
            "extracted": ext_brand,
            "raw": raw_brand,
            "evidence": f"Brand row: {raw_brand}"
        })
        summary_counts["brand_contradiction"] += 1

    # MPN / SKU check
    raw_pn = source_table.get("Part Number") or source_table.get("Manufacturer Part Number") or source_table.get("MPN")
    ext_mpn = specs.get("identity", {}).get("manufacturer_part_number")
    if raw_pn and ext_mpn and raw_pn.strip() != ext_mpn.strip():
        # Check if one is substring of other (e.g. without suffix)
        if raw_pn.strip() not in ext_mpn.strip() and ext_mpn.strip() not in raw_pn.strip():
            laptop_issues.append({
                "subsystem": "identity",
                "field": "manufacturer_part_number",
                "type": "CONTRADICTION",
                "extracted": ext_mpn,
                "raw": raw_pn,
                "evidence": f"Part Number row: {raw_pn}"
            })
            summary_counts["mpn_contradiction"] += 1

    # -------------------------------------------------------------
    # 2. CPU AUDIT
    # -------------------------------------------------------------
    ext_cpu_model = specs.get("cpu", {}).get("model")
    ext_cpu_line = specs.get("cpu", {}).get("line")
    ext_cpu_cores = specs.get("cpu", {}).get("cores")
    raw_cpu_text = specs.get("cpu", {}).get("raw_spec", "")

    # Cores check: compare raw cores against extracted
    raw_cores_match = re.search(r"(\d+)\s*(?:Cores?|C)\b", raw_cpu_text + " " + raw_text, re.I)
    if raw_cores_match and ext_cpu_cores is not None:
        c_val = int(raw_cores_match.group(1))
        # Ignore small numbers that could be cache or gen (e.g. 14th gen, 4.5GHz)
        if 2 <= c_val <= 32:
            # Check if this was indeed cores
            if re.search(r"\b" + str(c_val) + r"\s*Cores?\b", raw_cpu_text, re.I) and c_val != ext_cpu_cores:
                laptop_issues.append({
                    "subsystem": "cpu",
                    "field": "cores",
                    "type": "CONTRADICTION",
                    "extracted": ext_cpu_cores,
                    "raw": c_val,
                    "evidence": raw_cores_match.group(0)
                })
                summary_counts["cpu_cores_contradiction"] += 1

    # -------------------------------------------------------------
    # 3. GPU AUDIT
    # -------------------------------------------------------------
    ext_gpu_model = specs.get("gpu", {}).get("model")
    ext_gpu_vram = specs.get("gpu", {}).get("vram_gb")
    raw_gpu_text = specs.get("gpu", {}).get("raw_spec", "")
    
    # Check RTX series mismatch (e.g. RTX 4060 vs RTX 4050)
    rtx_raw = re.findall(r"RTX\s*(\d{4}(?:\s*Ti)?)", raw_text, re.I)
    if rtx_raw and ext_gpu_model:
        # take the most common RTX tag
        canonical_rtx = rtx_raw[0].upper().replace(" ", "")
        if "RTX" in ext_gpu_model.upper():
            ext_rtx = re.search(r"(\d{4}(?:\s*Ti)?)", ext_gpu_model, re.I)
            if ext_rtx and ext_rtx.group(1).upper().replace(" ", "") != canonical_rtx:
                laptop_issues.append({
                    "subsystem": "gpu",
                    "field": "model",
                    "type": "CONTRADICTION",
                    "extracted": ext_gpu_model,
                    "raw": f"RTX {canonical_rtx}",
                    "evidence": f"Found RTX {canonical_rtx} in raw text"
                })
                summary_counts["gpu_model_contradiction"] += 1

    # Check VRAM GB mismatch
    raw_vram_match = re.search(r"(?:RTX\s*\d{4}[^\d]+|Video RAM:\s*|Graphics:\s*[^\d]+)(\d+)\s*GB", raw_text, re.I)
    if raw_vram_match and ext_gpu_vram is not None:
        v_val = int(raw_vram_match.group(1))
        if v_val in (4, 6, 8, 12, 16, 24) and v_val != ext_gpu_vram:
            laptop_issues.append({
                "subsystem": "gpu",
                "field": "vram_gb",
                "type": "CONTRADICTION",
                "extracted": ext_gpu_vram,
                "raw": v_val,
                "evidence": raw_vram_match.group(0)
            })
            summary_counts["gpu_vram_contradiction"] += 1

    # Check TDP / TGP: did it hallucinate a TGP?
    ext_tdp = specs.get("gpu", {}).get("tdp_w")
    if ext_tdp is not None:
        # verify if TGP appears anywhere in raw_text
        if not re.search(r"\b" + str(ext_tdp) + r"\s*W\b", raw_text, re.I):
            laptop_issues.append({
                "subsystem": "gpu",
                "field": "tdp_w",
                "type": "HALLUCINATION",
                "extracted": ext_tdp,
                "raw": None,
                "evidence": f"TGP {ext_tdp}W does not appear in store raw specs"
            })
            summary_counts["gpu_tdp_hallucination"] += 1

    # -------------------------------------------------------------
    # 4. MEMORY AUDIT
    # -------------------------------------------------------------
    ext_ram_gb = specs.get("memory", {}).get("capacity_gb")
    ext_ram_type = specs.get("memory", {}).get("memory_type")
    ext_ram_speed = specs.get("memory", {}).get("speed")

    # Search RAM capacity
    ram_raw_matches = re.findall(r"(\d+)\s*(?:GB|G)\s*(?:DDR|LPDDR|RAM|Memory|Installed|System Memory)", raw_text, re.I)
    if ram_raw_matches and ext_ram_gb is not None:
        raw_caps = [int(m) for m in ram_raw_matches if int(m) in (4, 8, 12, 16, 24, 32, 48, 64, 96, 128)]
        if raw_caps and ext_ram_gb not in raw_caps:
            # Pick first valid
            laptop_issues.append({
                "subsystem": "memory",
                "field": "capacity_gb",
                "type": "CONTRADICTION",
                "extracted": ext_ram_gb,
                "raw": raw_caps[0],
                "evidence": f"Found {raw_caps[0]}GB in raw RAM description"
            })
            summary_counts["ram_capacity_contradiction"] += 1

    # -------------------------------------------------------------
    # 5. STORAGE AUDIT
    # -------------------------------------------------------------
    ext_storage_gb = specs.get("storage", {}).get("capacity_gb")
    storage_tb_matches = re.findall(r"(\d+)\s*TB\s*(?:SSD|PCIe|NVMe|Storage|M\.2)", raw_text, re.I)
    storage_gb_matches = re.findall(r"(\d+)\s*GB\s*(?:SSD|PCIe|NVMe|Storage|M\.2)", raw_text, re.I)
    
    expected_storage = None
    if storage_tb_matches:
        expected_storage = int(storage_tb_matches[0]) * 1024
    elif storage_gb_matches:
        cand = [int(m) for m in storage_gb_matches if int(m) in (128, 256, 512, 1024, 2048, 4096)]
        if cand:
            expected_storage = cand[0]

    if expected_storage and ext_storage_gb is not None and expected_storage != ext_storage_gb:
        laptop_issues.append({
            "subsystem": "storage",
            "field": "capacity_gb",
            "type": "CONTRADICTION",
            "extracted": ext_storage_gb,
            "raw": expected_storage,
            "evidence": f"Expected {expected_storage}GB from raw storage tag"
        })
        summary_counts["storage_capacity_contradiction"] += 1

    # -------------------------------------------------------------
    # 6. DISPLAY AUDIT
    # -------------------------------------------------------------
    ext_size = specs.get("display", {}).get("size_inches")
    ext_res = specs.get("display", {}).get("resolution")
    ext_hz = specs.get("display", {}).get("refresh_rate_hz")
    ext_touch = specs.get("display", {}).get("touchscreen")

    # Refresh rate check
    hz_matches = re.findall(r"(\d{2,3})\s*Hz\b", raw_text, re.I)
    valid_hz = [int(h) for h in hz_matches if int(h) in (60, 90, 120, 144, 165, 180, 240, 300, 360, 480)]
    if valid_hz and ext_hz is not None and ext_hz not in valid_hz:
        laptop_issues.append({
            "subsystem": "display",
            "field": "refresh_rate_hz",
            "type": "CONTRADICTION",
            "extracted": ext_hz,
            "raw": valid_hz[0],
            "evidence": f"Found {valid_hz[0]}Hz in display specs"
        })
        summary_counts["display_hz_contradiction"] += 1

    # Touchscreen check: if raw says touchscreen / touch display
    is_touch_in_raw = bool(re.search(r"\b(touchscreen|touch\s*display|touch\s*screen|oled\s*touch)\b", raw_text, re.I))
    is_non_touch = bool(re.search(r"\b(non-touch|no\s*touch)\b", raw_text, re.I))
    if is_touch_in_raw and not is_non_touch and ext_touch is False:
        laptop_issues.append({
            "subsystem": "display",
            "field": "touchscreen",
            "type": "MISSED_EXTRACTION",
            "extracted": ext_touch,
            "raw": True,
            "evidence": "Touchscreen explicitly stated in title/specs"
        })
        summary_counts["display_touch_missed"] += 1

    # -------------------------------------------------------------
    # 7. CONNECTIVITY AUDIT
    # -------------------------------------------------------------
    ext_wifi = specs.get("connectivity", {}).get("wifi")
    ext_bt = specs.get("connectivity", {}).get("bluetooth")
    ext_ethernet = specs.get("connectivity", {}).get("ethernet")
    ext_card = specs.get("connectivity", {}).get("has_card_reader")
    ext_ports = specs.get("connectivity", {}).get("ports") or []

    # Bluetooth check
    bt_match = re.search(r"Bluetooth\s*([0-9\.]+)", raw_text, re.I)
    if bt_match:
        expected_bt = f"Bluetooth {bt_match.group(1)}"
        if not ext_bt:
            laptop_issues.append({
                "subsystem": "connectivity",
                "field": "bluetooth",
                "type": "MISSED_EXTRACTION",
                "extracted": None,
                "raw": expected_bt,
                "evidence": bt_match.group(0)
            })
            summary_counts["bluetooth_missed"] += 1
        elif ext_bt.lower().replace(" ", "") != expected_bt.lower().replace(" ", ""):
            # Check if version difference
            laptop_issues.append({
                "subsystem": "connectivity",
                "field": "bluetooth",
                "type": "CONTRADICTION",
                "extracted": ext_bt,
                "raw": expected_bt,
                "evidence": bt_match.group(0)
            })
            summary_counts["bluetooth_contradiction"] += 1

    # Wi-Fi check
    wifi_match = re.search(r"Wi-Fi\s*([4567][eE]?)", raw_text, re.I)
    if wifi_match:
        expected_wifi = f"Wi-Fi {wifi_match.group(1).upper()}"
        if not ext_wifi:
            laptop_issues.append({
                "subsystem": "connectivity",
                "field": "wifi",
                "type": "MISSED_EXTRACTION",
                "extracted": None,
                "raw": expected_wifi,
                "evidence": wifi_match.group(0)
            })
            summary_counts["wifi_missed"] += 1

    # Card Reader check
    card_match = re.search(r"\b(card\s*reader|micro\s*sd|sd\s*card\s*slot|sd\s*express)\b", raw_text, re.I)
    if card_match and ext_card is False:
        # Check if it was "No card reader"
        if not re.search(r"\b(?:no|without)\s*card\s*reader\b", raw_text, re.I):
            laptop_issues.append({
                "subsystem": "connectivity",
                "field": "has_card_reader",
                "type": "MISSED_EXTRACTION",
                "extracted": ext_card,
                "raw": True,
                "evidence": card_match.group(0)
            })
            summary_counts["card_reader_missed"] += 1

    # -------------------------------------------------------------
    # 8. OPERATING SYSTEM AUDIT
    # -------------------------------------------------------------
    ext_os = specs.get("operating_system", {}).get("name")
    raw_os_row = source_table.get("Operating System") or source_table.get("OS")
    if raw_os_row and ext_os:
        if "freedos" in raw_os_row.lower() and "windows" in ext_os.lower():
            laptop_issues.append({
                "subsystem": "operating_system",
                "field": "name",
                "type": "CONTRADICTION",
                "extracted": ext_os,
                "raw": raw_os_row,
                "evidence": f"OS row states: {raw_os_row}"
            })
            summary_counts["os_contradiction"] += 1

    if laptop_issues:
        audit_results.append({
            "idx": idx + 1,
            "title": title,
            "url": url,
            "issue_count": len(laptop_issues),
            "issues": laptop_issues,
        })

print(f"\nAUDIT COMPLETE: Found issues in {len(audit_results)} of {len(catalog)} laptops.")
print(f"Total issue instances: {sum(len(r['issues']) for r in audit_results)}")
print("\n--- Summary of Issue Types ---")
for k, v in sorted(summary_counts.items(), key=lambda x: -x[1]):
    print(f"  {k:35}: {v}")

# Save detailed JSON report
with open("scratch/audit_124_detailed_report.json", "w", encoding="utf-8") as f:
    json.dump({"total_laptops": len(catalog), "laptops_with_issues": len(audit_results), "results": audit_results}, f, indent=2)

print("\nSaved detailed JSON to scratch/audit_124_detailed_report.json")

