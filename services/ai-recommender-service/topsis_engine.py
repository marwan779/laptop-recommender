#!/usr/bin/env python3
"""
Production TOPSIS & Persona Recommendation Engine (topsis_engine.py)
--------------------------------------------------------------------
Designed for seamless Backend integration:
1. Pre-computes `persona_scores` (fit & value scores across 6 personas) into the catalog JSON/DB
   for instant zero-compute sorting on landing/category pages.
2. Provides `rank_laptops_topsis()` for dynamic, budget-scoped TOPSIS ranking in < 0.5 ms,
   including:
   - Implicit Persona Gates (with automatic graceful relaxation if budget is tight)
   - Smart 60% Budget Floor inside TOPSIS (prevents ultra-cheap laptops from distorting the price vector)
   - Bilingual (Arabic/English) Text Box Parser (extracts hard filters & dynamic weight boosts)
   - Explainable Recommendation Badges (`why_recommended_ar`, `why_recommended_en`)
"""
import json
import math
import re
import sys
import copy
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

# =============================================================================
# 1. PERSONA WEIGHT CONFIGURATIONS (Sum of weights = 1.00 for each persona)
# =============================================================================
# The 10 TOPSIS columns in order:
# [0] cpu_score           (Benefit +)
# [1] gpu_score           (Benefit +)
# [2] power_therm_score   (Benefit +)
# [3] display_score       (Benefit +)
# [4] mobility_score      (Benefit +)
# [5] longevity_score     (Benefit +)
# [6] ergonomics_score    (Benefit +)
# [7] connectivity_score  (Benefit +)
# [8] community_nlp_score (Benefit +)
# [9] effective_price_egp (Cost    -)

TOPSIS_CRITERIA_KEYS: List[str] = [
    "cpu_score",
    "gpu_score",
    "power_therm_score",
    "display_score",
    "mobility_score",
    "longevity_score",
    "ergonomics_score",
    "connectivity_score",
    "community_nlp_score",
    "effective_price_egp",
]

# True = Benefit (higher is better), False = Cost (lower is better)
IS_BENEFIT_CRITERION: List[bool] = [
    True,   # cpu_score
    True,   # gpu_score
    True,   # power_therm_score
    True,   # display_score
    True,   # mobility_score
    True,   # longevity_score
    True,   # ergonomics_score
    True,   # connectivity_score
    True,   # community_nlp_score
    False,  # effective_price_egp (Cost criterion: cheaper within the budget window is better)
]

PERSONA_CONFIGS: Dict[str, Dict[str, Any]] = {
    "gaming": {
        "label_ar": "الألعاب الثقيلة والـ Esports",
        "label_en": "Heavy Gaming & Esports",
        "weights": {
            "cpu_score": 0.16,
            "gpu_score": 0.32,
            "power_therm_score": 0.14,
            "display_score": 0.14,
            "mobility_score": 0.03,
            "longevity_score": 0.06,
            "ergonomics_score": 0.02,
            "connectivity_score": 0.03,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_refresh_hz": 120,
            "min_ram_gb": 8,
        },
    },
    "ai_and_game_dev": {
        "label_ar": "الذكاء الاصطناعي وتطوير الألعاب والـ 3D",
        "label_en": "AI / ML, Game Dev & 3D Rendering",
        "weights": {
            "cpu_score": 0.20,
            "gpu_score": 0.28,
            "power_therm_score": 0.12,
            "display_score": 0.10,
            "mobility_score": 0.03,
            "longevity_score": 0.10,
            "ergonomics_score": 0.03,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_ram_gb": 16,
            "min_vram_gb": 6,
        },
    },
    "programming": {
        "label_ar": "البرمجة وهندسة البرمجيات",
        "label_en": "Programming & Software Engineering",
        "weights": {
            "cpu_score": 0.26,
            "gpu_score": 0.04,
            "power_therm_score": 0.08,
            "display_score": 0.10,
            "mobility_score": 0.12,
            "longevity_score": 0.14,
            "ergonomics_score": 0.08,
            "connectivity_score": 0.08,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "min_cpu_cores": 6,
        },
    },
    "content_creation": {
        "label_ar": "المونتاج والتصميم الجرافيكي وصناعة المحتوى",
        "label_en": "Video Editing, Design & Content Creation",
        "weights": {
            "cpu_score": 0.20,
            "gpu_score": 0.22,
            "power_therm_score": 0.08,
            "display_score": 0.24,
            "mobility_score": 0.03,
            "longevity_score": 0.05,
            "ergonomics_score": 0.03,
            "connectivity_score": 0.05,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "require_creator_display": True,  # 100% sRGB, DCI-P3, or OLED
        },
    },
    "student_and_office": {
        "label_ar": "الدراسة والجامعة والعمل المكتبي",
        "label_en": "Student, University & Office Work",
        "weights": {
            "cpu_score": 0.20,
            "gpu_score": 0.03,
            "power_therm_score": 0.05,
            "display_score": 0.10,
            "mobility_score": 0.28,
            "longevity_score": 0.08,
            "ergonomics_score": 0.12,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 2.35,
        },
    },
    "business_and_mobility": {
        "label_ar": "البيزنس والتنقل المستمر والاجتماعات",
        "label_en": "Executive Business & Ultraportable Mobility",
        "weights": {
            "cpu_score": 0.16,
            "gpu_score": 0.03,
            "power_therm_score": 0.05,
            "display_score": 0.12,
            "mobility_score": 0.28,
            "longevity_score": 0.05,
            "ergonomics_score": 0.14,
            "connectivity_score": 0.07,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 1.90,
        },
    },
    "balanced": {
        "label_ar": "استخدام شامل متوازن (أفضل قيمة)",
        "label_en": "Balanced All-Rounder",
        "weights": {
            "cpu_score": 0.20,
            "gpu_score": 0.18,
            "power_therm_score": 0.08,
            "display_score": 0.15,
            "mobility_score": 0.10,
            "longevity_score": 0.09,
            "ergonomics_score": 0.06,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
        },
    },
}


