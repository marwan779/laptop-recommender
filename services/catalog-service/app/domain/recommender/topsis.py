"""Vector-Normalized TOPSIS Multi-Criteria Decision Making (MCDM) Engine.

Implements dynamic 14-column budget-scoped TOPSIS ranking in < 1ms:
1. Implicit Persona Gates (with NVIDIA/VRAM/display/weight checks) + graceful relaxation.
2. Smart 60% Budget Floor to prevent cheap laptops from distorting the price vector.
3. Bilingual prompt parsing & remote /score-prompt NLP score/weight integration.
4. Calibrated persona_value_score using smooth logistic-sigmoid calibration.
5. Explainable recommendation badge generation.
6. In-memory pre-computation of static `persona_scores` (hardware_fit and value_fit).
"""

from collections.abc import Mapping
import copy
from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from app.domain.pricing import DEFAULT_COMMUNITY_NLP_SCORE, calculate_calibrated_value_score
from app.domain.recommender.explainer import build_why_recommended
from app.domain.recommender.personas import (
    IS_BENEFIT_CRITERION,
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    parse_user_text_prompt,
    resolve_persona_key,
)

DEFAULT_COMMUNITY_NLP_WEIGHT = 0.06

_LEGACY_WEIGHT_EXPANSION: dict[str, list[tuple[str, float]]] = {
    "gpu_score": [("gpu_compute_score", 0.72), ("vram_score", 0.28)],
    "display_score": [("display_gaming_score", 0.50), ("display_creator_score", 0.50)],
    "mobility_score": [("battery_score", 0.50), ("portability_score", 0.50)],
    "longevity_score": [("upgradeability_score", 0.65), ("build_quality_score", 0.35)],
}


@dataclass(frozen=True)
class RankedLaptopResult:
    """Domain model of a single ranked laptop recommendation."""

    rank: int
    canonical_id: str
    brand: str
    laptop_family: str | None
    laptop_model: str | None
    title: str
    thumbnail_url: str | None
    topsis_match_score: float
    effective_price_egp: float
    cheapest_store: str
    persona_value_score: float | None = None
    cheapest_offer_url: str | None = None
    available_stores: list[str] = field(default_factory=list)
    prices_by_store: dict[str, float] = field(default_factory=dict)
    urls_by_store: dict[str, str] = field(default_factory=dict)
    offers: list[dict[str, Any]] = field(default_factory=list)
    why_recommended_ar: list[str] = field(default_factory=list)
    why_recommended_en: list[str] = field(default_factory=list)
    pros_en: list[str] = field(default_factory=list)
    pros_ar: list[str] = field(default_factory=list)
    cons_en: list[str] = field(default_factory=list)
    cons_ar: list[str] = field(default_factory=list)
    reviews_evidence_count: int = 0
    aspect_scores: dict[str, float] = field(default_factory=dict)
    topsis_inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopsisExecutionResult:
    """Domain model of complete TOPSIS ranking execution."""

    persona: str
    persona_label_ar: str
    persona_label_en: str
    gates_relaxed_for_low_budget: bool
    total_candidates_before_floor: int
    total_candidates_after_gates_and_floor: int
    applied_budget_window_egp: list[float]
    parsed_text_prompt: dict[str, Any]
    effective_weights: dict[str, float]
    results: list[RankedLaptopResult]
    status: str = "OK"


def _normalize_evidence_count(value: Any) -> int:
    """Coerce a review evidence count into a non-negative integer."""
    if value is None or isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _normalize_aspect_scores(value: Any) -> dict[str, float]:
    """Coerce a raw aspect-score mapping into clean ``str -> float`` values."""
    if not isinstance(value, Mapping):
        return {}

    scores: dict[str, float] = {}
    for key, raw_score in value.items():
        if raw_score is None or isinstance(raw_score, bool):
            continue
        try:
            scores[str(key)] = float(raw_score)
        except (TypeError, ValueError):
            continue
    return scores


