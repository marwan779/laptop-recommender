"""Test and verify the deterministic extraction logic for:
1. physical (width_mm, depth_mm, height_mm, color)
2. connectivity (ports, ethernet)
3. audio_webcam (speaker_count, microphone, webcam_resolution)
4. build_security (pointing_device, security_features, has_fingerprint, has_backlit_keyboard)

Across real CompuMarts JSON scrapes.
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


def normalize_dimensions(w: Any, d: Any, h: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Normalize laptop chassis dimensions ensuring metric mm and width >= depth >= height."""
    vals = []
    for dim in [w, d, h]:
        if dim is not None:
            try:
                vals.append(float(dim))
            except (ValueError, TypeError):
                pass

    if len(vals) < 3:
        w_res = float(w) if w and 250 <= float(w) <= 460 else None
        d_res = float(d) if d and 170 <= float(d) <= 320 else None
        h_res = float(h) if h and 8 <= float(h) <= 40 else None
        return w_res, d_res, h_res

    v1, v2, v3 = vals[0], vals[1], vals[2]

    # Detect cm: if all three values < 60 and the smallest < 4.5 (thickness in cm)
    if all(x < 60 for x in [v1, v2, v3]) and min(v1, v2, v3) < 4.5:
        v1 *= 10.0
        v2 *= 10.0
        v3 *= 10.0

    # Ensure axis order: width >= depth >= height
    sorted_dims = sorted([v1, v2, v3], reverse=True)
    norm_w, norm_d, norm_h = sorted_dims[0], sorted_dims[1], sorted_dims[2]

    # Plausible laptop ranges (mm): width 250-460, depth 170-320, height 8-40
    if not (250 <= norm_w <= 460 and 170 <= norm_d <= 320 and 8 <= norm_h <= 40):
        return None, None, None

    return round(norm_w, 1), round(norm_d, 1), round(norm_h, 1)


def parse_dimensions_from_text(text: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not text:
        return None, None, None

    # 1. Height / Width / Depth labeled text (e.g. Apple, Dell)
    m_h = re.search(r"\bheight\b[^\d]*(\d+(?:\.\d+)?)\s*(mm|cm)?", text, re.I)
    m_w = re.search(r"\bwidth\b[^\d]*(\d+(?:\.\d+)?)\s*(mm|cm)?", text, re.I)
    m_d = re.search(r"\bdepth\b[^\d]*(\d+(?:\.\d+)?)\s*(mm|cm)?", text, re.I)
    if m_h and m_w and m_d:
        h_val, h_unit = float(m_h.group(1)), m_h.group(2)
        w_val, w_unit = float(m_w.group(1)), m_w.group(2)
        d_val, d_unit = float(m_d.group(1)), m_d.group(2)
        if h_unit == "cm" or "cm" in text.lower():
            if h_val < 10: h_val *= 10.0
            if w_val < 60: w_val *= 10.0
            if d_val < 60: d_val *= 10.0
        return normalize_dimensions(w_val, d_val, h_val)

    # 2. Triple measurement (e.g. 359.86 x 258.7 x 21.9-23.9 mm or 36.9 x 25.94 x 2.29 cm)
    m_trip = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*[xX×*]\s*(\d+(?:\.\d+)?)(?:[-–—](\d+(?:\.\d+)?))?\s*(mm|cm)?",
        text,
    )
    if m_trip:
        v1 = float(m_trip.group(1))
        v2 = float(m_trip.group(2))
        v3 = float(m_trip.group(3))
        unit = m_trip.group(5)
        if unit == "cm" or (v1 < 60 and v2 < 60 and v3 < 60 and min(v1, v2, v3) < 4.5):
            v1 *= 10.0
            v2 *= 10.0
            v3 *= 10.0
        return normalize_dimensions(v1, v2, v3)

    return None, None, None


def split_ports(text: str) -> List[str]:
    """Split and clean a raw port string into individual port items."""
    if not text:
        return []
    # If text contains semicolons, split by semicolon
    if ";" in text:
        raw_items = [p.strip() for p in text.split(";") if p.strip()]
    else:
        # Split by comma NOT inside parentheses
        raw_items = [p.strip() for p in re.split(r",\s*(?![^()]*\))", text) if p.strip()]

    cleaned = []
    for item in raw_items:
        # Remove footnote markers, trademark symbols
        p_clean = re.sub(r"[®™©\u200e\u200f\u200b\xa0]", " ", item)
        p_clean = re.sub(r"\s+", " ", p_clean).strip()
        if not p_clean or p_clean.lower() in ("none", "n/a", "no", "0"):
            continue
        # Skip pure marketing text
        if any(bad in p_clean.lower() for bad in ["all the ports you need", "built to dominate", "connect with ease"]):
            continue
        cleaned.append(p_clean)
    return cleaned