# =============================================================================
# 2. BILINGUAL (AR/EN) TEXT PROMPT PARSER (Extracts Filters + Weight Boosts)
# =============================================================================
def parse_user_text_prompt(prompt: Optional[str]) -> Dict[str, Any]:
    """
    Lightweight, zero-latency bilingual parser that turns optional user text into:
      1. `extracted_filters`: hard constraints if explicitly mentioned (e.g. '32GB RAM', '1TB', 'OLED')
      2. `weight_boosts`: additive boosts to TOPSIS criteria weights based on user intent keywords.
    """
    if not prompt or not str(prompt).strip():
        return {"extracted_filters": {}, "weight_boosts": {}}

    txt = str(prompt).lower()
    extracted_filters: Dict[str, Any] = {}
    weight_boosts: Dict[str, float] = {}

    # --- A. Extract Explicit Hardware Constraints from Text ---
    if re.search(r"(64\s*gb|64\s*جيجا)", txt):
        extracted_filters["min_ram_gb"] = 64
    elif re.search(r"(32\s*gb|32\s*جيجا)", txt):
        extracted_filters["min_ram_gb"] = 32
    elif re.search(r"(24\s*gb|24\s*جيجا)", txt):
        extracted_filters["min_ram_gb"] = 24
    elif re.search(r"(16\s*gb|16\s*جيجا)", txt):
        extracted_filters["min_ram_gb"] = 16

    if re.search(r"(2\s*tb|2000\s*gb|2\s*تيرا)", txt):
        extracted_filters["min_storage_gb"] = 2048
    elif re.search(r"(1\s*tb|1000\s*gb|1024\s*gb|تيرا|1\s*تيرا)", txt):
        extracted_filters["min_storage_gb"] = 1024

    if any(k in txt for k in ["oled", "اوليد", "أوليد"]):
        extracted_filters["require_oled"] = True
    if any(k in txt for k in ["touch", "تاتش", "لمس", "x360", "flip", "2-in-1"]):
        extracted_filters["require_touchscreen"] = True

    # --- B. Extract Dynamic Weight Boosts from Intent Keywords ---
    # 1. Mobility / Battery / Lightweight
    if any(k in txt for k in ["بطاريه", "بطارية", "خفيف", "تنقل", "سفر", "مواصلات", "محاضرات", "battery", "lightweight", "portable", "travel", "thin"]):
        weight_boosts["mobility_score"] = weight_boosts.get("mobility_score", 0.0) + 0.15

    # 2. Display / Colors / Screen / OLED
    if any(k in txt for k in ["شاشه", "شاشة", "الوان", "ألوان", "دقة", "سطوع", "مونتاج", "جرافيك", "display", "screen", "color", "srgb", "oled", "hdr"]):
        weight_boosts["display_score"] = weight_boosts.get("display_score", 0.0) + 0.14

    # 3. GPU / Gaming / Graphics / Rendering
    if any(k in txt for k in ["كارت شاشه", "كارت شاشة", "العاب", "ألعاب", "فريمات", "رندر", "جيمز", "gaming", "fps", "rtx", "gpu", "render", "3d"]):
        weight_boosts["gpu_score"] = weight_boosts.get("gpu_score", 0.0) + 0.15
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.06

    # 4. CPU / Multitasking / Heavy Coding / VMs
    if any(k in txt for k in ["معالج", "بروسيسور", "برمجه", "برمجة", "محاكاة", "داتا", "كود", "cpu", "processor", "coding", "docker", "vm", "multitask"]):
        weight_boosts["cpu_score"] = weight_boosts.get("cpu_score", 0.0) + 0.14

    # 5. Cooling / Thermals / Power
    if any(k in txt for k in ["تبريد", "حراره", "حرارة", "مراوح", "سخونة", "باور", "cooling", "thermal", "heat", "tgp", "watt"]):
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.14

    # 6. Upgradeability / Longevity / Future-proof
    if any(k in txt for k in ["تطوير", "ترقيه", "ترقية", "يعيش", "مستقبل", "رامات بتزيد", "upgrade", "future", "slots", "longevity", "expand"]):
        weight_boosts["longevity_score"] = weight_boosts.get("longevity_score", 0.0) + 0.14

    # 7. Keyboard / Webcam / Audio / Meetings
    if any(k in txt for k in ["كيبورد", "كاميرا", "صوت", "اجتماعات", "زووم", "بصمه", "بصمة", "keyboard", "webcam", "camera", "mic", "audio", "zoom"]):
        weight_boosts["ergonomics_score"] = weight_boosts.get("ergonomics_score", 0.0) + 0.12

    # 8. Ports / Thunderbolt / Type-C / LAN
    if any(k in txt for k in ["منافذ", "تايب سي", "ثندربولت", "لان", "شاشات خارجية", "ports", "thunderbolt", "usb-c", "hdmi", "ethernet", "lan"]):
        weight_boosts["connectivity_score"] = weight_boosts.get("connectivity_score", 0.0) + 0.12

    # 9. Budget / Cheapest / Value
    if any(k in txt for k in ["ارخص", "أرخص", "توفير", "سعر", "اقتصادي", "على قد الايد", "cheap", "budget", "value", "save", "affordable"]):
        weight_boosts["effective_price_egp"] = weight_boosts.get("effective_price_egp", 0.0) + 0.14

    return {
        "extracted_filters": extracted_filters,
        "weight_boosts": weight_boosts,
    }


