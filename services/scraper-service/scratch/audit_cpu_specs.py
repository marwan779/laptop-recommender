import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import json
import cpu_specs

specs = cpu_specs.CPU_SPECS
print(f"Total CPUs being audited: {len(specs)}")

issues = []

for key, cpu in specs.items():
    mfg = cpu.get("manufacturer")
    model = cpu.get("model", "")
    family = cpu.get("family", "")
    codename = cpu.get("codename", "")
    
    total_cores = cpu.get("total_cores")
    p_cores = cpu.get("performance_cores")
    e_cores = cpu.get("efficient_cores")
    lp_e_cores = cpu.get("low_power_efficient_cores")
    threads = cpu.get("total_threads")
    
    base_mhz = cpu.get("base_clock_mhz") or cpu.get("p_core_base_mhz")
    turbo_mhz = cpu.get("max_turbo_frequency_mhz") or cpu.get("boost_clock_mhz")
    cache_mb = cpu.get("cache_mb") or cpu.get("total_cache_mb") or cpu.get("l3_cache_mb")
    
    base_w = cpu.get("base_power_w") or cpu.get("default_tdp_w")
    turbo_w = cpu.get("max_turbo_power_w")
    min_w = cpu.get("minimum_assured_power_w") or cpu.get("ctdp_down_w")
    
    source_url = str(cpu.get("source_url", ""))
    
    # Check 1: Key vs Model sanity
    norm_key = key.replace("_", "").lower()
    norm_model = re.sub(r'[^a-zA-Z0-9]', '', model).lower()
    # Check if key numbers match model numbers
    key_nums = set(re.findall(r'\d+', key))
    model_nums = set(re.findall(r'\d+', model))
    if key_nums != model_nums:
        # Check if difference is trivial (e.g. series 2)
        diff = key_nums.symmetric_difference(model_nums)
        if diff and not (mfg == "Apple" and not key_nums and not model_nums):
            issues.append({
                "key": key,
                "category": "KEY_MODEL_MISMATCH",
                "severity": "HIGH",
                "detail": f"Key '{key}' numbers {key_nums} != Model '{model}' numbers {model_nums}"
            })
            
    # Check 2: Core summation
    if p_cores is not None and e_cores is not None:
        expected_total = p_cores + e_cores + (lp_e_cores or 0)
        if total_cores != expected_total:
            issues.append({
                "key": key,
                "category": "CORE_SUM_MISMATCH",
                "severity": "CRITICAL",
                "detail": f"total_cores ({total_cores}) != p_cores ({p_cores}) + e_cores ({e_cores}) + lp_e ({lp_e_cores})"
            })

    # Check 3: Thread logic
    if mfg == "Apple" or mfg == "Qualcomm":
        if threads != total_cores:
            issues.append({
                "key": key,
                "category": "THREAD_LOGIC_ERROR",
                "severity": "CRITICAL",
                "detail": f"{mfg} CPU should have threads == cores. Got cores={total_cores}, threads={threads}"
            })
    elif mfg == "Intel":
        is_celeron = ("celeron" in key.lower() or "celeron" in model.lower()) and "pentium" not in key.lower()
        if is_celeron:
            # Celerons famously disable Hyper-Threading on P-cores
            expected_threads = (p_cores or 0) + (e_cores or 0)
            if threads != expected_threads and threads != total_cores:
                issues.append({
                    "key": key,
                    "category": "THREAD_LOGIC_ERROR",
                    "severity": "HIGH",
                    "detail": f"Celeron/Pentium expected threads={expected_threads}. Got threads={threads}"
                })
        elif "Lunar Lake" in codename or "Arrow Lake-H" in codename or "Arrow Lake-HX" in codename:
            # Pure Lion Cove / Skymont (no HT at all)
            if threads != total_cores:
                issues.append({
                    "key": key,
                    "category": "THREAD_LOGIC_ERROR",
                    "severity": "CRITICAL",
                    "detail": f"Lion Cove/Skymont (no SMT) should have threads == cores ({total_cores}). Got threads={threads}"
                })
        elif "Arrow Lake-U" in codename or "Meteor Lake" in codename or "Series 1" in family:
            # Redwood Cove + Crestmont: P-cores have HT (2x), E & LP-E have 1x
            expected_threads = (p_cores * 2) + e_cores + (lp_e_cores or 0)
            if threads != expected_threads:
                issues.append({
                    "key": key,
                    "category": "THREAD_LOGIC_ERROR",
                    "severity": "CRITICAL",
                    "detail": f"Meteor Lake / Arrow Lake-U expected threads={expected_threads}. Got threads={threads}"
                })
        elif p_cores is not None and e_cores is not None:
            # Raptor Lake-H Refresh / 12th / 13th / 14th Gen Intel Hybrid: P-cores 2x, E-cores 1x
            expected_threads = (p_cores * 2) + e_cores
            if threads != expected_threads:
                issues.append({
                    "key": key,
                    "category": "THREAD_LOGIC_ERROR",
                    "severity": "HIGH",
                    "detail": f"Intel hybrid expected threads={expected_threads} (2*{p_cores} + {e_cores}). Got threads={threads}"
                })
    elif mfg == "AMD":
        # AMD mobile Zen 2, 3, 4, 5 typically have SMT (threads = 2 * cores) except a few Mendocino or Athlon
        if threads is not None and total_cores is not None:
            if threads != total_cores * 2 and threads != total_cores:
                issues.append({
                    "key": key,
                    "category": "THREAD_LOGIC_ERROR",
                    "severity": "HIGH",
                    "detail": f"AMD unexpected thread ratio: cores={total_cores}, threads={threads}"
                })

    # Check 4: Clock frequencies
    if base_mhz and turbo_mhz:
        if base_mhz > turbo_mhz:
            issues.append({
                "key": key,
                "category": "FREQUENCY_ERROR",
                "severity": "CRITICAL",
                "detail": f"Base clock ({base_mhz} MHz) > Turbo clock ({turbo_mhz} MHz)"
            })
        if turbo_mhz > 6200:
            issues.append({
                "key": key,
                "category": "FREQUENCY_ANOMALY",
                "severity": "MEDIUM",
                "detail": f"Unusually high laptop turbo clock: {turbo_mhz} MHz"
            })
            
    # Check 5: Power limits
    if base_w and turbo_w:
        if base_w > turbo_w:
            issues.append({
                "key": key,
                "category": "POWER_ERROR",
                "severity": "CRITICAL",
                "detail": f"Base power ({base_w}W) > Turbo power ({turbo_w}W)"
            })
    if min_w and base_w:
        if min_w > base_w:
            issues.append({
                "key": key,
                "category": "POWER_ERROR",
                "severity": "HIGH",
                "detail": f"Minimum assured power ({min_w}W) > Base power ({base_w}W)"
            })
            
    # Check 6: Memory compatibility
    mem_types = str(cpu.get("supported_memory_types", ""))
    ddr5_speed = cpu.get("max_ddr5_speed_mts")
    lpddr5x_speed = cpu.get("max_lpddr5x_speed_mts")
    if "DDR4" in mem_types and "DDR5" not in mem_types and (ddr5_speed or lpddr5x_speed):
        issues.append({
            "key": key,
            "category": "MEMORY_SPEC_CONTRADICTION",
            "severity": "HIGH",
            "detail": f"Memory types says DDR4 only, but DDR5/LPDDR5 speed is specified: {ddr5_speed or lpddr5x_speed}"
        })
    if "DDR5" in mem_types and not ddr5_speed and not lpddr5x_speed and mfg != "Apple":
        issues.append({
            "key": key,
            "category": "MEMORY_SPEC_INCOMPLETE",
            "severity": "LOW",
            "detail": f"Memory types includes DDR5, but max DDR5/LPDDR5 speed is missing"
        })

    # Check 7: Source URL copy-paste trace
    if source_url:
        # Extract potential SKU identifier from key
        # e.g., '13700h', '7840hs', '155h', 'm3_pro'
        key_parts = key.split('_')
        last_part = key_parts[-1]
        second_last = key_parts[-2] if len(key_parts) > 1 else ""
        
        # Check nanoreview / notebookcheck / cpu-world / techpowerup URLs
        if any(domain in source_url for domain in ["nanoreview.net", "notebookcheck.net", "techpowerup.com", "cpu-world.com"]):
            # Check if url contains a completely different SKU
            # Check if last_part or second_last appears in URL
            if len(last_part) >= 3 and last_part not in source_url.lower() and second_last not in source_url.lower():
                issues.append({
                    "key": key,
                    "category": "SUSPICIOUS_SOURCE_URL",
                    "severity": "HIGH",
                    "detail": f"Source URL '{source_url}' does not contain expected SKU '{last_part}'"
                })

print(f"\nAudit complete! Found {len(issues)} issues across {len(specs)} SKUs.")

# Group by category
by_cat = {}
for i in issues:
    by_cat.setdefault(i["category"], []).append(i)

for cat, lst in by_cat.items():
    print(f"\n--- {cat} ({len(lst)} issues) ---")
    for item in lst[:10]:
        print(f"  [{item['severity']}] {item['key']}: {item['detail']}")
    if len(lst) > 10:
        print(f"  ... and {len(lst) - 10} more")

with open("scratch/cpu_audit_results.json", "w", encoding="utf-8") as f:
    json.dump(issues, f, indent=2)