def test_on_all_files():
    files = glob.glob("services/scraper-service/raw_scrapes/compumarts/*.json")
    print(f"Testing on {len(files)} CompuMarts laptops...")

    stats = {
        "dimensions": 0,
        "ports": 0,
        "ethernet": 0,
        "webcam": 0,
        "mic": 0,
        "speakers": 0,
        "fingerprint": 0,
        "backlit": 0,
        "pointing": 0,
        "security": 0,
    }

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        specs = data.get("raw_tables", {}).get("specs", {})
        title = data.get("title", "")

        # 1. Dimensions
        dim_text = ""
        for k, v in specs.items():
            if any(term in k.lower() for term in ["dimension", "dimensions (wxdxh)", "size"]):
                dim_text = str(v)
                break
        w, d, h = parse_dimensions_from_text(dim_text)
        if w and d and h:
            stats["dimensions"] += 1

        # 2. Ports & Ethernet
        ports_list = []
        eth = None
        for k, v in specs.items():
            kl = k.lower()
            if any(term in kl for term in ["standard ports", "external i/o", "ports", "i/o ports"]):
                ports_list = split_ports(str(v))
            if any(term in kl for term in ["ethernet", "lan", "rj-45", "rj45"]):
                eth = str(v).strip()

        if not eth and ports_list:
            for p in ports_list:
                if re.search(r"\b(rj-?45|ethernet|lan)\b", p, re.I):
                    eth = p
                    break

        if ports_list:
            stats["ports"] += 1
        if eth:
            stats["ethernet"] += 1

        # 3. Audio & Webcam
        cam = None
        mic = None
        spk = None
        for k, v in specs.items():
            kl = k.lower()
            vs = str(v).strip()
            if any(term in kl for term in ["camera", "webcam"]):
                m = re.search(r"\b(\d{3,4}\s*p|HD|FHD|QHD|\d+(?:\.\d+)?\s*(?:MP|M\b))\b", vs, re.I)
                if m:
                    cam = m.group(0)
            if any(term in kl for term in ["microphone", "mic"]):
                if not any(bad in vs.lower() for bad in ["none", "no ", "n/a"]):
                    mic = vs
            if any(term in kl for term in ["speaker", "audio"]):
                m_sp = re.search(r"(\d+)\s*(?:x\s*\d+(?:\.\d+)?\s*W|\s*speakers?)", vs, re.I)
                if m_sp:
                    spk = int(m_sp.group(1))
                elif re.search(r"\b(?:dual|stereo|two|2x)\b", vs, re.I):
                    spk = 2
                elif re.search(r"\b(?:quad|four|4x)\b", vs, re.I):
                    spk = 4

        if cam: stats["webcam"] += 1
        if mic: stats["mic"] += 1
        if spk: stats["speakers"] += 1

        # 4. Build & Security
        fp_reader = None
        backlit = None
        pointing = None
        sec_feats = []

        for k, v in specs.items():
            kl = k.lower()
            vs = str(v).strip()
            if any(term in kl for term in ["fingerprint"]):
                if re.search(r"\b(?:no|none|n/a|without)\b", vs, re.I):
                    fp_reader = False
                elif re.search(r"\b(?:fingerprint|touch|yes)\b", vs, re.I):
                    fp_reader = True
            if any(term in kl for term in ["keyboard"]):
                if re.search(r"\b(?:backlit|backlight|rgb)\b", vs, re.I):
                    backlit = True
                elif re.search(r"\b(?:non-backlit|no backlight)\b", vs, re.I):
                    backlit = False
            if any(term in kl for term in ["touchpad", "pointing"]):
                pointing = vs
            if any(term in kl for term in ["security chip", "other security", "security"]):
                sec_feats.append(vs)

        if fp_reader is not None: stats["fingerprint"] += 1
        if backlit is not None or "backlit" in title.lower(): stats["backlit"] += 1
        if pointing: stats["pointing"] += 1
        if sec_feats: stats["security"] += 1

    print("\nExtraction Success Counts across all laptops:")
    for k, v in stats.items():
        print(f"  {k:15}: {v}/{len(files)} ({v/len(files)*100:.1f}%)")


if __name__ == "__main__":
    test_on_all_files()