def _apply_weight_overrides(
    weights_dict: dict[str, float],
    overrides: Mapping[str, float],
    additive: bool = False,
) -> None:
    """Apply overrides onto 14-column weights, expanding any legacy 10-column keys safely."""
    for k, v in overrides.items():
        if v is None:
            continue
        fval = float(v)
        if k in weights_dict:
            weights_dict[k] = (weights_dict[k] + fval) if additive else fval
        elif k in _LEGACY_WEIGHT_EXPANSION:
            for sub_k, share in _LEGACY_WEIGHT_EXPANSION[k]:
                if sub_k in weights_dict:
                    delta = fval * share
                    weights_dict[sub_k] = (weights_dict[sub_k] + delta) if additive else delta


def _extract_matrix_cell(
    ti: Mapping[str, Any],
    col_key: str,
    cid: str,
    adjusted_nlp_scores: Mapping[str, float] | None,
) -> float:
    """Safely extract a 14-column numeric criterion with backward-compatible fallbacks."""
    if col_key == "community_nlp_score":
        if adjusted_nlp_scores and cid in adjusted_nlp_scores and adjusted_nlp_scores[cid] is not None:
            val = float(adjusted_nlp_scores[cid])
        elif ti.get("community_nlp_score") is not None:
            val = float(ti["community_nlp_score"])
        else:
            val = DEFAULT_COMMUNITY_NLP_SCORE
        return val if math.isfinite(val) else DEFAULT_COMMUNITY_NLP_SCORE

    raw_val = ti.get(col_key)
    if raw_val is None:
        fallback_map = {
            "gpu_compute_score": ti.get("gpu_score", 18.0),
            "vram_score": 15.0,
            "display_gaming_score": ti.get("display_score", 50.0),
            "display_creator_score": ti.get("display_score", 50.0),
            "battery_score": ti.get("mobility_score", 50.0),
            "portability_score": ti.get("mobility_score", 50.0),
            "upgradeability_score": ti.get("longevity_score", 50.0),
            "build_quality_score": ti.get("longevity_score", 60.0),
        }
        raw_val = fallback_map.get(col_key, 50.0)
    val = float(raw_val)
    return val if math.isfinite(val) else 50.0


