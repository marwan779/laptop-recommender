"""Pure TOPSIS, persona weighting, bilingual prompt parsing, and semantic scoring domain logic.

Zero external I/O, database, HTTP framework, or model loading dependencies.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

import numpy as np

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

# Reference bilingual anchor descriptions for Semantic Weight Boosting
CRITERIA_SEMANTIC_ANCHORS: Dict[str, str] = {
    "cpu_score": "معالج قوي بروسيسور سريع للبرمجة والملتي تاسكينج والمحاكاة والداتا fast CPU processor heavy coding multitasking virtualization",
    "gpu_score": "كارت شاشة قوي للألعاب الثقيلة وفريمات عالية وريندر وجرافيك 3D powerful gaming GPU high FPS RTX rendering",
    "power_therm_score": "تبريد ممتاز ميسخنش في الصيف مراوح قوية باور عالي بدون اختناق حراري excellent cooling thermals runs cool no thermal throttling full TGP",
    "display_score": "شاشة اوليد ألوان دقيقة مونتاج وتصميم سطوع عالي 100% sRGB OLED display screen accurate colors brightness",
    "mobility_score": "بطارية تقعد وقت طويل وزن خفيف للتنقل والسفر والجامعة والمحاضرات long battery life lightweight portable thin travel",
    "longevity_score": "قابل للتطوير وزيادة الرامات والهارد ومفصلات وشاسيه متين يعيش للمستقبل upgradeable RAM SSD slots durable metal chassis sturdy hinges",
    "ergonomics_score": "كيبورد مريحة في الكتابة كاميرا نقية للاجتماعات وصوت عالي وبصمة comfortable backlit keyboard good webcam microphone speakers fingerprint",
    "connectivity_score": "منافذ كتير تايب سي ثندربولت وكابل نت وشاشات خارجية thunderbolt USB-C PD HDMI ethernet LAN ports",
}

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


def parse_user_text_prompt(prompt: Optional[str]) -> Dict[str, Any]:
    """Turn optional Arabic/English user text into hard constraints and criteria weight boosts."""
    if not prompt or not str(prompt).strip():
        return {"extracted_filters": {}, "weight_boosts": {}}

    txt = str(prompt).lower()
    extracted_filters: Dict[str, Any] = {}
    weight_boosts: Dict[str, float] = {}

    if re.search(r" (64\s*gb|64\s*جيجا) ", txt):
        extracted_filters["min_ram_gb"] = 64
    elif re.search(r" (32\s*gb|32\s*جيجا) ", txt):
        extracted_filters["min_ram_gb"] = 32
    elif re.search(r" (24\s*gb|24\s*جيجا) ", txt):
        extracted_filters["min_ram_gb"] = 24
    elif re.search(r" (16\s*gb|16\s*جيجا) ", txt):
        extracted_filters["min_ram_gb"] = 16

    if re.search(r" (2\s*tb|2000\s*gb|2\s*تيرا) ", txt):
        extracted_filters["min_storage_gb"] = 2048
    elif re.search(r" (1\s*tb|1000\s*gb|1024\s*gb|تيرا|1\s*تيرا) ", txt):
        extracted_filters["min_storage_gb"] = 1024

    if any(k in txt for k in ["oled", "اوليد", "أوليد"]):
        extracted_filters["require_oled"] = True
    if any(k in txt for k in ["touch", "تاتش", "لمس", "x360", "flip", "2-in-1"]):
        extracted_filters["require_touchscreen"] = True

    if any(
        k in txt
        for k in [
            "بطاريه",
            "بطارية",
            "خفيف",
            "تنقل",
            "سفر",
            "مواصلات",
            "محاضرات",
            "battery",
            "lightweight",
            "portable",
            "travel",
            "thin",
        ]
    ):
        weight_boosts["mobility_score"] = weight_boosts.get("mobility_score", 0.0) + 0.15

    if any(
        k in txt
        for k in [
            "شاشه",
            "شاشة",
            "الوان",
            "ألوان",
            "دقة",
            "سطوع",
            "مونتاج",
            "جرافيك",
            "display",
            "screen",
            "color",
            "srgb",
            "oled",
            "hdr",
        ]
    ):
        weight_boosts["display_score"] = weight_boosts.get("display_score", 0.0) + 0.14

    if any(
        k in txt
        for k in [
            "كارت شاشه",
            "كارت شاشة",
            "العاب",
            "ألعاب",
            "فريمات",
            "رندر",
            "جيمز",
            "gaming",
            "fps",
            "rtx",
            "gpu",
            "render",
            "3d",
        ]
    ):
        weight_boosts["gpu_score"] = weight_boosts.get("gpu_score", 0.0) + 0.15
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.06

    if any(
        k in txt
        for k in [
            "معالج",
            "بروسيسور",
            "برمجه",
            "برمجة",
            "محاكاة",
            "داتا",
            "كود",
            "cpu",
            "processor",
            "coding",
            "docker",
            "vm",
            "multitask",
        ]
    ):
        weight_boosts["cpu_score"] = weight_boosts.get("cpu_score", 0.0) + 0.14

    if any(
        k in txt
        for k in [
            "تبريد",
            "حراره",
            "حرارة",
            "مراوح",
            "سخونة",
            "باور",
            "cooling",
            "thermal",
            "heat",
            "tgp",
            "watt",
        ]
    ):
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.14

    if any(
        k in txt
        for k in [
            "تطوير",
            "ترقيه",
            "ترقية",
            "يعيش",
            "مستقبل",
            "رامات بتزيد",
            "upgrade",
            "future",
            "slots",
            "longevity",
            "expand",
        ]
    ):
        weight_boosts["longevity_score"] = weight_boosts.get("longevity_score", 0.0) + 0.14

    if any(
        k in txt
        for k in [
            "كيبورد",
            "كاميرا",
            "صوت",
            "اجتماعات",
            "زووم",
            "بصمه",
            "بصمة",
            "keyboard",
            "webcam",
            "camera",
            "mic",
            "audio",
            "zoom",
        ]
    ):
        weight_boosts["ergonomics_score"] = weight_boosts.get("ergonomics_score", 0.0) + 0.12

    if any(
        k in txt
        for k in [
            "منافذ",
            "تايب سي",
            "ثندربولت",
            "لان",
            "شاشات خارجية",
            "ports",
            "thunderbolt",
            "usb-c",
            "hdmi",
            "ethernet",
            "lan",
        ]
    ):
        weight_boosts["connectivity_score"] = weight_boosts.get("connectivity_score", 0.0) + 0.12

    if any(
        k in txt
        for k in [
            "ارخص",
            "أرخص",
            "توفير",
            "سعر",
            "اقتصادي",
            "على قد الايد",
            "cheap",
            "budget",
            "value",
            "save",
            "affordable",
        ]
    ):
        weight_boosts["effective_price_egp"] = weight_boosts.get("effective_price_egp", 0.0) + 0.14

    return {
        "extracted_filters": extracted_filters,
        "weight_boosts": weight_boosts,
    }


def get_persona_db_query_spec(persona: str, max_budget_egp: float) -> Dict[str, Any]:
    """Return baseline filter spec with low-budget relaxation for backend queries."""
    p_key = persona if persona in PERSONA_CONFIGS else "balanced"
    gates = copy.deepcopy(PERSONA_CONFIGS[p_key]["implicit_gates"])
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


def _run_topsis_vector(
    decision_matrix: np.ndarray,
    weights_vec: np.ndarray,
    is_benefit_vec: List[bool],
) -> np.ndarray:
    """Execute standard Vector-Normalized TOPSIS on an (M x N) NumPy matrix."""
    m_rows, n_cols = decision_matrix.shape
    if m_rows == 0:
        return np.array([], dtype=float)
    if m_rows == 1:
        return np.array([100.0], dtype=float)

    col_norms = np.linalg.norm(decision_matrix, axis=0)
    col_norms[col_norms == 0.0] = 1.0
    r_mat = decision_matrix / col_norms

    w_norm = weights_vec / np.sum(weights_vec)
    v_mat = r_mat * w_norm

    ideal_best = np.zeros(n_cols, dtype=float)
    ideal_worst = np.zeros(n_cols, dtype=float)
    for j in range(n_cols):
        if is_benefit_vec[j]:
            ideal_best[j] = np.max(v_mat[:, j])
            ideal_worst[j] = np.min(v_mat[:, j])
        else:
            ideal_best[j] = np.min(v_mat[:, j])
            ideal_worst[j] = np.max(v_mat[:, j])

    d_pos = np.linalg.norm(v_mat - ideal_best, axis=1)
    d_neg = np.linalg.norm(v_mat - ideal_worst, axis=1)

    denom = d_pos + d_neg
    closeness = np.where(denom > 1e-12, (d_neg / denom) * 100.0, 50.0)
    return np.round(closeness, 2)


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

    disp_size = s["display"].get("size_inches")
    panel = dm["display"].get("panel_technology")
    hz = dm["display"].get("refresh_rate_hz")
    gamut = dm["display"].get("color_gamut_tier", "").split(" (")[0]
    reasons_ar.append(f"شاشة {disp_size} بوصة {panel} بتردد {hz}Hz وتغطية ألوان {gamut}")
    reasons_en.append(f"{disp_size}-inch {panel} {hz}Hz display ({gamut})")

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


def score_dual_review_vectors(
    pro_res: Optional[Dict[str, Any]],
    con_res: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute net Dual-Vector review similarity adjustment per canonical ID."""
    pro_sim: Dict[str, float] = {}
    base_scores: Dict[str, float] = {}
    cids_map: Dict[str, List[str]] = {}
    if pro_res and pro_res.get("metadatas") and pro_res.get("distances"):
        for meta, dist in zip(pro_res["metadatas"][0], pro_res["distances"][0]):
            ckey = meta["chassis_key"]
            pro_sim[ckey] = max(0.0, 1.0 - float(dist))
            base_scores[ckey] = float(meta.get("community_nlp_score", 75.0))
            cids_map[ckey] = [c for c in meta.get("matched_canonical_ids", "").split(",") if c]

    con_sim: Dict[str, float] = {}
    if con_res and con_res.get("metadatas") and con_res.get("distances"):
        for meta, dist in zip(con_res["metadatas"][0], con_res["distances"][0]):
            ckey = meta["chassis_key"]
            con_sim[ckey] = max(0.0, 1.0 - float(dist))

    adjusted_nlp_scores: Dict[str, float] = {}
    for ckey, base_s in base_scores.items():
        net_sim = pro_sim.get(ckey, 0.0) - 0.75 * con_sim.get(ckey, 0.0)
        adj = max(35.0, min(98.0, round(base_s + net_sim * 32.0, 2)))
        for cid in cids_map.get(ckey, []):
            adjusted_nlp_scores[cid] = adj
    return adjusted_nlp_scores


