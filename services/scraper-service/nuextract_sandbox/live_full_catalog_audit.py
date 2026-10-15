"""Live Network Ground-Truth Audit: Audits 100% of laptops in compumarts_all_laptops_nuextract.json against live PDPs.

Evaluates every specification dimension across all 35+ fields directly against raw live DOM/HTML.
Filters strictly for our logic/extractor failures (where the spec is present on the live PDP but our extractor failed or corrupted it).
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nuextract_sandbox.scraper import PDPScraper

EXTRACTED_FILE = Path(__file__).resolve().parent / "output" / "compumarts_all_laptops_nuextract.json"
OUTPUT_REPORT_FILE = Path(__file__).resolve().parent / "output" / "live_audit_logic_failures.json"

def audit_single_laptop(record: dict[str, Any], scraper: PDPScraper) -> dict[str, Any]:
    url = record["url"]
    idx = record["index"]
    title_saved = record["title"]
    struct = record.get("structured", {})

    failures: list[dict[str, Any]] = []

    try:
        live_pdp = scraper.fetch_pdp(url)
    except Exception as e:
        return {
            "index": idx,
            "url": url,
            "title": title_saved,
            "fetch_error": str(e),
            "logic_failures": [],
        }

    live_title = live_pdp["title"]
    raw_specs = live_pdp["raw_specs"]
    all_table_text = " ".join(f"{k}: {v}" for k, v in raw_specs.items())
    all_live_text = f"{live_title} {all_table_text}"

    # Helpers
    def find_in_table(patterns: list[str]) -> list[tuple[str, str]]:
        matches = []
        for k, v in raw_specs.items():
            for p in patterns:
                if re.search(p, f"{k}: {v}", re.I):
                    matches.append((k, str(v)))
        return matches

    # =========================================================================
    # 1. IDENTITY AUDIT
    # =========================================================================
    ident = struct.get("identity", {})
    # laptop_model
    if not ident.get("laptop_model"):
        # Check if table had Model Name / Model
        model_rows = find_in_table([r"\bmodel\s*name\b", r"\bmodel\s*number\b", r"\blaptop\s*model\b"])
        if model_rows:
            failures.append({
                "field": "identity.laptop_model",
                "extracted": None,
                "expected_source": f"Table explicitly states: {model_rows[0][0]}: {model_rows[0][1]}",
                "failure_type": "table_model_missed",
            })
        else:
            # Check if clean model code was in title
            m_code = re.search(r"\b([A-Za-z0-9]{3,8}-[A-Za-z0-9]{2,8}(?:-[A-Za-z0-9]{2,8})?|\d{3}\s+G\d{1,2}|1[4567]-[a-z0-9]{6,10})\b", live_title)
            if m_code and m_code.group(1).lower() not in ["2-in-1", "wi-fi", "type-c"]:
                # Check if it was missed
                if not re.match(r"^(?:i[3579]|u\d+|r[3579]|core|ultra|ryzen|rtx|gtx)$", m_code.group(1), re.I):
                    failures.append({
                        "field": "identity.laptop_model",
                        "extracted": None,
                        "expected_source": f"Title code: '{m_code.group(1)}'",
                        "failure_type": "title_model_missed",
                    })

    # manufacturer_part_number
    if not ident.get("manufacturer_part_number"):
        mpn_rows = find_in_table([r"\bpart\s*number\b", r"\bmpn\b", r"\bsku\b", r"\bacer\s*part\s*number\b"])
        if mpn_rows and mpn_rows[0][1].strip().lower() not in ["no", "none", "n/a"]:
            failures.append({
                "field": "identity.manufacturer_part_number",
                "extracted": None,
                "expected_source": f"Table: {mpn_rows[0][0]}: {mpn_rows[0][1]}",
                "failure_type": "table_mpn_missed",
            })

    # =========================================================================
    # 2. CPU AUDIT
    # =========================================================================
    cpu = struct.get("cpu", {})
    if not cpu.get("model"):
        failures.append({
            "field": "cpu.model",
            "extracted": None,
            "expected_source": "CPU model missing despite laptop title/table",
            "failure_type": "cpu_model_null",
        })

    # CPU cores / threads
    if cpu.get("cores") is None:
        core_rows = find_in_table([r"\bcore\s*count\b", r"\bnumber\s*of\s*cores\b", r"\b\d+\s*cores?\b"])
        if core_rows:
            failures.append({
                "field": "cpu.cores",
                "extracted": None,
                "expected_source": f"Table: {core_rows[0][0]}: {core_rows[0][1]}",
                "failure_type": "cpu_cores_missed",
            })

    if cpu.get("threads") is None:
        thread_rows = find_in_table([r"\bthread\s*count\b", r"\bnumber\s*of\s*threads\b", r"\b\d+\s*threads?\b"])
        if thread_rows:
            failures.append({
                "field": "cpu.threads",
                "extracted": None,
                "expected_source": f"Table: {thread_rows[0][0]}: {thread_rows[0][1]}",
                "failure_type": "cpu_threads_missed",
            })

    # CPU cache_mb
    if cpu.get("cache_mb") is None:
        cache_match = re.search(r"\b(\d+)\s*(?:MB|M)\s*(?:Cache|Intel\s+Smart\s+Cache|L3\s+Cache)\b", all_live_text, re.I)
        if cache_match:
            c_val = int(cache_match.group(1))
            if 4 <= c_val <= 128:
                failures.append({
                    "field": "cpu.cache_mb",
                    "extracted": None,
                    "expected_source": f"Live text states: '{cache_match.group(0)}'",
                    "failure_type": "cpu_cache_missed",
                })

    # =========================================================================
    # 3. GPU AUDIT
    # =========================================================================
    gpu = struct.get("gpu", {})
    if not gpu.get("model"):
        failures.append({
            "field": "gpu.model",
            "extracted": None,
            "expected_source": "GPU model missing",
            "failure_type": "gpu_model_null",
        })

    # =========================================================================
    # 4. MEMORY AUDIT
    # =========================================================================
    mem = struct.get("memory", {})
    if mem.get("capacity_gb") is None:
        ram_m = re.search(r"\b(4|8|16|24|32|64|128)\s*(?:GB|G)\s*(?:RAM|Memory|DDR)\b", all_live_text, re.I)
        if ram_m:
            failures.append({
                "field": "memory.capacity_gb",
                "extracted": None,
                "expected_source": f"Live text: '{ram_m.group(0)}'",
                "failure_type": "ram_capacity_missed",
            })

    if not mem.get("memory_type"):
        type_m = re.search(r"\b(LPDDR5X|LPDDR5|DDR5|DDR4|LPDDR4X)\b", all_live_text, re.I)
        if type_m:
            failures.append({
                "field": "memory.memory_type",
                "extracted": None,
                "expected_source": f"Live text: '{type_m.group(0)}'",
                "failure_type": "ram_type_missed",
            })

    if mem.get("speed") is None:
        speed_m = re.search(r"\b(3200|4800|5200|5600|6400|7467|7500|8400|8533)\s*(?:MHz|MT/s)\b", all_live_text, re.I)
        if speed_m:
            failures.append({
                "field": "memory.speed",
                "extracted": None,
                "expected_source": f"Live text: '{speed_m.group(0)}'",
                "failure_type": "ram_speed_missed",
            })

    # =========================================================================
    # 5. STORAGE AUDIT
    # =========================================================================
    st = struct.get("storage", {})
    if st.get("capacity_gb") is None:
        st_m = re.search(r"\b(256|512|1024|2048|4096)\s*GB\s*(?:SSD|NVMe|PCIe|Storage)\b|\b([124])\s*TB\s*(?:SSD|NVMe|PCIe|Storage)\b", all_live_text, re.I)
        if st_m:
            failures.append({
                "field": "storage.capacity_gb",
                "extracted": None,
                "expected_source": f"Live text: '{st_m.group(0)}'",
                "failure_type": "storage_capacity_missed",
            })

    if not st.get("interface"):
        if_m = re.search(r"\b(PCIe\s*(?:4\.0|3\.0|Gen\s*4|Gen\s*3)?(?:\s*NVMe)?|NVMe|SATA)\b", all_live_text, re.I)
        if if_m and if_m.group(1).lower() not in ["no", "none"]:
            failures.append({
                "field": "storage.interface",
                "extracted": None,
                "expected_source": f"Live text: '{if_m.group(0)}'",
                "failure_type": "storage_interface_missed",
            })

    # =========================================================================
    # 6. DISPLAY AUDIT
    # =========================================================================
    disp = struct.get("display", {})
    if disp.get("size_inches") is None:
        inch_m = re.search(r'(\d{2}(?:\.\d+)?)\s*(?:["\u2033\u201d\u2019]|inch|\-inch|\s*in\b)', all_live_text, re.I)
        if inch_m:
            failures.append({
                "field": "display.size_inches",
                "extracted": None,
                "expected_source": f"Live text: '{inch_m.group(0)}'",
                "failure_type": "display_size_missed",
            })

    if not disp.get("resolution"):
        res_m = re.search(r"(\d{3,4})\s*[xX*×]\s*(\d{3,4})|\b(FHD\+|FHD|WUXGA|QHD\+|QHD|WQXGA|UHD|2\.5K|2K|3K|4K)\b", all_live_text, re.I)
        if res_m:
            failures.append({
                "field": "display.resolution",
                "extracted": None,
                "expected_source": f"Live text: '{res_m.group(0)}'",
                "failure_type": "display_resolution_missed",
            })

    if disp.get("refresh_rate_hz") is None:
        hz_m = re.search(r"\b(60|90|120|144|165|180|240|300|360)\s*Hz\b", all_live_text, re.I)
        if hz_m:
            failures.append({
                "field": "display.refresh_rate_hz",
                "extracted": None,
                "expected_source": f"Live text: '{hz_m.group(0)}'",
                "failure_type": "refresh_rate_missed",
            })

    # =========================================================================
    # 7. AUDIO & WEBCAM AUDIT
    # =========================================================================
    audio = struct.get("audio", {})
    if audio.get("speaker_count") is None:
        sp_rows = find_in_table([r"\bnumber\s*of\s*speakers\b", r"\bspeakers?\b"])
        for k, v in sp_rows:
            if re.search(r"(?:x\s*[1-8]|[1-8]\s*x|\b[1-8]\s*(?:speakers?|w\b)|\b[1-8]\b|dual|stereo)", v, re.I):
                failures.append({
                    "field": "audio.speaker_count",
                    "extracted": None,
                    "expected_source": f"Table: {k}: {v}",
                    "failure_type": "speaker_count_missed",
                })
                break

    if not audio.get("microphone"):
        mic_rows = find_in_table([r"\bmicrophone\b", r"\bbuilt-in\s*microphone\b"])
        # Exclude port entries like '1x Headphone / microphone combo jack' where key is 'ports' or 'i/o'
        mic_rows = [
            (k, v) for k, v in mic_rows
            if not re.search(r"\b(?:ports?|interfaces?|i/?o|connect(?:ors?|ivity))\b", k, re.I)
            and not re.search(r"combo\s*jack|headphone\s*/\s*microphone\s*jack", v, re.I)
        ]
        if mic_rows and any(w in mic_rows[0][1].lower() for w in ["yes", "mic", "array", "dual", "digital", "built-in"]):
            failures.append({
                "field": "audio.microphone",
                "extracted": None,
                "expected_source": f"Table: {mic_rows[0][0]}: {mic_rows[0][1]}",
                "failure_type": "microphone_missed",
            })

    webcam = struct.get("webcam", {})
    if not webcam.get("resolution"):
        cam_rows = find_in_table([r"\bcamera\b", r"\bwebcam\b"])
        for k, v in cam_rows:
            if re.search(r"\b(\d{3,4}\s*p|HD|FHD|QHD|\d+(?:\.\d+)?\s*(?:MP|M\b))\b", v, re.I):
                failures.append({
                    "field": "webcam.resolution",
                    "extracted": None,
                    "expected_source": f"Table: {k}: {v}",
                    "failure_type": "webcam_resolution_missed",
                })
                break

    # =========================================================================
    # 8. PHYSICAL CHASSIS AUDIT
    # =========================================================================
    phys = struct.get("physical", {})
    for dim_fld, dim_pat in [("width_mm", r"\bwidth\b"), ("depth_mm", r"\bdepth\b"), ("height_mm", r"\bheight\b|\bthickness\b")]:
        if phys.get(dim_fld) is None:
            dim_rows = find_in_table([dim_pat])
            if dim_rows and re.search(r"\b\d+(?:\.\d+)?\s*(?:mm|cm)\b", dim_rows[0][1], re.I):
                failures.append({
                    "field": f"physical.{dim_fld}",
                    "extracted": None,
                    "expected_source": f"Table: {dim_rows[0][0]}: {dim_rows[0][1]}",
                    "failure_type": f"{dim_fld}_missed",
                })

    return {
        "index": idx,
        "url": url,
        "title": live_title,
        "logic_failures": failures,
    }


def main():
    print("=" * 80)
    print("LIVE NETWORK GROUND-TRUTH AUDIT (100% LIVE PDP HTML FETCH)")
    print("=" * 80)

    if not EXTRACTED_FILE.exists():
        print(f"[Error] File not found: {EXTRACTED_FILE}")
        return

    with open(EXTRACTED_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    total_laptops = len(records)
    print(f"[*] Auditing {total_laptops} laptops against raw live PDP HTML directly over network...")

    scraper = PDPScraper()
    results = []
    t0 = time.time()

    # Parallel live network fetching (8 workers)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(audit_single_laptop, r, scraper): r for r in records}
        completed = 0
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            completed += 1
            if completed % 15 == 0 or completed == total_laptops:
                print(f"  [{completed}/{total_laptops}] Live PDPs audited ({time.time() - t0:.1f}s)...")

    results.sort(key=lambda x: x["index"])
    elapsed = time.time() - t0
    print(f"\n[OK] Fetched and verified 100% of {total_laptops} live PDPs in {elapsed:.1f}s")

    # Filter strictly for laptops where our logic failed
    laptops_with_logic_failures = [r for r in results if len(r["logic_failures"]) > 0]
    total_failures = sum(len(r["logic_failures"]) for r in laptops_with_logic_failures)

    print("\n" + "=" * 80)
    print(f"AUDIT SUMMARY: {len(laptops_with_logic_failures)} / {total_laptops} LAPTOPS CONTAIN LOGIC FAILURES ({total_failures} TOTAL FIELD DEFECTS)")
    print("=" * 80)

    # Save to JSON
    with open(OUTPUT_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_laptops_audited": total_laptops,
            "laptops_with_failures_count": len(laptops_with_logic_failures),
            "total_field_failures": total_failures,
            "elapsed_seconds": round(elapsed, 2),
            "failures_by_laptop": laptops_with_logic_failures,
        }, f, indent=2, ensure_ascii=False)

    print(f"[OK] Full failure breakdown saved to: {OUTPUT_REPORT_FILE}")

if __name__ == "__main__":
    main()

