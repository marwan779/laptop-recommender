import json
import re
from pathlib import Path
from collections import defaultdict

with open("pipeline_results_compumarts.json", encoding="utf-8") as f:
    catalog = json.load(f)

print(f"Running comprehensive contradiction audit across all {len(catalog)} laptops...")

audit_report = []

for idx, laptop in enumerate(catalog):
    url = laptop.get("url", "")
    title = laptop.get("title", "")
    source_table = laptop.get("source_table", {})
    specs = laptop.get("specs", {})
    cpu_key = laptop.get("cpu_key", "")
    
    # Raw text sources
    table_text = " | ".join(f"{k}: {v}" for k, v in source_table.items())
    full_raw = f"{title} | {table_text}"

    contradictions = []

    # -------------------------------------------------------------
    # 1. CPU CONTRADICTIONS
    # -------------------------------------------------------------
    ext_cpu = specs.get("cpu", {})
    ext_cpu_model = ext_cpu.get("model", "")
    ext_cpu_mfg = ext_cpu.get("manufacturer", "")
    ext_cpu_cores = ext_cpu.get("cores")

    # Check manufacturer mismatch
    if "intel" in full_raw.lower() and "amd" not in full_raw.lower() and ext_cpu_mfg.lower() == "amd":
        contradictions.append({
            "subsystem": "CPU",
            "field": "manufacturer",
            "type": "CONTRADICTION",
            "extracted": ext_cpu_mfg,
            "raw_expected": "Intel",
            "raw_evidence": title
        })
    elif "amd" in full_raw.lower() and "intel" not in full_raw.lower() and ext_cpu_mfg.lower() == "intel":
        contradictions.append({
            "subsystem": "CPU",
            "field": "manufacturer",
            "type": "CONTRADICTION",
            "extracted": ext_cpu_mfg,
            "raw_expected": "AMD",
            "raw_evidence": title
        })

    # Check specific CPU model mismatch (e.g. Ryzen 9 8940HX extracted as Core Ultra 9 275HX)
    m_ryzen = re.search(r"Ryzen\s*(?:AI\s*)?(\d\s*[0-9A-Z]+)", full_raw, re.I)
    m_intel = re.search(r"(?:Core\s*Ultra\s*[3579]\s*[0-9A-Z]+|Core\s*i[3579]-?\d{4,5}[A-Z]*|\b\d{4,5}[A-Z]+\b)", full_raw, re.I)
    
    if m_ryzen and "intel" in ext_cpu_mfg.lower():
        contradictions.append({
            "subsystem": "CPU",
            "field": "model",
            "type": "CRITICAL_CONTRADICTION",
            "extracted": f"{ext_cpu_mfg} {ext_cpu_model}",
            "raw_expected": f"AMD {m_ryzen.group(0)}",
            "raw_evidence": f"Title/Table specifies AMD Ryzen: {m_ryzen.group(0)}"
        })

    # -------------------------------------------------------------
    # 2. GPU CONTRADICTIONS
    # -------------------------------------------------------------
    ext_gpu = specs.get("gpu", {})
    ext_gpu_model = ext_gpu.get("model", "")
    ext_gpu_vram = ext_gpu.get("vram_gb")
    ext_gpu_tdp = ext_gpu.get("tdp_w")

    # Check conflicting GPU rows on page (e.g. MSI Cyborg listing both RTX 3050 and RTX 5070)
    rtx_tags = set(re.findall(r"RTX\s*(\d{4}(?:\s*Ti)?)", full_raw, re.I))
    if len(rtx_tags) > 1:
        contradictions.append({
            "subsystem": "GPU",
            "field": "model",
            "type": "STORE_INTERNAL_CONFLICT",
            "extracted": ext_gpu_model,
            "raw_expected": f"Conflict between {list(rtx_tags)}",
            "raw_evidence": f"Store table contains conflicting GPU rows: {list(rtx_tags)}"
        })

    # Check discrete GPU VRAM
    if "RTX 4050" in full_raw.upper() and ext_gpu_vram is not None and ext_gpu_vram != 6:
        contradictions.append({
            "subsystem": "GPU",
            "field": "vram_gb",
            "type": "CONTRADICTION",
            "extracted": ext_gpu_vram,
            "raw_expected": 6,
            "raw_evidence": "RTX 4050 Laptop standard is 6GB GDDR6"
        })
    elif "RTX 4060" in full_raw.upper() and ext_gpu_vram is not None and ext_gpu_vram != 8:
        contradictions.append({
            "subsystem": "GPU",
            "field": "vram_gb",
            "type": "CONTRADICTION",
            "extracted": ext_gpu_vram,
            "raw_expected": 8,
            "raw_evidence": "RTX 4060 Laptop standard is 8GB GDDR6"
        })

    # Check TGP mismatch / hallucination
    if ext_gpu_tdp is not None:
        if not re.search(r"\b" + str(ext_gpu_tdp) + r"\s*W\b", full_raw, re.I):
            contradictions.append({
                "subsystem": "GPU",
                "field": "tdp_w",
                "type": "HALLUCINATION",
                "extracted": ext_gpu_tdp,
                "raw_expected": None,
                "raw_evidence": f"{ext_gpu_tdp}W does not appear in raw text"
            })

    # -------------------------------------------------------------
    # 3. MEMORY CONTRADICTIONS
    # -------------------------------------------------------------
    ext_mem = specs.get("memory", {})
    ext_mem_gb = ext_mem.get("capacity_gb")
    ext_mem_speed = ext_mem.get("speed")

    # Check title vs extracted capacity
    m_title_ram = re.search(r"\b(\d+)\s*(?:GB|G)\s*(?:RAM|DDR|Memory|LPDDR)\b", title, re.I)
    if m_title_ram and ext_mem_gb is not None:
        title_ram_val = int(m_title_ram.group(1))
        if title_ram_val in (4, 8, 12, 16, 24, 32, 48, 64, 96, 128) and title_ram_val != ext_mem_gb:
            contradictions.append({
                "subsystem": "Memory",
                "field": "capacity_gb",
                "type": "CONTRADICTION",
                "extracted": ext_mem_gb,
                "raw_expected": title_ram_val,
                "raw_evidence": f"Title states {title_ram_val}GB RAM: '{m_title_ram.group(0)}'"
            })

    # Check hybrid RAM (e.g. 8GB Soldered + 8GB SODIMM)
    m_hybrid = re.search(r"(\d+)\s*GB\s*Soldered[^\+]*\+\s*(\d+)\s*GB\s*SODIMM", full_raw, re.I)
    if m_hybrid and ext_mem_gb is not None:
        soldered_val = int(m_hybrid.group(1))
        sodimm_val = int(m_hybrid.group(2))
        total_hybrid = soldered_val + sodimm_val
        if ext_mem_gb == soldered_val and ext_mem_gb != total_hybrid:
            contradictions.append({
                "subsystem": "Memory",
                "field": "capacity_gb",
                "type": "PARTIAL_EXTRACTION_CONTRADICTION",
                "extracted": ext_mem_gb,
                "raw_expected": total_hybrid,
                "raw_evidence": f"Raw table states: '{m_hybrid.group(0)}' (Total: {total_hybrid}GB)"
            })

    # Check RAM speed anomaly (e.g. 2.93 GT/s extracted as 2.93 MHz)
    if ext_mem_speed is not None and isinstance(ext_mem_speed, (int, float)) and ext_mem_speed < 1000:
        contradictions.append({
            "subsystem": "Memory",
            "field": "speed",
            "type": "MALFORMED_VALUE",
            "extracted": ext_mem_speed,
            "raw_expected": "e.g. 5600 MHz",
            "raw_evidence": f"RAM speed value '{ext_mem_speed}' appears to be GT/s transfer rate or invalid MHz"
        })

    # -------------------------------------------------------------
    # 4. STORAGE CONTRADICTIONS
    # -------------------------------------------------------------
    ext_storage = specs.get("storage", {})
    ext_storage_gb = ext_storage.get("capacity_gb")

    m_title_ssd_tb = re.search(r"\b(\d+)\s*TB\s*(?:SSD|NVMe|Storage|PCIe)\b", title, re.I)
    m_title_ssd_gb = re.search(r"\b(\d+)\s*GB\s*(?:SSD|NVMe|Storage|PCIe)\b", title, re.I)
    expected_title_ssd = None
    if m_title_ssd_tb:
        expected_title_ssd = int(m_title_ssd_tb.group(1)) * 1024
    elif m_title_ssd_gb:
        expected_title_ssd = int(m_title_ssd_gb.group(1))

    if expected_title_ssd and ext_storage_gb is not None and expected_title_ssd != ext_storage_gb:
        contradictions.append({
            "subsystem": "Storage",
            "field": "capacity_gb",
            "type": "CONTRADICTION",
            "extracted": ext_storage_gb,
            "raw_expected": expected_title_ssd,
            "raw_evidence": f"Title states storage: '{m_title_ssd_tb.group(0) if m_title_ssd_tb else m_title_ssd_gb.group(0)}'"
        })

    # -------------------------------------------------------------
    # 5. DISPLAY CONTRADICTIONS
    # -------------------------------------------------------------
    ext_disp = specs.get("display", {})
    ext_disp_size = ext_disp.get("size_inches")
    ext_disp_hz = ext_disp.get("refresh_rate_hz")
    ext_disp_touch = ext_disp.get("touchscreen")

    # Touchscreen contradiction check
    m_touch_yes = re.search(r"Touchscreen:\s*Yes\b", full_raw, re.I)
    m_touch_no = re.search(r"Touchscreen:\s*No\b", full_raw, re.I)
    if m_touch_yes and ext_disp_touch is False:
        contradictions.append({
            "subsystem": "Display",
            "field": "touchscreen",
            "type": "CONTRADICTION",
            "extracted": ext_disp_touch,
            "raw_expected": True,
            "raw_evidence": "Store table row: 'Touchscreen: Yes'"
        })
    elif m_touch_no and ext_disp_touch is True:
        contradictions.append({
            "subsystem": "Display",
            "field": "touchscreen",
            "type": "CONTRADICTION",
            "extracted": ext_disp_touch,
            "raw_expected": False,
            "raw_evidence": "Store table row: 'Touchscreen: No'"
        })

    # Refresh rate contradiction from title
    m_title_hz = re.search(r"\b(\d{2,3})\s*Hz\b", title, re.I)
    if m_title_hz and ext_disp_hz is not None:
        title_hz = int(m_title_hz.group(1))
        if title_hz in (60, 90, 120, 144, 165, 180, 240, 300, 360, 480) and title_hz != ext_disp_hz:
            contradictions.append({
                "subsystem": "Display",
                "field": "refresh_rate_hz",
                "type": "CONTRADICTION",
                "extracted": ext_disp_hz,
                "raw_expected": title_hz,
                "raw_evidence": f"Title states {title_hz}Hz: '{m_title_hz.group(0)}'"
            })

    # -------------------------------------------------------------
    # 6. POWER & BATTERY CONTRADICTIONS
    # -------------------------------------------------------------
    ext_bat = specs.get("power_battery", {})
    ext_bat_wh = ext_bat.get("battery_capacity_wh")
    
    # Check if CPU Turbo Power (e.g. 157W, 115W) was incorrectly extracted as Battery Wh
    m_turbo_pwr = re.search(r"Max Turbo Power:\s*(\d+)\s*W", full_raw, re.I)
    if m_turbo_pwr and ext_bat_wh is not None:
        turbo_val = float(m_turbo_pwr.group(1))
        if ext_bat_wh == turbo_val:
            contradictions.append({
                "subsystem": "Power & Battery",
                "field": "battery_capacity_wh",
                "type": "CONTRADICTION_ATTR_COLLISION",
                "extracted": ext_bat_wh,
                "raw_expected": "Battery Wh (not CPU Turbo Power)",
                "raw_evidence": f"Extracted CPU Max Turbo Power ({turbo_val}W) as Battery Capacity Wh"
            })

    # -------------------------------------------------------------
    # 7. OPERATING SYSTEM CONTRADICTIONS
    # -------------------------------------------------------------
    ext_os = specs.get("operating_system", {})
    ext_os_name = ext_os.get("name", "")
    
    if "freedos" in title.lower() and ext_os_name and "windows" in ext_os_name.lower():
        contradictions.append({
            "subsystem": "Operating System",
            "field": "name",
            "type": "CONTRADICTION",
            "extracted": ext_os_name,
            "raw_expected": "FreeDOS",
            "raw_evidence": f"Title states FreeDOS: '{title}'"
        })
    elif "no os" in title.lower() and ext_os_name and "windows" in ext_os_name.lower():
        contradictions.append({
            "subsystem": "Operating System",
            "field": "name",
            "type": "CONTRADICTION",
            "extracted": ext_os_name,
            "raw_expected": "No OS",
            "raw_evidence": f"Title states No OS: '{title}'"
        })

    if contradictions:
        audit_report.append({
            "laptop_index": idx + 1,
            "title": title,
            "url": url,
            "contradiction_count": len(contradictions),
            "contradictions": contradictions
        })

print(f"\nAUDIT FINISHED:")
print(f"Total Laptops Evaluated: {len(catalog)}")
print(f"Laptops with Contradictions: {len(audit_report)} ({(len(audit_report)/len(catalog))*100:.1f}%)")
print(f"Laptops 100% Contradiction-Free: {len(catalog) - len(audit_report)} ({((len(catalog) - len(audit_report))/len(catalog))*100:.1f}%)")

cat_summary = defaultdict(int)
for item in audit_report:
    for c in item["contradictions"]:
        cat_summary[f"{c['subsystem']}.{c['field']} ({c['type']})"] += 1

print("\n--- Contradictions Breakdown by Subsystem & Field ---")
for k, v in sorted(cat_summary.items(), key=lambda x: -x[1]):
    print(f"  {k:55}: {v}")

with open("scratch/audit_124_contradictions_report.json", "w", encoding="utf-8") as f:
    json.dump({
        "total_laptops": len(catalog),
        "contradiction_free_laptops": len(catalog) - len(audit_report),
        "laptops_with_contradictions": len(audit_report),
        "details": audit_report
    }, f, indent=2)

print("\nSaved full audit to scratch/audit_124_contradictions_report.json")