def compute_semantic_weight_boosts(
    anchor_keys: List[str],
    anchor_matrix: Optional[np.ndarray],
    query_vec: np.ndarray,
) -> Dict[str, float]:
    """Compute cosine-similarity TOPSIS criteria boosts against normalized semantic anchors."""
    semantic_boosts: Dict[str, float] = {}
    if anchor_matrix is None:
        return semantic_boosts
    sims = np.dot(anchor_matrix, query_vec)
    for idx, sim_val in enumerate(sims):
        if sim_val >= 0.48:
            key = anchor_keys[idx]
            semantic_boosts[key] = round(float((sim_val - 0.45) * 0.35), 3)
    return semantic_boosts


def build_budget_too_low_fallback(working_laptops: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    """Return cheapest in-stock alternatives when no laptop matches the requested budget window."""
    active_all = [
        l
        for l in working_laptops
        if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("in_stock_active")
    ]
    active_all.sort(
        key=lambda x: x["derived_metrics"]["topsis_inputs"].get("effective_price_egp") or 999999
    )
    return [
        {
            "canonical_id": l["canonical_id"],
            "title": l.get("title"),
            "effective_price_egp": l["derived_metrics"]["topsis_inputs"].get("effective_price_egp"),
            "cheapest_store": l.get("cheapest_store"),
        }
        for l in active_all[:limit]
    ]


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
    """Run budget-scoped 10-column TOPSIS ranking with implicit persona gates and smart fallback."""
    p_key = persona if persona in PERSONA_CONFIGS else "balanced"
    p_cfg = PERSONA_CONFIGS[p_key]

    parsed_prompt = parse_user_text_prompt(user_text_prompt)
    ext_filters = parsed_prompt["extracted_filters"]
    w_boosts = parsed_prompt["weight_boosts"]

    final_weights_dict = copy.deepcopy(p_cfg["weights"])
    final_weights_dict.setdefault("community_nlp_score", 0.08)
    if custom_weights:
        for k, v in custom_weights.items():
            if k in final_weights_dict and v is not None:
                final_weights_dict[k] = float(v)
    for k, boost in w_boosts.items():
        if k in final_weights_dict:
            final_weights_dict[k] += boost

    w_sum = sum(final_weights_dict.values()) or 1.0
    final_weights_dict = {k: round(v / w_sum, 4) for k, v in final_weights_dict.items()}
    weights_vec = np.array([final_weights_dict[k] for k in TOPSIS_CRITERIA_KEYS], dtype=float)

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

    gates_relaxed = False
    if len(persona_pool) < 3 and len(base_pool) >= 3:
        persona_pool = base_pool
        gates_relaxed = True

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
            "persona_label_en": p_cfg["label_en"],
            "gates_relaxed_for_low_budget": gates_relaxed,
            "total_candidates_before_floor": len(base_pool),
            "total_candidates_after_gates_and_floor": 0,
            "applied_budget_window_egp": [applied_floor_egp, max_budget_egp],
            "parsed_text_prompt": parsed_prompt,
            "effective_weights": final_weights_dict,
            "results": [],
        }

    mat = np.array(
        [[l["derived_metrics"]["topsis_inputs"][k] for k in TOPSIS_CRITERIA_KEYS] for l in scoped_pool],
        dtype=float,
    )
    scores = _run_topsis_vector(mat, weights_vec, IS_BENEFIT_CRITERION)

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


def apply_persona_scores_to_catalog(catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Compute and attach static `persona_scores` (`hardware_fit`, `value_fit`) in-place."""
    laptops = catalog.get("laptops", [])
    if not laptops:
        return catalog

    hw_keys = TOPSIS_CRITERIA_KEYS[:9]
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
        w_val = np.array(
            [p_cfg["weights"].get(k, 0.08) for k in hw_keys]
            + [p_cfg["weights"]["effective_price_egp"] * 1.5],
            dtype=float,
        )

        hw_scores = _run_topsis_vector(hw_mat, w_hw, [True] * 9)
        val_scores = _run_topsis_vector(hw_plus_val_mat, w_val, [True] * 10)

        for i, lap in enumerate(laptops):
            ps = lap["derived_metrics"].setdefault("persona_scores", {})
            ps[p_key] = {
                "hardware_fit": float(hw_scores[i]),
                "value_fit": float(val_scores[i]),
            }

    return catalog