# =============================================================================
# 3. HELPER FOR BACKEND DB QUERY GENERATION
# =============================================================================
def get_persona_db_query_spec(persona: str, max_budget_egp: float) -> Dict[str, Any]:
    """
    Returns the exact baseline filter dictionary that the Backend can translate into
    SQL WHERE / MongoDB find() clauses if desired.
    Note: Even if the Backend only queries by `min_price_egp <= max_budget_egp`,
    `rank_laptops_topsis()` automatically enforces these gates in-memory with smart fallback!
    """
    p_key = persona if persona in PERSONA_CONFIGS else "balanced"
    gates = copy.deepcopy(PERSONA_CONFIGS[p_key]["implicit_gates"])
    # If budget is under 35,000 EGP, relax 16GB RAM gate to 8GB and dGPU gate automatically
    if max_budget_egp < 35000:
        if gates.get("min_ram_gb", 8) > 8:
            gates["min_ram_gb"] = 8
        if max_budget_egp < 30000 and gates.get("require_dgpu"):
            gates["require_dgpu"] = False
            gates.pop("min_refresh_hz", None)
            gates.pop("min_vram_gb", None)

    return {
        "in_stock_active": True,
        "max_price_egp": max_budget_egp,
        "persona_gates": gates,
    }


# =============================================================================
# 4. CORE VECTOR-NORMALIZED TOPSIS MATHEMATICAL ENGINE
# =============================================================================
def _run_topsis_vector(
    decision_matrix: np.ndarray,
    weights_vec: np.ndarray,
    is_benefit_vec: List[bool],
) -> np.ndarray:
    """
    Executes standard Vector-Normalized TOPSIS on an (M x N) NumPy matrix.
    Returns an array of Closeness Scores scaled [0.0, 100.0] for the M laptops.
    """
    m_rows, n_cols = decision_matrix.shape
    if m_rows == 0:
        return np.array([], dtype=float)
    if m_rows == 1:
        return np.array([100.0], dtype=float)

    # Step 1: Vector Normalization r_ij = x_ij / sqrt(sum(x_ij^2))
    col_norms = np.linalg.norm(decision_matrix, axis=0)
    col_norms[col_norms == 0.0] = 1.0
    r_mat = decision_matrix / col_norms

    # Step 2: Weighted Normalized Matrix v_ij = w_j * r_ij
    w_norm = weights_vec / np.sum(weights_vec)
    v_mat = r_mat * w_norm

    # Step 3: Ideal Best (A+) and Ideal Worst (A-)
    ideal_best = np.zeros(n_cols, dtype=float)
    ideal_worst = np.zeros(n_cols, dtype=float)
    for j in range(n_cols):
        if is_benefit_vec[j]:
            ideal_best[j] = np.max(v_mat[:, j])
            ideal_worst[j] = np.min(v_mat[:, j])
        else:
            # Cost criterion (Price): lower is better
            ideal_best[j] = np.min(v_mat[:, j])
            ideal_worst[j] = np.max(v_mat[:, j])

    # Step 4: Euclidean Distances D+ and D-
    d_pos = np.linalg.norm(v_mat - ideal_best, axis=1)
    d_neg = np.linalg.norm(v_mat - ideal_worst, axis=1)

    # Step 5: Relative Closeness C_i = D- / (D+ + D-) * 100
    denom = d_pos + d_neg
    closeness = np.where(denom > 1e-12, (d_neg / denom) * 100.0, 50.0)
    return np.round(closeness, 2)