def _effective_topsis_inputs(
    lap: dict[str, Any],
    chroma_adjusted_nlp_scores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return a copy of a laptop's TOPSIS inputs with 14-column fallbacks and NLP overrides."""
    raw_inputs = (lap.get("derived_metrics") or {}).get("topsis_inputs") or {}
    inputs = dict(raw_inputs)
    cid = str(lap.get("canonical_id") or "")
    for key in TOPSIS_CRITERIA_KEYS:
        if key == "effective_price_egp":
            continue
        inputs[key] = _extract_matrix_cell(inputs, key, cid, chroma_adjusted_nlp_scores)
    return inputs


def _is_nvidia_gpu(lap: dict[str, Any]) -> bool:
    """Return True when the laptop's GPU is an NVIDIA GeForce/RTX/Quadro discrete GPU."""
    gpu = (lap.get("specs") or {}).get("gpu") or {}
    if gpu.get("integrated", True):
        return False
    mfr = str(gpu.get("manufacturer") or "").lower()
    model = str(gpu.get("model") or "").lower()
    return "nvidia" in mfr or "rtx" in model or "gtx" in model or "geforce" in model


def _passes_persona_gates(
    lap: dict[str, Any],
    gates: Mapping[str, Any],
) -> bool:
    """Return True when a laptop satisfies every implicit persona gate."""
    specs = lap.get("specs") or {}
    derived = lap.get("derived_metrics") or {}
    gpu = specs.get("gpu") or {}
    display = specs.get("display") or {}
    memory = specs.get("memory") or {}
    cpu = specs.get("cpu") or {}

    if gates.get("require_dgpu") and gpu.get("integrated", True):
        return False
    if gates.get("require_nvidia") and not _is_nvidia_gpu(lap):
        return False
    if gates.get("min_vram_gb") and (gpu.get("vram_gb") or 0) < gates["min_vram_gb"]:
        return False
    if gates.get("min_refresh_hz") and (display.get("refresh_rate_hz") or 60) < gates["min_refresh_hz"]:
        return False
    if gates.get("min_ram_gb") and (memory.get("capacity_gb") or 0) < gates["min_ram_gb"]:
        return False
    if gates.get("min_cpu_cores") and (cpu.get("cores") or 0) < gates["min_cpu_cores"]:
        return False
    if gates.get("require_creator_display"):
        gamut_tier = str((derived.get("display") or {}).get("color_gamut_tier", "")).lower()
        if "100% srgb" not in gamut_tier and "dci-p3" not in gamut_tier:
            return False
    if gates.get("max_weight_kg") and (derived.get("mobility") or {}).get("weight_kg", 2.0) > gates["max_weight_kg"]:
        return False

    return True


def compute_nlp_dynamic_weight(net_sims: list[float]) -> tuple[float, float]:
    """Map net_sim spread (mean top-5 minus median rest) smoothly to [0.10, 0.25]."""
    if not net_sims:
        return 0.10, 0.0
    sorted_sims = sorted(net_sims, reverse=True)
    if len(sorted_sims) > 5:
        spread = max(0.0, float(np.mean(sorted_sims[:5]) - np.median(sorted_sims[5:])))
    else:
        spread = max(0.0, float(sorted_sims[0] - np.median(sorted_sims)))
    ratio = max(0.0, min(1.0, (spread - 0.08) / (0.26 - 0.08)))
    dyn_weight = round(0.10 + ratio * (0.25 - 0.10), 4)
    return dyn_weight, round(spread, 4)


def _compute_persona_value_score(
    laptop: dict[str, Any],
    hw_row_13: np.ndarray,
    hw_weights_13: np.ndarray,
    p_key: str,
    eff_price: float | None,
) -> float:
    """Compute smoothly calibrated persona value score from persona hardware_fit and price."""
    if not eff_price or eff_price < 10000:
        return 50.0
    ps_entry = (laptop.get("derived_metrics") or {}).get("persona_scores", {}).get(p_key, {})
    persona_hw_fit = ps_entry.get("hardware_fit")
    if persona_hw_fit is None:
        w_sum = float(np.sum(hw_weights_13))
        if w_sum > 1e-12:
            persona_hw_fit = float(np.dot(hw_row_13, hw_weights_13) / w_sum)
        else:
            persona_hw_fit = float(np.mean(hw_row_13))
    return calculate_calibrated_value_score(max(1.0, float(persona_hw_fit)), eff_price)


def run_topsis_vector(
    decision_matrix: np.ndarray,
    weights_vec: np.ndarray,
    is_benefit_vec: list[bool],
) -> np.ndarray:
    """Execute standard Vector-Normalized TOPSIS on an (M x N) NumPy matrix.

    Returns an array of Relative Closeness Scores scaled [0.0, 100.0] for the M laptops.
    """
    m_rows, n_cols = decision_matrix.shape
    if m_rows == 0:
        return np.array([], dtype=float)
    if m_rows == 1:
        return np.array([100.0], dtype=float)

    col_norms = np.linalg.norm(decision_matrix, axis=0)
    col_norms[col_norms == 0.0] = 1.0
    r_mat = decision_matrix / col_norms

    w_sum = float(np.sum(weights_vec))
    w_norm = weights_vec / w_sum if w_sum > 0 else np.ones(n_cols, dtype=float) / n_cols
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
    closeness = np.where(denom == 0.0, 1.0, d_neg / np.where(denom == 0.0, 1.0, denom))
    return np.round(closeness * 100.0, 2)


def rank_laptops_topsis(
    laptops: list[dict[str, Any]],
    max_budget_egp: float = 300000.0,
    min_budget_egp: float | None = None,
    persona: str = "balanced",
    user_text_prompt: str | None = None,
    min_ram_gb: int | None = None,
    min_storage_gb: int | None = None,
    require_dgpu: bool | None = None,
    brand_filter: list[str] | None = None,
    custom_weights: dict[str, float] | None = None,
    nlp_dynamic_weight: float | None = None,
    chroma_adjusted_nlp_scores: Mapping[str, float] | None = None,
    parsed_constraints: Mapping[str, Any] | None = None,
    apply_smart_60pct_floor: bool = True,
    min_floor_candidates: int = 5,
    top_k: int = 10,
) -> TopsisExecutionResult:
    """Execute dynamic 14-column budget-scoped TOPSIS ranking on candidate laptops."""
    p_key = resolve_persona_key(persona)
    p_cfg = PERSONA_CONFIGS[p_key]

    # 1. Parse optional bilingual user text prompt & merge remote parsed_constraints
    parsed_prompt = parse_user_text_prompt(user_text_prompt)
    ext_filters = dict(parsed_prompt["extracted_filters"])
    if parsed_constraints:
        ext_filters.update(dict(parsed_constraints))
        parsed_prompt = {
            "extracted_filters": ext_filters,
            "weight_boosts": parsed_prompt["weight_boosts"],
        }
    w_boosts = parsed_prompt["weight_boosts"]

    # 2. Merge weights: Base Persona (14 cols) -> Dynamic NLP Weight -> Custom Weights -> Text Prompt Boosts
    final_weights_dict: dict[str, float] = copy.deepcopy(p_cfg["weights"])
    final_weights_dict.setdefault("community_nlp_score", DEFAULT_COMMUNITY_NLP_WEIGHT)
    if nlp_dynamic_weight is not None:
        final_weights_dict["community_nlp_score"] = float(nlp_dynamic_weight)
    if custom_weights:
        _apply_weight_overrides(final_weights_dict, custom_weights, additive=False)
    if w_boosts:
        _apply_weight_overrides(final_weights_dict, w_boosts, additive=True)

    # Normalize weights so sum equals 1.00
    w_sum = sum(final_weights_dict.values()) or 1.0
    final_weights_dict = {k: round(v / w_sum, 4) for k, v in final_weights_dict.items()}
    weights_vec = np.array([final_weights_dict[k] for k in TOPSIS_CRITERIA_KEYS], dtype=float)
    hw_weights_13 = weights_vec[:13]

    # 3. Base Hard Filters: active in-stock, budget boundary, explicit hardware constraints
    eff_min_ram = min_ram_gb or ext_filters.get("min_ram_gb")
    eff_min_sto = min_storage_gb or ext_filters.get("min_storage_gb")
    eff_require_dgpu = require_dgpu if require_dgpu is not None else ext_filters.get("require_dgpu")
    brands_norm = {b.lower().strip() for b in brand_filter} if brand_filter else None

    base_pool: list[dict[str, Any]] = []
    for lap in laptops:
        ti = (lap.get("derived_metrics") or {}).get("topsis_inputs") or {}
        if not ti.get("in_stock_active", False):
            continue
        price = ti.get("effective_price_egp")
        if price is None or price > max_budget_egp:
            continue
        if min_budget_egp is not None and price < min_budget_egp:
            continue
        if brands_norm and str(lap.get("brand") or "").lower().strip() not in brands_norm:
            continue

        specs = lap.get("specs") or {}
        mem = specs.get("memory") or {}
        storage = specs.get("storage") or {}
        gpu = specs.get("gpu") or {}
        disp = specs.get("display") or {}

        if eff_min_ram and (mem.get("capacity_gb") or 0) < eff_min_ram:
            continue
        if eff_min_sto and (storage.get("capacity_gb") or 0) < eff_min_sto:
            continue
        if eff_require_dgpu is True and gpu.get("integrated", True):
            continue
        if eff_require_dgpu is False and not gpu.get("integrated", True):
            continue
        if ext_filters.get("require_oled") and "OLED" not in str(disp.get("panel_type") or "").upper():
            continue
        if ext_filters.get("require_touchscreen") and not disp.get("touchscreen"):
            continue

        base_pool.append(lap)

    # 4. Apply Implicit Persona Gates (with graceful relaxation for low budgets)
    gates = p_cfg["implicit_gates"]
    persona_pool = [lap for lap in base_pool if _passes_persona_gates(lap, gates)]

    gates_relaxed = False
    if (len(persona_pool) < 3 and len(base_pool) >= 3) or (not persona_pool and len(base_pool) > 0):
        persona_pool = base_pool
        gates_relaxed = True

    # 5. Smart 60% Budget Floor (prevents cheap laptops from distorting the price vector)
    applied_floor_egp = min_budget_egp if min_budget_egp is not None else 0.0
    scoped_pool = persona_pool

    if min_budget_egp is None and apply_smart_60pct_floor and len(persona_pool) > min_floor_candidates:
        floor_60 = round(max_budget_egp * 0.60, 0)
        pool_60 = [
            l
            for l in persona_pool
            if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("effective_price_egp", 0.0) >= floor_60
        ]
        if len(pool_60) >= min_floor_candidates:
            scoped_pool = pool_60
            applied_floor_egp = floor_60
        else:
            floor_45 = round(max_budget_egp * 0.45, 0)
            pool_45 = [
                l
                for l in persona_pool
                if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("effective_price_egp", 0.0) >= floor_45
            ]
            if len(pool_45) >= min_floor_candidates:
                scoped_pool = pool_45
                applied_floor_egp = floor_45

    # 6. Zero-Candidate Edge Case: return cheapest active alternatives
    status = "OK"
    if not scoped_pool:
        fallback_pool: list[dict[str, Any]] = []
        for lap in laptops:
            ti = (lap.get("derived_metrics") or {}).get("topsis_inputs") or {}
            if not ti.get("in_stock_active", False):
                continue
            price = ti.get("effective_price_egp")
            if price is None or float(price) <= 0:
                continue
            fallback_pool.append(lap)

        if brands_norm:
            branded_fallback = [l for l in fallback_pool if str(l.get("brand") or "").lower().strip() in brands_norm]
            if branded_fallback:
                fallback_pool = branded_fallback

        persona_fallback = [lap for lap in fallback_pool if _passes_persona_gates(lap, gates)]
        if eff_require_dgpu is True:
            dgpu_fallback = [
                lap
                for lap in (persona_fallback or fallback_pool)
                if not (lap.get("specs") or {}).get("gpu", {}).get("integrated", True)
            ]
            if dgpu_fallback:
                fallback_pool = dgpu_fallback
            elif persona_fallback:
                fallback_pool = persona_fallback
        elif persona_fallback:
            fallback_pool = persona_fallback

        fallback_pool.sort(
            key=lambda l: float(
                (((l.get("derived_metrics") or {}).get("topsis_inputs") or {}).get("effective_price_egp")) or 0.0
            )
        )
        scoped_pool = fallback_pool[: min(3, top_k)]
        status = "BUDGET_TOO_LOW_FOR_CATEGORY"
        gates_relaxed = True
    elif gates_relaxed:
        status = "GATES_RELAXED_FOR_LOW_BUDGET"

    if not scoped_pool:
        return TopsisExecutionResult(
            persona=p_key,
            persona_label_ar=p_cfg["label_ar"],
            persona_label_en=p_cfg["label_en"],
            gates_relaxed_for_low_budget=gates_relaxed,
            total_candidates_before_floor=len(base_pool),
            total_candidates_after_gates_and_floor=0,
            applied_budget_window_egp=[applied_floor_egp, max_budget_egp],
            parsed_text_prompt=parsed_prompt,
            effective_weights=final_weights_dict,
            results=[],
            status=status,
        )

    # 7. Build Decision Matrix (M x 14) with optional Chroma review-score overrides
    decision_inputs = [_effective_topsis_inputs(lap, chroma_adjusted_nlp_scores) for lap in scoped_pool]
    mat = np.array(
        [[ti[k] for k in TOPSIS_CRITERIA_KEYS] for ti in decision_inputs],
        dtype=float,
    )
    scores = run_topsis_vector(mat, weights_vec, IS_BENEFIT_CRITERION)

    # 8. Sort and Format Top-K Results
    ranked_indices = np.argsort(-scores)[:top_k]
    results: list[RankedLaptopResult] = []

    for rank_idx, idx in enumerate(ranked_indices, start=1):
        row_i = int(idx)
        lap = scoped_pool[row_i]
        score_val = float(scores[row_i])
        ti = decision_inputs[row_i]
        eff_price = float(ti.get("effective_price_egp", 0.0))
        p_val_score = _compute_persona_value_score(lap, mat[row_i, :13], hw_weights_13, p_key, eff_price)
        why = build_why_recommended(lap, p_key)
        community_reviews = (lap.get("derived_metrics") or {}).get("community_reviews") or {}
        if not isinstance(community_reviews, dict):
            community_reviews = {}
        aspect_scores = _normalize_aspect_scores(community_reviews.get("aspect_scores"))

        cheapest_store = lap.get("cheapest_store") or "unknown"
        urls_by_store = lap.get("urls_by_store") or {}
        cheapest_offer_url = lap.get("cheapest_offer_url") or urls_by_store.get(cheapest_store.lower().strip())
        raw_offers = lap.get("offers") or []

        results.append(
            RankedLaptopResult(
                rank=rank_idx,
                canonical_id=lap["canonical_id"],
                brand=lap.get("brand") or "Generic",
                laptop_family=lap.get("laptop_family"),
                laptop_model=lap.get("laptop_model"),
                title=lap.get("title") or "Laptop",
                thumbnail_url=lap.get("thumbnail_url"),
                topsis_match_score=score_val,
                persona_value_score=p_val_score,
                effective_price_egp=eff_price,
                cheapest_store=cheapest_store,
                cheapest_offer_url=cheapest_offer_url,
                available_stores=lap.get("available_stores") or [],
                prices_by_store=lap.get("prices_by_store") or {},
                urls_by_store=urls_by_store,
                offers=raw_offers,
                why_recommended_ar=why["ar"],
                why_recommended_en=why["en"],
                pros_en=list(community_reviews.get("pros_en") or []),
                pros_ar=list(community_reviews.get("pros_ar") or []),
                cons_en=list(community_reviews.get("cons_en") or []),
                cons_ar=list(community_reviews.get("cons_ar") or []),
                reviews_evidence_count=_normalize_evidence_count(community_reviews.get("evidence_count")),
                aspect_scores=aspect_scores,
                topsis_inputs=ti,
            )
        )

    return TopsisExecutionResult(
        persona=p_key,
        persona_label_ar=p_cfg["label_ar"],
        persona_label_en=p_cfg["label_en"],
        gates_relaxed_for_low_budget=gates_relaxed,
        total_candidates_before_floor=len(base_pool),
        total_candidates_after_gates_and_floor=len(scoped_pool),
        applied_budget_window_egp=[applied_floor_egp, max_budget_egp],
        parsed_text_prompt=parsed_prompt,
        effective_weights=final_weights_dict,
        results=results,
        status=status,
    )


def enrich_catalog_with_persona_scores(catalog_dict: dict[str, Any]) -> dict[str, Any]:
    """Calculate and attach `derived_metrics.persona_scores` across all 16 personas."""
    laptops = catalog_dict.get("laptops", [])
    if not laptops:
        return catalog_dict

    hw_keys = TOPSIS_CRITERIA_KEYS[:13]  # 13 benefit criteria

    def _hw_row(lap: dict[str, Any]) -> list[float]:
        inputs = lap["derived_metrics"]["topsis_inputs"]
        cid = str(lap.get("canonical_id") or "")
        return [_extract_matrix_cell(inputs, k, cid, None) for k in hw_keys]

    hw_mat = np.array([_hw_row(lap) for lap in laptops], dtype=float)
    val_col = np.array(
        [[l["derived_metrics"]["topsis_inputs"]["value_score"]] for l in laptops],
        dtype=float,
    )
    hw_plus_val_mat = np.hstack([hw_mat, val_col])

    for p_key, p_cfg in PERSONA_CONFIGS.items():
        w_hw = np.array(
            [p_cfg["weights"].get(k, DEFAULT_COMMUNITY_NLP_WEIGHT) for k in hw_keys],
            dtype=float,
        )
        w_val = np.array(
            [p_cfg["weights"].get(k, DEFAULT_COMMUNITY_NLP_WEIGHT) for k in hw_keys]
            + [p_cfg["weights"]["effective_price_egp"] * 1.5],
            dtype=float,
        )

        hw_scores = run_topsis_vector(hw_mat, w_hw, [True] * 13)
        val_scores = run_topsis_vector(hw_plus_val_mat, w_val, [True] * 14)

        for i, lap in enumerate(laptops):
            dm = lap.setdefault("derived_metrics", {})
            ps = dm.setdefault("persona_scores", {})
            ps[p_key] = {
                "hardware_fit": float(hw_scores[i]),
                "value_fit": float(val_scores[i]),
            }

    return catalog_dict
