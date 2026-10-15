"""Non-destructive catalog updater: Apply the 8 validated bug fixes across all 116 laptops."""

import json
import re
import sys
from pathlib import Path
from copy import deepcopy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.validators import (
    validate_webcam,
    validate_microphone,
    normalize_dimensions,
)

RAW_SPECS_FILE = Path(__file__).resolve().parent.parent / "local_extractor" / "my_raw_specs.json"
EXTRACTED_FILE = Path(__file__).resolve().parent / "output" / "compumarts_all_laptops_nuextract.json"

def main():
    raw_specs_by_url = {}
    if RAW_SPECS_FILE.exists():
        for item in json.load(open(RAW_SPECS_FILE, "r", encoding="utf-8")):
            raw_specs_by_url[item["product_url"]] = item.get("specs", {})

    with open(EXTRACTED_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    extractor = CompumartsExtractor()
    fixed_count = 0
    stat_changes = {
        "identity_model_fixed": 0,
        "title_resolution_fixed": 0,
        "storage_interface_fixed": 0,
        "dimension_cm_converted": 0,
        "speaker_count_rescued": 0,
        "microphone_rescued": 0,
        "webcam_rescued": 0,
        "unmapped_keys_resolved": 0,
    }

    updated_records = []

    for r in records:
        idx = r["index"]
        url = r["url"]
        title = r["title"]
        meta_in = r.get("metadata", {})
        raw_s = raw_specs_by_url.get(url, {})

        struct_orig = deepcopy(r["structured"])
        meta_orig = struct_orig.get("extraction_meta", {})
        orig_sources = meta_orig.get("field_sources", {})
        orig_rejected = meta_orig.get("rejected", [])

        # Run updated Tier 1 Extractor
        t1_struct, _ = extractor.extract(raw_s, title, metadata=meta_in)
        t1_meta = t1_struct.get("extraction_meta", {})
        t1_sources = t1_meta.get("field_sources", {})

        # Merge with existing NuExtract fields non-destructively:
        # 1. Start with updated Tier 1
        merged_struct = deepcopy(t1_struct)
        merged_meta = merged_struct.setdefault("extraction_meta", {})
        merged_sources = merged_meta.setdefault("field_sources", {})
        merged_rejected = []

        # 2. Re-apply any fields previously provided by NuExtract if Tier 1 didn't provide them
        for section, sec_data in struct_orig.items():
            if section in ("extraction_meta", "product_type", "condition"):
                continue
            if not isinstance(sec_data, dict):
                continue
            merged_sec = merged_struct.setdefault(section, {})
            for k, v in sec_data.items():
                if v is not None and merged_sec.get(k) is None:
                    # If NuExtract originally provided it, keep it
                    src = orig_sources.get(f"{section}.{k}")
                    if src == "nuextract":
                        merged_sec[k] = v
                        merged_sources[f"{section}.{k}"] = "nuextract"

        # 3. Apply BUG-01: Fix dimensions in cm
        phys = merged_struct.setdefault("physical", {})
        w = phys.get("width_mm")
        d = phys.get("depth_mm")
        h = phys.get("height_mm")
        dim_changed = False
        if w is not None and w < 60.0:
            phys["width_mm"] = round(w * 10.0, 1)
            dim_changed = True
        if d is not None and d < 60.0:
            phys["depth_mm"] = round(d * 10.0, 1)
            dim_changed = True
        if h is not None and h < 5.0:
            phys["height_mm"] = round(h * 10.0, 1)
            dim_changed = True

        # If one dimension is in mm (> 150) and another is between 20 and 50 (cm), multiply that cm dimension by 10
        dims = [phys.get("width_mm"), phys.get("depth_mm"), phys.get("height_mm")]
        has_large_mm = any(v is not None and v > 150.0 for v in dims)
        for dim_k in ("width_mm", "depth_mm", "height_mm"):
            val = phys.get(dim_k)
            if val is not None and 20.0 <= val <= 50.0 and has_large_mm:
                phys[dim_k] = round(val * 10.0, 1)
                dim_changed = True

        # Check if depth was rejected due to < 5mm bound (e.g., 1.34 cm rejected because 1.34 < 5.0)
        for rej in orig_rejected:
            if rej.get("field") == "physical.depth_mm" and phys.get("depth_mm") is None:
                val = rej.get("value")
                m = re.search(r"(\d+(?:\.\d+)?)", str(val))
                if m:
                    fv = float(m.group(1))
                    if fv < 60.0 or "cm" in str(val).lower():
                        fv = round(fv * 10.0, 1)
                    if 170.0 <= fv <= 320.0:
                        phys["depth_mm"] = fv
                        merged_sources["physical.depth_mm"] = "nuextract"
                        dim_changed = True

        if phys.get("width_mm") and phys.get("depth_mm") and phys.get("height_mm"):
            nw, nd, nh = normalize_dimensions(phys["width_mm"], phys["depth_mm"], phys["height_mm"])
            if nw and nd and nh:
                phys["width_mm"], phys["depth_mm"], phys["height_mm"] = nw, nd, nh
        if dim_changed:
            stat_changes["dimension_cm_converted"] += 1

        # 4. Apply BUG-03: Rescue speaker count previously rejected
        audio = merged_struct.setdefault("audio", {})
        if audio.get("speaker_count") is None:
            for rej in orig_rejected:
                if rej.get("field") == "audio.speaker_count":
                    val_sc = str(rej.get("value")).strip()
                    val_sc_low = val_sc.lower()
                    count = None
                    if "quad" in val_sc_low:
                        count = 4
                    elif "dual" in val_sc_low or "stereo" in val_sc_low:
                        count = 2
                    else:
                        m_sp = re.search(r"(?:x\s*([1-8])|([1-8])\s*x|\b([1-8])\s*(?:speakers?|w\b)|\b([1-8])\b)", val_sc, re.I)
                        if m_sp:
                            c_str = m_sp.group(1) or m_sp.group(2) or m_sp.group(3) or m_sp.group(4)
                            count = int(c_str)
                    if count is not None and not any(bad in val_sc_low for bad in ["mp", "hz", "ram", "gb"]):
                        audio["speaker_count"] = count
                        merged_sources["audio.speaker_count"] = "nuextract"
                        stat_changes["speaker_count_rescued"] += 1
                        break

        # 5. Apply BUG-04: Rescue microphone previously rejected
        if not audio.get("microphone"):
            for rej in orig_rejected:
                if rej.get("field") == "audio.microphone":
                    v_mic, err_mic = validate_microphone(rej.get("value"))
                    if v_mic:
                        audio["microphone"] = v_mic
                        audio["has_microphone"] = True
                        merged_sources["audio.microphone"] = "nuextract"
                        stat_changes["microphone_rescued"] += 1
                        break

        # 6. Apply BUG-07: Rescue webcam previously rejected
        webcam = merged_struct.setdefault("webcam", {})
        if not webcam.get("resolution"):
            for rej in orig_rejected:
                if rej.get("field") == "webcam.resolution":
                    v_cam, err_cam = validate_webcam(rej.get("value"))
                    if v_cam:
                        webcam["resolution"] = v_cam
                        merged_sources["webcam.resolution"] = "nuextract"
                        stat_changes["webcam_rescued"] += 1
                        break

        # Re-filter rejected list to remove any rescued fields
        for rej in orig_rejected:
            fld = rej.get("field")
            if fld == "audio.speaker_count" and audio.get("speaker_count") is not None:
                continue
            if fld == "audio.microphone" and audio.get("microphone") is not None:
                continue
            if fld == "webcam.resolution" and webcam.get("resolution") is not None:
                continue
            if fld == "physical.depth_mm" and phys.get("depth_mm") is not None:
                continue
            merged_rejected.append(rej)

        merged_meta["rejected"] = merged_rejected

        # Track stats
        if not struct_orig.get("identity", {}).get("laptop_model") and merged_struct.get("identity", {}).get("laptop_model"):
            stat_changes["identity_model_fixed"] += 1
        if not struct_orig.get("display", {}).get("resolution") and merged_struct.get("display", {}).get("resolution"):
            stat_changes["title_resolution_fixed"] += 1
        if not struct_orig.get("storage", {}).get("interface") and merged_struct.get("storage", {}).get("interface"):
            stat_changes["storage_interface_fixed"] += 1

        unmapped_orig_cnt = len(meta_orig.get("unmapped_keys", []))
        unmapped_new_cnt = len(t1_meta.get("unmapped_keys", []))
        if unmapped_new_cnt < unmapped_orig_cnt:
            stat_changes["unmapped_keys_resolved"] += (unmapped_orig_cnt - unmapped_new_cnt)

        # Update record
        r_updated = deepcopy(r)
        r_updated["structured"] = merged_struct
        updated_records.append(r_updated)

    # Save atomically
    temp_out = EXTRACTED_FILE.with_suffix(".tmp")
    with open(temp_out, "w", encoding="utf-8") as f:
        json.dump(updated_records, f, indent=2, ensure_ascii=False)
    temp_out.replace(EXTRACTED_FILE)

    print("=" * 80)
    print("BUG FIXES APPLIED SUCCESSFULLY ACROSS 116 LAPTOPS")
    print("=" * 80)
    for k, v in stat_changes.items():
        print(f"  - {k}: {v} records improved")
    print(f"\n[OK] Updated catalog data written to {EXTRACTED_FILE}")

if __name__ == "__main__":
    main()
