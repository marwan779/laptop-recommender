"""Pure physical-aspect recalibration rules (no I/O, no model or DB access)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_BASELINE_ASPECT_RE = re.compile(
    r"Thermals:\s*([\d.]+)/100,\s*Fan Noise/Acoustics:\s*([\d.]+)/100,\s*"
    r"Chassis Build & Hinges:\s*([\d.]+)/100,\s*Keyboard & Trackpad:\s*([\d.]+)/100,\s*"
    r"Real Battery & Reliability:\s*([\d.]+)/100"
)


def _extract_baseline_aspects(prof: Dict[str, Any], fallback_aspects: Dict[str, Any]) -> Dict[str, float]:
    synth_en = str(prof.get("synthesized_review_en") or "")
    m = _BASELINE_ASPECT_RE.search(synth_en)
    if m:
        return {
            "thermals_score": float(m.group(1)),
            "acoustics_score": float(m.group(2)),
            "build_and_hinges_score": float(m.group(3)),
            "keyboard_and_trackpad_score": float(m.group(4)),
            "real_battery_and_reliability_score": float(m.group(5)),
        }
    return {
        "thermals_score": float(fallback_aspects.get("thermals_score", 78.0)),
        "acoustics_score": float(fallback_aspects.get("acoustics_score", 78.0)),
        "build_and_hinges_score": float(fallback_aspects.get("build_and_hinges_score", 78.0)),
        "keyboard_and_trackpad_score": float(fallback_aspects.get("keyboard_and_trackpad_score", 78.0)),
        "real_battery_and_reliability_score": float(fallback_aspects.get("real_battery_and_reliability_score", 78.0)),
    }


def _recalibrate_item(
    ident: Dict[str, Any],
    cids: List[str],
    primary_cid: Optional[str],
    base_aspects: Dict[str, float],
    cat_map: Dict[str, Any],
) -> Dict[str, Any]:
    primary_lap = cat_map.get(primary_cid) if primary_cid else None
    if not primary_lap:
        for mcid in cids:
            if mcid in cat_map:
                primary_lap = cat_map[mcid]
                break

    fam_low = (
        str(ident.get("brand", "")) + " " +
        str(ident.get("laptop_family", "")) + " " +
        str(ident.get("laptop_model", ""))
    ).lower()

    if primary_lap:
        s = primary_lap["specs"]
        dm = primary_lap["derived_metrics"]
        is_igpu = s["gpu"].get("integrated", True)
        tgp_w = float(dm["silicon"].get("inferred_tgp_w") or 0.0)
        cpu_w = float(s["cpu"].get("base_power_w") or 28.0)
        batt_hrs = float(dm["mobility"].get("battery_hours_estimate") or 5.0)
        chassis_tier = str(dm["longevity"].get("chassis_tier") or "")
    else:
        is_igpu = True
        tgp_w = 0.0
        cpu_w = 28.0
        batt_hrs = 5.5
        chassis_tier = ""

    # 1. Stretch baseline scores away from the 75.0 Bayesian center (1.25x avoids 96/42 saturation)
    def stretch(val: float, lo: float = 42.0, hi: float = 96.0) -> float:
        stretched = 75.0 + (float(val) - 75.0) * 1.25
        return round(max(lo, min(hi, stretched)), 1)

    therm = stretch(base_aspects.get("thermals_score", 78.0))
    acoust = stretch(base_aspects.get("acoustics_score", 78.0))
    build = stretch(base_aspects.get("build_and_hinges_score", 78.0))
    kb = stretch(base_aspects.get("keyboard_and_trackpad_score", 78.0))

    # 2. Differentiate Build & Hinges by actual chassis material & convertible/budget class
    if "Metal" in chassis_tier or any(k in fam_low for k in ["prestige", "zenbook", "proart", "zephyrus", "legion pro", "strix scar", "omnibook", "yoga", "thinkpad", "latitude"]):
        build = max(build, 84.5 if "omnibook" in fam_low or "latitude" in fam_low else 89.0)
    elif any(k in fam_low for k in ["flex", "victus", "15-fd", "15-fc", "255 g", "250 g", "aspire", "modern", "ideapad 1", "ideapad 3"]):
        build = min(build, 71.5)

    # 3. Anchor Real Battery Run-Time to actual estimated battery endurance & HX/dGPU power draw
    raw_batt_score = 38.0 + (batt_hrs - 2.5) * 7.2
    if not is_igpu and (cpu_w >= 55.0 or tgp_w >= 115.0):
        raw_batt_score = min(raw_batt_score, 61.5)
        acoust = min(acoust, 72.5)
    elif is_igpu and batt_hrs >= 7.0:
        raw_batt_score = max(raw_batt_score, 86.5)

    batt = round(max(45.0, min(95.0, raw_batt_score)), 1)
    updated_aspects = {
        "thermals_score": therm,
        "acoustics_score": acoust,
        "build_and_hinges_score": build,
        "keyboard_and_trackpad_score": kb,
        "real_battery_and_reliability_score": batt,
    }
    comm_score = round(0.30 * therm + 0.15 * acoust + 0.25 * build + 0.15 * kb + 0.15 * batt, 2)
    return {"community_nlp_score": comm_score, "aspect_scores": updated_aspects}
