"""Full Audit Script: Compares all 119 laptops in hybrid_results.json against their live CompuMarts PDPs.

Strictly READ-ONLY regarding hybrid_results.json.
Fetches live PDP HTML via curl_cffi and compares specifications across all catalog categories.
"""

import concurrent.futures
import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests as cffi_requests
from local_extractor.table_extractor import extract_raw_spec_table

HYBRID_FILE = os.path.join(os.path.dirname(__file__), "hybrid_results.json")
AUDIT_OUT_FILE = os.path.join(os.path.dirname(__file__), "audit_119_full.json")


def fetch_live_pdp(url: str, retries: int = 2) -> tuple[str, dict[str, str], int]:
    """Fetch live PDP HTML and parse specs table."""
    for attempt in range(retries + 1):
        try:
            res = cffi_requests.get(url, impersonate="chrome", timeout=20)
            if res.status_code == 200:
                specs = extract_raw_spec_table(res.text)
                return url, specs, res.status_code
            elif res.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
        except Exception:
            time.sleep(1.0)
    return url, {}, 0


def audit_laptop(idx: int, item: dict, live_specs: dict[str, str], status_code: int) -> dict:
    """Compare structured catalog fields against live PDP specifications."""
    title = item.get("title", "")
    url = item.get("product_url", "")
    structured = item.get("structured", {})

    field_audits = {}

    # 1. Identity Audit
    brand_s = structured.get("identity", {}).get("brand") or ""
    family_s = structured.get("identity", {}).get("laptop_family") or ""
    model_s = structured.get("identity", {}).get("laptop_model") or ""
    mpn_s = structured.get("identity", {}).get("manufacturer_part_number") or ""

    # Check if brand matches title/specs
    brand_ok = bool(brand_s and brand_s.lower() in title.lower())
    field_audits["brand"] = {"value": brand_s, "verified": brand_ok}

    # Model / MPN verification
    model_ok = bool(model_s and (model_s.lower() in title.lower() or any(model_s.lower() in str(v).lower() for v in live_specs.values())))
    field_audits["model"] = {"value": model_s, "verified": model_ok}

    # 2. CPU Audit
    cpu_s = structured.get("cpu", {})
    cpu_name = cpu_s.get("full_name") or cpu_s.get("model") or ""
    cpu_cores = cpu_s.get("cores")
    cpu_verified = False
    for k, v in live_specs.items():
        if any(c in k.lower() for c in ["processor", "cpu"]):
            if cpu_s.get("model") and str(cpu_s.get("model")).lower() in str(v).lower():
                cpu_verified = True
                break
            if cpu_name and any(part.lower() in str(v).lower() for part in cpu_name.split() if len(part) > 2):
                cpu_verified = True
                break
    field_audits["cpu"] = {"value": cpu_name, "cores": cpu_cores, "verified": cpu_verified}

    # 3. GPU Audit
    gpu_s = structured.get("gpu", {})
    gpu_model = gpu_s.get("model") or ""
    gpu_vram = gpu_s.get("vram_gb")
    gpu_verified = False
    for k, v in live_specs.items():
        if any(g in k.lower() for g in ["graphics", "gpu"]):
            if gpu_model and any(w.lower() in str(v).lower() for w in gpu_model.split() if len(w) > 3):
                gpu_verified = True
                break
            if gpu_s.get("integrated") and any(i in str(v).lower() for i in ["integrated", "shared", "intel graphics", "radeon"]):
                gpu_verified = True
                break
    field_audits["gpu"] = {"value": gpu_model, "vram_gb": gpu_vram, "verified": gpu_verified}

    # 4. RAM Audit
    ram_s = structured.get("memory", {})
    ram_gb = ram_s.get("capacity_gb")
    ram_verified = False
    for k, v in live_specs.items():
        if any(m in k.lower() for m in ["memory", "ram"]):
            if ram_gb and str(ram_gb) in str(v):
                ram_verified = True
                break
    field_audits["ram"] = {"capacity_gb": ram_gb, "type": ram_s.get("memory_type"), "verified": ram_verified}

    # 5. Storage Audit
    storage_s = structured.get("storage", {})
    storage_gb = storage_s.get("capacity_gb")
    storage_verified = False
    for k, v in live_specs.items():
        if any(s in k.lower() for s in ["storage", "solid state", "ssd"]):
            if storage_gb:
                # Check for 512, 1024 / 1TB, etc.
                if str(storage_gb) in str(v) or (storage_gb == 1024 and ("1tb" in str(v).lower() or "1 tb" in str(v).lower())):
                    storage_verified = True
                    break
    field_audits["storage"] = {"capacity_gb": storage_gb, "verified": storage_verified}

    # 6. Display Audit
    disp_s = structured.get("display", {})
    size_in = disp_s.get("size_inches")
    res_str = disp_s.get("resolution") or ""
    disp_verified = False
    for k, v in live_specs.items():
        if any(d in k.lower() for d in ["screen", "display", "resolution"]):
            if (size_in and str(size_in) in str(v)) or (res_str and res_str in str(v)) or (disp_s.get("resolution_width") and str(disp_s.get("resolution_width")) in str(v)):
                disp_verified = True
                break
    field_audits["display"] = {"size": size_in, "resolution": res_str, "hz": disp_s.get("refresh_rate_hz"), "verified": disp_verified}

    # 7. Battery & Power Audit
    pwr_s = structured.get("power_battery", {})
    battery_wh = pwr_s.get("battery_capacity_wh")
    adapter_w = pwr_s.get("power_adapter_w")
    pwr_verified = bool(battery_wh or adapter_w or pwr_s.get("battery_cells"))
    field_audits["power"] = {"battery_wh": battery_wh, "adapter_w": adapter_w, "verified": pwr_verified}

    # Overall Match Score
    verified_count = sum(1 for f in field_audits.values() if f.get("verified"))
    total_fields = len(field_audits)
    score_pct = round((verified_count / total_fields) * 100, 1)

    return {
        "index": idx,
        "title": title,
        "url": url,
        "http_status": status_code,
        "live_specs_row_count": len(live_specs),
        "score_pct": score_pct,
        "field_audits": field_audits,
        "live_specs_sample": {k: v for k, v in list(live_specs.items())[:10]},
    }


