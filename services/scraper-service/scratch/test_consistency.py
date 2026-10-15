import json
import math
import re
from pathlib import Path

# Load databases
DATA_DIR = Path('gliner_extractor/data')
with open(DATA_DIR / 'cpu_specs.json', 'r', encoding='utf-8') as f:
    CPU_SPECS = json.load(f)
with open(DATA_DIR / 'gpu_specs.json', 'r', encoding='utf-8') as f:
    GPU_SPECS = json.load(f)

with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    fixtures = json.load(f)

def _get_gpu_spec(model_name: str):
    if not model_name:
        return None
    m = model_name.strip()
    if m in GPU_SPECS:
        return GPU_SPECS[m]
    # Try with GeForce
    if not m.lower().startswith('geforce') and f"GeForce {m}" in GPU_SPECS:
        return GPU_SPECS[f"GeForce {m}"]
    # Try without Laptop GPU
    clean = re.sub(r'\s+Laptop\s+GPU\b', '', m, flags=re.I).strip()
    if clean in GPU_SPECS:
        return GPU_SPECS[clean]
    if not clean.lower().startswith('geforce') and f"GeForce {clean}" in GPU_SPECS:
        return GPU_SPECS[f"GeForce {clean}"]
    return None

def validate_consistency(structured: dict, raw_specs: dict | None = None) -> list[dict]:
    rejections = []
    
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
            
    # 8. Same cpu.model must give authoritative cores/threads from DB
    model = cpu.get("model")
    if model:
        m_str = str(model).strip()
        spec = CPU_SPECS.get(m_str)
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
                
    # 3. aspect_ratio == reduced(width, height)
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

    # 4. Storage form_factor 2.5 incompatible with NVMe/M.2
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

    # 5. iGPU => vram_gb is null; dGPU vram in table
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
        spec = _get_gpu_spec(model_name)
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

    # 6. max_supported_gb >= capacity_gb
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

    # Append to extraction_meta.rejected
    meta = structured.setdefault("extraction_meta", {})
    rej_list = meta.setdefault("rejected", [])
    rej_list.extend(rejections)
    return rejections

print("Running consistency check on test cases...")
for idx in ['1', '30', '44', '51', '85', '17', '26', '29', '63', '77', '48']:
    item = fixtures[idx]
    import copy
    struct_copy = copy.deepcopy(item['structured'])
    rejs = validate_consistency(struct_copy, raw_specs=item.get('specs'))
    print(f"\n=== IDX {idx} ===")
    for r in rejs:
        print("  Rejection:", r)
    if idx == '1':
        print("  Result CPU:", struct_copy['cpu']['cores'], "cores,", struct_copy['cpu']['threads'], "threads")
    elif idx == '30':
        print("  Result CPU mfg:", struct_copy['cpu']['manufacturer'], "line:", struct_copy['cpu']['line'])
    elif idx == '44':
        print("  Result display aspect:", struct_copy['display']['aspect_ratio'])
    elif idx == '51':
        print("  Result GPU vram:", struct_copy['gpu']['vram_gb'])
    elif idx == '85':
        print("  Result storage ff:", struct_copy['storage']['form_factor'])
    elif idx in ('17', '26', '29'):
        print("  Result max RAM:", struct_copy['memory']['max_supported_gb'])
        if idx == '29':
            print("  Result adapter W:", struct_copy['power_battery']['power_adapter_w'])
    elif idx == '63':
        print("  Result adapter W:", struct_copy['power_battery']['power_adapter_w'])
    elif idx in ('77', '48'):
        print("  Result CPU:", struct_copy['cpu']['model'], struct_copy['cpu']['cores'], "cores,", struct_copy['cpu']['threads'], "threads")

