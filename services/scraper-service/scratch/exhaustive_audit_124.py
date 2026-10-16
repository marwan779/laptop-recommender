import json
import re
import sys
from collections import defaultdict

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

print(f"Total catalog laptops: {len(catalog)}")

catalog_report = []

for idx, laptop in enumerate(catalog, start=1):
    title = laptop.get("title", "")
    url = laptop.get("url", "")
    st = laptop.get("source_table", {})
    specs = laptop.get("specs", {})
    
    # Raw text dump
    full_table_text = " | ".join(f"{k}: {v}" for k, v in st.items())
    full_context = f"{title} | {full_table_text}"

    contradictions = []

    # -------------------------------------------------------------
    # 1. IDENTITY
    # -------------------------------------------------------------
    ext_id = specs.get("identity", {})
    brand = ext_id.get("brand")
    family = ext_id.get("laptop_family")
    mpn = ext_id.get("manufacturer_part_number")

    # Brand check
    if brand:
        if brand.lower() not in full_context.lower():
            contradictions.append({
                "subsystem": "Identity",
                "field": "brand",
                "issue": "BRAND_NOT_FOUND_IN_RAW",
                "extracted": brand,
                "raw_evidence": f"Brand '{brand}' not found in title/table"
            })
    
    # MPN check
    for k, v in st.items():
        if k.lower() in ("model", "part number", "mpn"):
            val_clean = str(v).strip()
            if val_clean and len(val_clean) >= 5 and mpn:
                if val_clean.lower() != mpn.lower() and val_clean.lower() in title.lower():
                    # Likely mismatch if table Model is in title but mpn is different
                    pass

    # -------------------------------------------------------------
    # 2. CPU
    # -------------------------------------------------------------
    ext_cpu = specs.get("cpu", {})
    cpu_mfg = ext_cpu.get("manufacturer")
    cpu_model = ext_cpu.get("model")
    cpu_cores = ext_cpu.get("cores")

    # Manufacturer contradiction
    if "intel" in full_context.lower() and "amd" not in full_context.lower() and cpu_mfg == "AMD":
        contradictions.append({
            "subsystem": "CPU",
            "field": "manufacturer",
            "issue": "MANUFACTURER_MISMATCH",
            "extracted": cpu_mfg,
            "expected": "Intel",
            "raw_evidence": title
        })
    elif "amd" in full_context.lower() and "intel" not in full_context.lower() and cpu_mfg == "Intel":
        contradictions.append({
            "subsystem": "CPU",
            "field": "manufacturer",
            "issue": "MANUFACTURER_MISMATCH",
            "extracted": cpu_mfg,
            "expected": "AMD",
            "raw_evidence": title
        })

    # Model contradiction
    m_ryzen = re.search(r"Ryzen\s*(?:AI\s*)?(\d\s*[0-9A-Z]+)", full_context, re.I)
    if m_ryzen and cpu_mfg == "Intel":
        contradictions.append({
            "subsystem": "CPU",
            "field": "model",
            "issue": "CPU_FAMILY_CONTRADICTION",
            "extracted": f"{cpu_mfg} {cpu_model}",
            "expected": f"AMD {m_ryzen.group(0)}",
            "raw_evidence": f"Raw text states AMD Ryzen: {m_ryzen.group(0)}"
        })

    # -------------------------------------------------------------
    # 3. GPU
    # -------------------------------------------------------------
    ext_gpu = specs.get("gpu", {})
    gpu_model = ext_gpu.get("model")
    gpu_vram = ext_gpu.get("vram_gb")
    gpu_tdp = ext_gpu.get("tdp_w")
    gpu_integ = ext_gpu.get("integrated")

    # Contradictory GPU rows in retailer table
    rtx_matches = set(re.findall(r"RTX\s*(\d{4}(?:\s*Ti)?)", full_context, re.I))
    if len(rtx_matches) > 1:
        contradictions.append({
            "subsystem": "GPU",
            "field": "model",
            "issue": "RETAILER_INTERNAL_CONFLICT",
            "extracted": gpu_model,
            "expected": f"Conflict between RTX {list(rtx_matches)}",
            "raw_evidence": f"Raw table lists multiple conflicting RTX cards: {list(rtx_matches)}"
        })

    # TGP contradiction
    if gpu_tdp is not None:
        # Check if tdp matches raw W
        m_tgp = re.findall(r"(\d{2,3})\s*W", full_context, re.I)
        tgp_ints = [int(x) for x in m_tgp]
        if gpu_tdp not in tgp_ints:
            contradictions.append({
                "subsystem": "GPU",
                "field": "tdp_w",
                "issue": "TGP_VALUE_CONTRADICTION",
                "extracted": gpu_tdp,
                "expected": f"One of {tgp_ints}",
                "raw_evidence": f"Extracted TGP {gpu_tdp}W not found in raw W values: {tgp_ints}"
            })

    # -------------------------------------------------------------
    # 4. MEMORY
    # -------------------------------------------------------------
    ext_mem = specs.get("memory", {})
    mem_gb = ext_mem.get("capacity_gb")
    mem_speed = ext_mem.get("speed")
    mem_type = ext_mem.get("memory_type")

    # Capacity mismatch with title
    m_title_ram = re.search(r"\b(\d+)\s*(?:GB|G)\s*(?:RAM|DDR|Memory|LPDDR)\b", title, re.I)
    if m_title_ram and mem_gb is not None:
        t_ram = int(m_title_ram.group(1))
        if t_ram in (4, 8, 12, 16, 24, 32, 48, 64, 96, 128) and t_ram != mem_gb:
            contradictions.append({
                "subsystem": "Memory",
                "field": "capacity_gb",
                "issue": "CAPACITY_MISMATCH_WITH_TITLE",
                "extracted": mem_gb,
                "expected": t_ram,
                "raw_evidence": f"Title specifies {t_ram}GB: '{m_title_ram.group(0)}' vs Extracted {mem_gb}GB"
            })

    # Soldered + SODIMM hybrid dropped capacity
    m_hybrid = re.search(r"(\d+)\s*GB\s*Soldered[^\+]*\+\s*(\d+)\s*GB\s*SODIMM", full_table_text, re.I)
    if m_hybrid and mem_gb is not None:
        tot_hyb = int(m_hybrid.group(1)) + int(m_hybrid.group(2))
        if mem_gb == int(m_hybrid.group(1)) and mem_gb != tot_hyb:
            contradictions.append({
                "subsystem": "Memory",
                "field": "capacity_gb",
                "issue": "HYBRID_RAM_PARTIAL_EXTRACTION",
                "extracted": mem_gb,
                "expected": tot_hyb,
                "raw_evidence": f"Raw table states: '{m_hybrid.group(0)}' (Total: {tot_hyb}GB)"
            })

    # Memory speed unit defect (e.g. 2.93, 4.8, 5.6 GT/s)
    if mem_speed is not None:
        try:
            sp_val = float(str(mem_speed).split()[0])
            if sp_val < 1000:
                contradictions.append({
                    "subsystem": "Memory",
                    "field": "speed",
                    "issue": "SPEED_UNIT_CONVERSION_DEFECT",
                    "extracted": mem_speed,
                    "expected": f"{int(sp_val * 1000)} MHz",
                    "raw_evidence": f"Speed '{mem_speed}' appears to be unconverted GT/s"
                })
        except ValueError:
            pass

    # -------------------------------------------------------------
    # 5. STORAGE
    # -------------------------------------------------------------
    ext_stor = specs.get("storage", {})
    stor_gb = ext_stor.get("capacity_gb")

    m_title_ssd_tb = re.search(r"\b(\d+)\s*TB\s*(?:SSD|NVMe|Storage|PCIe)\b", title, re.I)
    m_title_ssd_gb = re.search(r"\b(\d+)\s*GB\s*(?:SSD|NVMe|Storage|PCIe)\b", title, re.I)
    exp_stor = None
    if m_title_ssd_tb:
        exp_stor = int(m_title_ssd_tb.group(1)) * 1024
    elif m_title_ssd_gb:
        exp_stor = int(m_title_ssd_gb.group(1))

    if exp_stor and stor_gb is not None and exp_stor != stor_gb:
        contradictions.append({
            "subsystem": "Storage",
            "field": "capacity_gb",
            "issue": "STORAGE_MAX_EXPANSION_COLLISION",
            "extracted": stor_gb,
            "expected": exp_stor,
            "raw_evidence": f"Title states {exp_stor}GB: '{m_title_ssd_tb.group(0) if m_title_ssd_tb else m_title_ssd_gb.group(0)}' vs Extracted {stor_gb}GB"
        })

    # -------------------------------------------------------------
    # 6. DISPLAY
    # -------------------------------------------------------------
    ext_disp = specs.get("display", {})
    disp_touch = ext_disp.get("touchscreen")
    disp_hz = ext_disp.get("refresh_rate_hz")
    disp_size = ext_disp.get("size_inches")

    # Touchscreen contradiction with explicit raw table row
    for k, v in st.items():
        if "touchscreen" in k.lower():
            v_clean = str(v).strip().lower()
            if v_clean in ("none", "no", "non-touch", "false") and disp_touch is True:
                contradictions.append({
                    "subsystem": "Display",
                    "field": "touchscreen",
                    "issue": "TOUCHSCREEN_CONTRADICTION",
                    "extracted": True,
                    "expected": False,
                    "raw_evidence": f"Store table specifies '{k}: {v}'"
                })
            elif v_clean in ("yes", "true", "supported") and disp_touch is False:
                contradictions.append({
                    "subsystem": "Display",
                    "field": "touchscreen",
                    "issue": "TOUCHSCREEN_CONTRADICTION",
                    "extracted": False,
                    "expected": True,
                    "raw_evidence": f"Store table specifies '{k}: {v}'"
                })

    # Display refresh rate mismatch with title
    m_title_hz = re.search(r"\b(\d{2,3})\s*Hz\b", title, re.I)
    if m_title_hz and disp_hz is not None:
        thz = int(m_title_hz.group(1))
        if thz in (60, 90, 120, 144, 165, 180, 240, 300, 360, 480) and thz != disp_hz:
            contradictions.append({
                "subsystem": "Display",
                "field": "refresh_rate_hz",
                "issue": "REFRESH_RATE_MISMATCH",
                "extracted": disp_hz,
                "expected": thz,
                "raw_evidence": f"Title states {thz}Hz: '{m_title_hz.group(0)}' vs Extracted {disp_hz}Hz"
            })

    # -------------------------------------------------------------
    # 7. POWER & BATTERY
    # -------------------------------------------------------------
    ext_bat = specs.get("power_battery", {})
    bat_wh = ext_bat.get("battery_capacity_wh")
    pwr_w = ext_bat.get("power_adapter_w")

    # Check CPU Turbo Power collision with Battery Wh
    m_turbo = re.search(r"Max Turbo Power:\s*(\d+)\s*W", full_table_text, re.I)
    if m_turbo and bat_wh is not None:
        if bat_wh == float(m_turbo.group(1)):
            contradictions.append({
                "subsystem": "Power & Battery",
                "field": "battery_capacity_wh",
                "issue": "CPU_TURBO_POWER_BATTERY_COLLISION",
                "extracted": bat_wh,
                "expected": "Actual Battery Wh",
                "raw_evidence": f"CPU Max Turbo Power ({m_turbo.group(0)}) extracted as battery capacity"
            })

    # -------------------------------------------------------------
    # 8. OPERATING SYSTEM
    # -------------------------------------------------------------
    ext_os = specs.get("operating_system", {})
    os_name = ext_os.get("name")
    if os_name:
        if "freedos" in title.lower() and "windows" in os_name.lower():
            contradictions.append({
                "subsystem": "Operating System",
                "field": "name",
                "issue": "OS_MISMATCH",
                "extracted": os_name,
                "expected": "FreeDOS",
                "raw_evidence": f"Title states FreeDOS: '{title}'"
            })
        elif "no os" in title.lower() and "windows" in os_name.lower():
            contradictions.append({
                "subsystem": "Operating System",
                "field": "name",
                "issue": "OS_MISMATCH",
                "extracted": os_name,
                "expected": "No OS",
                "raw_evidence": f"Title states No OS: '{title}'"
            })

    if contradictions:
        catalog_report.append({
            "laptop_index": idx,
            "title": title,
            "url": url,
            "contradiction_count": len(contradictions),
            "contradictions": contradictions
        })

print(f"Audit completed: {len(catalog_report)} laptops have contradictions ({len(catalog) - len(catalog_report)} are 100% clean).")

with open("scratch/exhaustive_audit_report.json", "w", encoding="utf-8") as f:
    json.dump({
        "total_catalog": len(catalog),
        "clean_laptops": len(catalog) - len(catalog_report),
        "contradiction_laptops": len(catalog_report),
        "details": catalog_report
    }, f, indent=2)

issue_counts = defaultdict(int)
for item in catalog_report:
    for c in item["contradictions"]:
        issue_counts[f"{c['subsystem']}.{c['field']}: {c['issue']}"] += 1

print("\n--- Summary of Issues Found ---")
for k, v in sorted(issue_counts.items(), key=lambda x: -x[1]):
    print(f"  {k:55}: {v}")