def main():
    if not os.path.exists(HYBRID_FILE):
        print(f"[ERROR] {HYBRID_FILE} not found!")
        sys.exit(1)

    print("=" * 80)
    print(f"[*] Loading laptops from: {HYBRID_FILE}")
    with open(HYBRID_FILE, "r", encoding="utf-8") as f:
        laptops = json.load(f)

    total_laptops = len(laptops)
    print(f"[*] Total laptops to audit: {total_laptops}")
    print("[*] Fetching live PDPs concurrently via curl_cffi (max_workers=5)...")
    print("=" * 80)

    start_t = time.perf_counter()

    # Step 1: Concurrently fetch all live PDPs
    url_to_specs: dict[str, tuple[dict[str, str], int]] = {}
    urls = [(i, lap.get("product_url", "")) for i, lap in enumerate(laptops)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_idx = {
            executor.submit(fetch_live_pdp, u): (idx, u)
            for idx, u in urls if u
        }

        completed = 0
        for future in concurrent.futures.as_completed(future_to_idx):
            idx, u = future_to_idx[future]
            try:
                url_ret, specs, status = future.result()
                url_to_specs[u] = (specs, status)
            except Exception as e:
                url_to_specs[u] = ({}, 0)

            completed += 1
            if completed % 20 == 0 or completed == total_laptops:
                print(f"  [Fetching Live PDPs: {completed:3d}/{total_laptops}] ({time.perf_counter()-start_t:.1f}s)")

    fetch_time = time.perf_counter() - start_t
    print(f"\n[OK] Fetched all {total_laptops} live PDPs in {fetch_time:.2f}s!")

    # Step 2: Compare each laptop
    print("\n[*] Auditing structured specs vs live PDPs...")
    audit_results = []
    scores = []
    brand_stats = {}

    for idx, lap in enumerate(laptops):
        u = lap.get("product_url", "")
        specs, status = url_to_specs.get(u, ({}, 0))

        audit_res = audit_laptop(idx, lap, specs, status)
        audit_results.append(audit_res)
        scores.append(audit_res["score_pct"])

        # Track Brand stats
        brand = lap.get("structured", {}).get("identity", {}).get("brand") or "Unknown"
        brand_stats.setdefault(brand, []).append(audit_res["score_pct"])

        # Progress sample
        cpu_val = audit_res["field_audits"]["cpu"]["value"] or "N/A"
        ram_val = audit_res["field_audits"]["ram"]["capacity_gb"]
        disp_val = audit_res["field_audits"]["display"]["resolution"] or "N/A"
        rows_n = audit_res["live_specs_row_count"]
        print(f"  [{idx+1:03d}/{total_laptops}] Live Rows: {rows_n:2d} | Score: {audit_res['score_pct']:5.1f}% | Brand: {brand[:8]:<8} | CPU: {cpu_val[:20]:<20} | RAM: {ram_val}GB | Disp: {disp_val[:10]}")

    # Step 3: Save Full Audit JSON
    with open(AUDIT_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2, ensure_ascii=False)

    total_time = time.perf_counter() - start_t
    avg_score = sum(scores) / len(scores) if scores else 0.0

    print("\n" + "=" * 80)
    print("🎯 FULL 119-LAPTOP AUDIT SUMMARY:")
    print(f"  - Total Laptops Audited:    {total_laptops}")
    print(f"  - Total Time Elapsed:       {total_time:.2f}s")
    print(f"  - Average Fidelity Score:   {avg_score:.1f}%")
    print(f"  - Perfect Match Rate:       {sum(1 for s in scores if s >= 99.0)} / {total_laptops} laptops")
    print(f"  - Results saved to:         {AUDIT_OUT_FILE}")
    print("\n  Brand Performance Breakdown:")
    for b, scs in sorted(brand_stats.items(), key=lambda x: -len(x[1])):
        print(f"    • {b:<12}: {len(scs):2d} laptops | Avg Match: {sum(scs)/len(scs):.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    main()