# =============================================================================
# 5. EXPLAINABLE RECOMMENDATION REASONS GENERATOR (AR & EN)
# =============================================================================
def _build_why_recommended(laptop: Dict[str, Any], persona: str) -> Dict[str, List[str]]:
    s = laptop["specs"]
    dm = laptop["derived_metrics"]
    reasons_ar: List[str] = []
    reasons_en: List[str] = []

    cpu_name = s["cpu"].get("full_name") or s["cpu"].get("model")
    cores = s["cpu"].get("cores")
    boost = s["cpu"].get("clock_boost_ghz")
    gpu_model = s["gpu"].get("model")
    is_igpu = s["gpu"].get("integrated")
    tgp = dm["silicon"].get("inferred_tgp_w")
    vram = s["gpu"].get("vram_gb")
    ram_gb = s["memory"].get("capacity_gb")
    mem_type = s["memory"].get("memory_type")
    ssd_gb = s["storage"].get("capacity_gb")
    ssd_str = f"{ssd_gb // 1024}TB" if (ssd_gb and ssd_gb >= 1024) else f"{ssd_gb}GB"

    if not is_igpu and gpu_model:
        reasons_ar.append(f"كارت شاشة {gpu_model} ({vram}GB) بقدرة {int(tgp)}W ومعالج {cpu_name}")
        reasons_en.append(f"{gpu_model} ({vram}GB, {int(tgp)}W TGP) paired with {cpu_name}")
    else:
        reasons_ar.append(f"معالج {cpu_name} ({cores} أنوية حتى {boost}GHz) مع رام {ram_gb}GB {mem_type}")
        reasons_en.append(f"{cpu_name} ({cores}C, up to {boost}GHz) with {ram_gb}GB {mem_type} RAM")

    # Display highlight
    disp_size = s["display"].get("size_inches")
    panel = dm["display"].get("panel_technology")
    hz = dm["display"].get("refresh_rate_hz")
    gamut = dm["display"].get("color_gamut_tier", "").split(" (")[0]
    reasons_ar.append(f"شاشة {disp_size} بوصة {panel} بتردد {hz}Hz وتغطية ألوان {gamut}")
    reasons_en.append(f"{disp_size}-inch {panel} {hz}Hz display ({gamut})")

    # Persona-specific 3rd highlight
    if persona in ["student_and_office", "business_and_mobility"]:
        w_kg = dm["mobility"].get("weight_kg")
        b_hrs = dm["mobility"].get("battery_hours_estimate")
        reasons_ar.append(f"وزن خفيف {w_kg} كجم وبطارية تدوم حوالي {b_hrs} ساعات مع تخزين {ssd_str} SSD")
        reasons_en.append(f"Lightweight {w_kg} kg chassis with ~{b_hrs}h battery life & {ssd_str} SSD")
    else:
        m2_slots = dm["longevity"].get("total_m2_slots")
        max_r = dm["longevity"].get("max_ram_gb")
        reasons_ar.append(f"رام {ram_gb}GB {mem_type} (تقبل حتى {max_r}GB) وتخزين {ssd_str} ({m2_slots} فتحات M.2)")
        reasons_en.append(f"{ram_gb}GB {mem_type} RAM (up to {max_r}GB) & {ssd_str} SSD ({m2_slots}x M.2 slots)")

    # Store & Price spread highlight
    price = dm["topsis_inputs"].get("effective_price_egp")
    store = laptop.get("cheapest_store")
    spread = laptop.get("price_spread_egp") or 0
    if spread >= 1000:
        reasons_ar.append(f"أفضل سعر متاح لدى {store} ({price:,.0f} ج.م) بتوفير {spread:,.0f} ج.م عن أعلى متجر")
        reasons_en.append(f"Best price at {store} ({price:,.0f} EGP), saving {spread:,.0f} EGP across stores")
    elif price:
        reasons_ar.append(f"متاح بسعر {price:,.0f} ج.م لدى {store}")
        reasons_en.append(f"Available at {price:,.0f} EGP via {store}")

    return {"ar": reasons_ar, "en": reasons_en}


