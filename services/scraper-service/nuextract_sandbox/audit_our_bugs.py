"""Comprehensive Code-Side Bug Audit: Inspect all 116 records for extractor bugs."""

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RAW_SPECS_FILE = Path(__file__).resolve().parent.parent / "local_extractor" / "my_raw_specs.json"
EXTRACTED_FILE = Path(__file__).resolve().parent / "output" / "compumarts_all_laptops_nuextract.json"

def main():
    raw_specs_by_url = {}
    if RAW_SPECS_FILE.exists():
        for item in json.load(open(RAW_SPECS_FILE, "r", encoding="utf-8")):
            raw_specs_by_url[item["product_url"]] = item.get("specs", {})

    with open(EXTRACTED_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    bugs = {
        "title_resolution_not_extracted": [],
        "dimension_unit_cm_not_converted": [],
        "speaker_count_regex_word_boundary_fail": [],
        "microphone_keyword_strictness_fail": [],
        "webcam_megapixels_suffix_fail": [],
        "identity_model_missing_from_title": [],
        "storage_interface_missed_when_in_table": [],
        "unmapped_store_keys_with_specs": [],
        "mpn_whitespace_or_formatting_defect": [],
    }

    for r in records:
        idx = r["index"]
        url = r["url"]
        title = r["title"]
        struct = r["structured"]
        meta = struct.get("extraction_meta", {})
        raw_s = raw_specs_by_url.get(url, {})

        # 1. Title Resolution Bug: Title has resolution keywords, but resolution is null
        disp = struct.get("display", {})
        if not disp.get("resolution"):
            m_res = re.search(r"\b(FHD\+|FHD|WUXGA|QHD\+|QHD|WQXGA|UHD|2\.5K|2K|3K|4K)\b", title, re.I)
            if m_res:
                bugs["title_resolution_not_extracted"].append({
                    "index": idx,
                    "title": title[:65],
                    "keyword_found": m_res.group(1),
                })

        # 2. Dimensions Bug: Dimensions in cm not converted to mm
        phys = struct.get("physical", {})
        for dim in ("height_mm", "width_mm", "depth_mm"):
            val = phys.get(dim)
            if val is not None and ((dim in ("width_mm", "depth_mm") and val < 60.0) or (dim == "height_mm" and val < 5.0)):
                bugs["dimension_unit_cm_not_converted"].append({
                    "index": idx,
                    "title": title[:65],
                    "field": dim,
                    "value_stored": val,
                    "probable_true_mm": round(val * 10, 1),
                })

        # 3. Speaker Count Bug: 2W x2 rejected due to \b([1-8])\b word boundary
        for rej in meta.get("rejected", []):
            if rej.get("rule") == "invalid_speaker_count":
                v = str(rej.get("value"))
                if re.search(r"x\s*[1-8]|[1-8]\s*x|[1-8]\s*speaker", v, re.I):
                    bugs["speaker_count_regex_word_boundary_fail"].append({
                        "index": idx,
                        "title": title[:65],
                        "rejected_value": v,
                    })

        # 4. Microphone Bug: 2x, Array rejected by mic_missing_keyword
        for rej in meta.get("rejected", []):
            if rej.get("rule") == "mic_missing_keyword":
                v = str(rej.get("value"))
                if any(w in v.lower() for w in ["array", "dual", "stereo", "digital"]):
                    bugs["microphone_keyword_strictness_fail"].append({
                        "index": idx,
                        "title": title[:65],
                        "rejected_value": v,
                    })

        # 5. Webcam Bug: 5.0M rejected by webcam_unrecognized
        for rej in meta.get("rejected", []):
            if rej.get("rule") == "webcam_unrecognized":
                v = str(rej.get("value"))
                if re.search(r"\b\d+(?:\.\d+)?\s*M\b", v, re.I):
                    bugs["webcam_megapixels_suffix_fail"].append({
                        "index": idx,
                        "title": title[:65],
                        "rejected_value": v,
                    })

        # 6. Identity Model Bug: Null laptop_model despite code in title
        ident = struct.get("identity", {})
        if not ident.get("laptop_model"):
            # Look for model codes like ANV15-A31-R8LA, B14WGK, X1504VA, etc.
            m_code = re.search(r"\b([A-Z0-9]{3,8}-[A-Z0-9]{3,8}|[A-Z][0-9]{4}[A-Z0-9]{1,4}|[A-Z0-9]{6,10})\b", title)
            if m_code and m_code.group(1).lower() not in ["windows", "gaming", "laptop", "rtx4050", "rtx4060", "rtx5050"]:
                bugs["identity_model_missing_from_title"].append({
                    "index": idx,
                    "title": title[:65],
                    "candidate_model": m_code.group(1),
                })

        # 7. Storage Interface Bug: In raw specs, but ended up null
        st = struct.get("storage", {})
        if not st.get("interface") and raw_s:
            for k, v in raw_s.items():
                if any(w in str(v).lower() for w in ["nvme", "pcie", "sata"]):
                    bugs["storage_interface_missed_when_in_table"].append({
                        "index": idx,
                        "title": title[:65],
                        "table_row": f"{k}: {v}",
                    })
                    break

        # 8. Unmapped Keys containing valid specs
        for unmapped in meta.get("unmapped_keys", []):
            u_low = unmapped.lower()
            if any(w in u_low for w in ["colour", "display tech", "display quality", "acer part number"]):
                bugs["unmapped_store_keys_with_specs"].append({
                    "index": idx,
                    "title": title[:65],
                    "unmapped_key": unmapped,
                })

    print("=" * 80)
    print("CODE-SIDE DEFECT / BUG AUDIT REPORT (ALL 116 LIVE LAPTOPS)")
    print("=" * 80)
    for category, items in bugs.items():
        print(f"\n[{category}] -> {len(items)} instances found:")
        for it in items[:4]:
            print(f"  - Laptop #{it['index']}: {it}")
        if len(items) > 4:
            print(f"    ... and {len(items) - 4} more")

    # Save to JSON
    out_file = Path(__file__).resolve().parent / "output" / "code_bugs_audit.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(bugs, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Detailed bug audit saved to {out_file}")

if __name__ == "__main__":
    main()