# =============================================================================
# 6. MAIN DYNAMIC TOPSIS API ENDPOINT FUNCTION FOR BACKEND
# =============================================================================
def rank_laptops_topsis(
    laptops: List[Dict[str, Any]],
    max_budget_egp: float = 300000.0,
    min_budget_egp: Optional[float] = None,
    persona: str = "balanced",
    user_text_prompt: Optional[str] = None,
    min_ram_gb: Optional[int] = None,
    min_storage_gb: Optional[int] = None,
    require_dgpu: Optional[bool] = None,
    brand_filter: Optional[List[str]] = None,
    custom_weights: Optional[Dict[str, float]] = None,
    apply_smart_60pct_floor: bool = True,
    min_floor_candidates: int = 5,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Main entry point for Backend `POST /recommend`.
    Accepts either the full 295-laptop catalog OR a pre-queried subset of laptops (`price <= max_budget_egp`),
    applies Implicit Persona Gates + Smart 60% Budget Floor + Text Prompt Weight Modifiers,
    and returns the Top-K ranked laptops with match percentages and explanations in < 0.5 ms.
    """
    p_key = persona if persona in PERSONA_CONFIGS else "balanced"
    p_cfg = PERSONA_CONFIGS[p_key]

    # 1. Parse optional text prompt
    parsed_prompt = parse_user_text_prompt(user_text_prompt)
    ext_filters = parsed_prompt["extracted_filters"]
    w_boosts = parsed_prompt["weight_boosts"]

    # 2. Merge weights: Base Persona -> Community NLP baseline -> Custom Weights -> Text Prompt Boosts
    final_weights_dict = copy.deepcopy(p_cfg["weights"])
    final_weights_dict.setdefault("community_nlp_score", 0.08)
    if custom_weights:
        for k, v in custom_weights.items():
            if k in final_weights_dict and v is not None:
                final_weights_dict[k] = float(v)
    for k, boost in w_boosts.items():
        if k in final_weights_dict:
            final_weights_dict[k] += boost

    # Normalize weights to sum to 1.00
    w_sum = sum(final_weights_dict.values()) or 1.0
    final_weights_dict = {k: round(v / w_sum, 4) for k, v in final_weights_dict.items()}
    weights_vec = np.array([final_weights_dict[k] for k in TOPSIS_CRITERIA_KEYS], dtype=float)

    # 3. Base Hard Filter: Active in-stock + within max_budget_egp + explicit user filters
    eff_min_ram = min_ram_gb or ext_filters.get("min_ram_gb")
    eff_min_sto = min_storage_gb or ext_filters.get("min_storage_gb")
    brands_norm = {b.lower() for b in brand_filter} if brand_filter else None

    base_pool: List[Dict[str, Any]] = []
    for lap in laptops:
        ti = lap.get("derived_metrics", {}).get("topsis_inputs", {})
        if not ti.get("in_stock_active", False):
            continue
        price = ti.get("effective_price_egp")
        if price is None or price > max_budget_egp:
            continue
        if min_budget_egp is not None and price < min_budget_egp:
            continue
        if brands_norm and str(lap.get("brand") or "").lower() not in brands_norm:
            continue
        if eff_min_ram and (lap["specs"]["memory"].get("capacity_gb") or 0) < eff_min_ram:
            continue
        if eff_min_sto and (lap["specs"]["storage"].get("capacity_gb") or 0) < eff_min_sto:
            continue
        if require_dgpu is True and lap["specs"]["gpu"].get("integrated", True):
            continue
        if ext_filters.get("require_oled") and "OLED" not in str(lap["specs"]["display"].get("panel_type") or "").upper():
            continue
        if ext_filters.get("require_touchscreen") and not lap["specs"]["display"].get("touchscreen"):
            continue
        base_pool.append(lap)

    # 4. Apply Implicit Persona Gates (with graceful fallback if budget is too low to satisfy all gates)
    gates = p_cfg["implicit_gates"]
    persona_pool: List[Dict[str, Any]] = []
    for lap in base_pool:
        s = lap["specs"]
        dm = lap["derived_metrics"]
        if gates.get("require_dgpu") and s["gpu"].get("integrated", True):
            continue
        if gates.get("min_vram_gb") and (s["gpu"].get("vram_gb") or 0) < gates["min_vram_gb"]:
            continue
        if gates.get("min_refresh_hz") and (s["display"].get("refresh_rate_hz") or 60) < gates["min_refresh_hz"]:
            continue
        if gates.get("min_ram_gb") and (s["memory"].get("capacity_gb") or 0) < gates["min_ram_gb"]:
            continue
        if gates.get("min_cpu_cores") and (s["cpu"].get("cores") or 0) < gates["min_cpu_cores"]:
            continue
        if gates.get("require_creator_display"):
            gtier = dm["display"].get("color_gamut_tier", "").lower()
            if "100% srgb" not in gtier and "dci-p3" not in gtier:
                continue
        if gates.get("max_weight_kg") and dm["mobility"].get("weight_kg", 2.0) > gates["max_weight_kg"]:
            continue
        persona_pool.append(lap)

    # Graceful relaxation if strict persona gates left fewer than 3 laptops (e.g. low budget)
    gates_relaxed = False
    if len(persona_pool) < 3 and len(base_pool) >= 3:
        persona_pool = base_pool
        gates_relaxed = True

    # 5. Smart 60% Budget Floor inside TOPSIS (Backend Engineer's design)
    applied_floor_egp = min_budget_egp if min_budget_egp is not None else 0.0
    scoped_pool = persona_pool
    if min_budget_egp is None and apply_smart_60pct_floor and len(persona_pool) > min_floor_candidates:
        floor_60 = round(max_budget_egp * 0.60, 0)
        pool_60 = [
            l for l in persona_pool
            if l["derived_metrics"]["topsis_inputs"]["effective_price_egp"] >= floor_60
        ]
        if len(pool_60) >= min_floor_candidates:
            scoped_pool = pool_60
            applied_floor_egp = floor_60
        else:
            floor_45 = round(max_budget_egp * 0.45, 0)
            pool_45 = [
                l for l in persona_pool
                if l["derived_metrics"]["topsis_inputs"]["effective_price_egp"] >= floor_45
            ]
            if len(pool_45) >= min_floor_candidates:
                scoped_pool = pool_45
                applied_floor_egp = floor_45

    if not scoped_pool:
        return {
            "persona": p_key,
            "persona_label_ar": p_cfg["label_ar"],
            "total_candidates_before_floor": len(base_pool),
            "total_candidates_after_gates_and_floor": 0,
            "applied_budget_window_egp": [applied_floor_egp, max_budget_egp],
            "effective_weights": final_weights_dict,
            "results": [],
        }

    # 6. Build Decision Matrix (M x 9) and Run Vector TOPSIS
    mat = np.array(
        [[l["derived_metrics"]["topsis_inputs"][k] for k in TOPSIS_CRITERIA_KEYS] for l in scoped_pool],
        dtype=float,
    )
    scores = _run_topsis_vector(mat, weights_vec, IS_BENEFIT_CRITERION)

    # 7. Sort & Format Top-K Output
    ranked_indices = np.argsort(-scores)[:top_k]
    results = []
    for rank_idx, idx in enumerate(ranked_indices, start=1):
        lap = scoped_pool[int(idx)]
        score_val = float(scores[int(idx)])
        ti = lap["derived_metrics"]["topsis_inputs"]
        why = _build_why_recommended(lap, p_key)
        results.append({
            "rank": rank_idx,
            "canonical_id": lap["canonical_id"],
            "brand": lap.get("brand"),
            "laptop_family": lap.get("laptop_family"),
            "laptop_model": lap.get("laptop_model"),
            "title": lap.get("title"),
            "thumbnail_url": lap.get("thumbnail_url"),
            "topsis_match_score": score_val,
            "effective_price_egp": ti["effective_price_egp"],
            "cheapest_store": lap.get("cheapest_store"),
            "available_stores": lap.get("available_stores"),
            "prices_by_store": lap.get("prices_by_store"),
            "why_recommended_ar": why["ar"],
            "why_recommended_en": why["en"],
            "topsis_inputs": ti,
        })

    return {
        "persona": p_key,
        "persona_label_ar": p_cfg["label_ar"],
        "persona_label_en": p_cfg["label_en"],
        "gates_relaxed_for_low_budget": gates_relaxed,
        "total_candidates_before_floor": len(base_pool),
        "total_candidates_after_gates_and_floor": len(scoped_pool),
        "applied_budget_window_egp": [applied_floor_egp, max_budget_egp],
        "parsed_text_prompt": parsed_prompt,
        "effective_weights": final_weights_dict,
        "results": results,
    }


# =============================================================================
# 7. PRE-COMPUTE STATIC PERSONA SCORES INTO CATALOG JSON FOR LANDING/DB PAGES
# =============================================================================
def enrich_catalog_with_persona_scores(input_path: str, output_path: str) -> Dict[str, Any]:
    """
    Computes and attaches `derived_metrics.persona_scores` for all 295 laptops:
    - `hardware_fit`: 0-100 TOPSIS score using only the 8 hardware benefit metrics (price-independent)
    - `value_fit`: 0-100 TOPSIS score combining the 8 hardware metrics + `value_score`
    This allows the Backend to do simple `ORDER BY derived_metrics.persona_scores.gaming.value_fit DESC`
    on general catalog browse pages without running any code!
    """
    with open(input_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    laptops = catalog["laptops"]
    hw_keys = TOPSIS_CRITERIA_KEYS[:9]  # The 9 benefit criteria (8 hardware + community_nlp_score)
    hw_mat = np.array(
        [[l["derived_metrics"]["topsis_inputs"][k] for k in hw_keys] for l in laptops],
        dtype=float,
    )
    val_col = np.array(
        [[l["derived_metrics"]["topsis_inputs"]["value_score"]] for l in laptops],
        dtype=float,
    )
    hw_plus_val_mat = np.hstack([hw_mat, val_col])

    for p_key, p_cfg in PERSONA_CONFIGS.items():
        w_hw = np.array([p_cfg["weights"].get(k, 0.08) for k in hw_keys], dtype=float)
        w_val = np.array([p_cfg["weights"].get(k, 0.08) for k in hw_keys] + [p_cfg["weights"]["effective_price_egp"] * 1.5], dtype=float)

        hw_scores = _run_topsis_vector(hw_mat, w_hw, [True] * 9)
        val_scores = _run_topsis_vector(hw_plus_val_mat, w_val, [True] * 10)

        for i, lap in enumerate(laptops):
            ps = lap["derived_metrics"].setdefault("persona_scores", {})
            ps[p_key] = {
                "hardware_fit": float(hw_scores[i]),
                "value_fit": float(val_scores[i]),
            }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    return catalog


if __name__ == "__main__":
    in_p = sys.argv[1] if len(sys.argv) > 1 else "unified_catalog_with_metrics_v6.json"
    out_p = sys.argv[2] if len(sys.argv) > 2 else "unified_catalog_topsis_ready_v6.json"
    cat_out = enrich_catalog_with_persona_scores(in_p, out_p)
    print(f"Enriched {len(cat_out['laptops'])} laptops with pre-computed persona_scores -> {out_p}")
