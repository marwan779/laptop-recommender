"""Vector-Normalized TOPSIS Multi-Criteria Decision Making (MCDM) Engine.

Implements dynamic budget-scoped TOPSIS ranking in < 1ms:
1. Implicit Persona Gates with automatic graceful relaxation for low budgets.
2. Smart 60% Budget Floor to prevent cheap laptops from distorting the price vector.
3. Bilingual prompt parsing integration with dynamic criteria weight boosts.
4. Explainable recommendation badge generation.
5. In-memory pre-computation of static `persona_scores` (hardware_fit and value_fit).
"""

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from app.domain.recommender.explainer import build_why_recommended
from app.domain.recommender.personas import (
    IS_BENEFIT_CRITERION,
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    PersonaType,
    parse_user_text_prompt,
)


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
    cheapest_offer_url: str | None = None
    available_stores: list[str] = field(default_factory=list)
    prices_by_store: dict[str, float] = field(default_factory=dict)
    urls_by_store: dict[str, str] = field(default_factory=dict)
    offers: list[dict[str, Any]] = field(default_factory=list)
    why_recommended_ar: list[str] = field(default_factory=list)
    why_recommended_en: list[str] = field(default_factory=list)
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

    # Step 1: Vector Normalization r_ij = x_ij / sqrt(sum(x_ij^2))
    col_norms = np.linalg.norm(decision_matrix, axis=0)
    col_norms[col_norms == 0.0] = 1.0
    r_mat = decision_matrix / col_norms

    # Step 2: Weighted Normalized Matrix v_ij = w_j * r_ij
    w_sum = np.sum(weights_vec)
    w_norm = weights_vec / (w_sum if w_sum > 0 else 1.0)
    v_mat = r_mat * w_norm

    # Step 3: Ideal Best (A+) and Ideal Worst (A-)
    ideal_best = np.zeros(n_cols, dtype=float)
    ideal_worst = np.zeros(n_cols, dtype=float)
    for j in range(n_cols):
        if is_benefit_vec[j]:
            ideal_best[j] = np.max(v_mat[:, j])
            ideal_worst[j] = np.min(v_mat[:, j])
        else:
            # Cost criterion (Price): lower price is better
            ideal_best[j] = np.min(v_mat[:, j])
            ideal_worst[j] = np.max(v_mat[:, j])

    # Step 4: Euclidean Distances D+ and D-
    d_pos = np.linalg.norm(v_mat - ideal_best, axis=1)
    d_neg = np.linalg.norm(v_mat - ideal_worst, axis=1)

    # Step 5: Relative Closeness C_i = D- / (D+ + D-) * 100
    denom = d_pos + d_neg
    closeness = np.where(denom > 1e-12, (d_neg / denom) * 100.0, 50.0)
    return np.round(closeness, 2)


def rank_laptops_topsis(
    laptops: list[dict[str, Any]],
    max_budget_egp: float = 300000.0,
    min_budget_egp: float | None = None,
    persona: str = PersonaType.BALANCED,
    user_text_prompt: str | None = None,
    min_ram_gb: int | None = None,
    min_storage_gb: int | None = None,
    require_dgpu: bool | None = None,
    brand_filter: list[str] | None = None,
    custom_weights: dict[str, float] | None = None,
    apply_smart_60pct_floor: bool = True,
    min_floor_candidates: int = 5,
    top_k: int = 10,
) -> TopsisExecutionResult:
    """Execute dynamic, budget-scoped TOPSIS ranking on candidate laptops.

    Accepts the full catalog or a pre-filtered list, applies implicit gates,
    resolves dynamic weight modifications from user prompts, and ranks the
    best options within milliseconds.
    """
    p_key = persona if persona in PERSONA_CONFIGS else PersonaType.BALANCED
    p_cfg = PERSONA_CONFIGS[p_key]

    # 1. Parse optional bilingual user text prompt
    parsed_prompt = parse_user_text_prompt(user_text_prompt)
    ext_filters = parsed_prompt["extracted_filters"]
    w_boosts = parsed_prompt["weight_boosts"]

    # 2. Merge weights: Base Persona -> Custom Weights -> Text Prompt Boosts
    final_weights_dict = dict(p_cfg["weights"])
    if custom_weights:
        for k, v in custom_weights.items():
            if k in final_weights_dict and v is not None:
                final_weights_dict[k] = float(v)
    for k, boost in w_boosts.items():
        if k in final_weights_dict:
            final_weights_dict[k] += boost

    # Normalize weights so sum equals 1.00
    w_sum = sum(final_weights_dict.values()) or 1.0
    final_weights_dict = {k: round(v / w_sum, 4) for k, v in final_weights_dict.items()}
    weights_vec = np.array([final_weights_dict[k] for k in TOPSIS_CRITERIA_KEYS], dtype=float)

    # 3. Base Hard Filters: active in-stock, budget boundary, explicit hardware constraints
    eff_min_ram = min_ram_gb or ext_filters.get("min_ram_gb")
    eff_min_sto = min_storage_gb or ext_filters.get("min_storage_gb")
    brands_norm = {b.lower().strip() for b in brand_filter} if brand_filter else None

    base_pool: list[dict[str, Any]] = []
    for lap in laptops:
        ti = lap.get("derived_metrics", {}).get("topsis_inputs", {})
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
        if require_dgpu is True and gpu.get("integrated", True):
            continue
        if ext_filters.get("require_oled") and "OLED" not in str(disp.get("panel_type") or "").upper():
            continue
        if ext_filters.get("require_touchscreen") and not disp.get("touchscreen"):
            continue

        base_pool.append(lap)

    # 4. Apply Implicit Persona Gates (with graceful relaxation for low budgets)
    gates = p_cfg["implicit_gates"]
    persona_pool: list[dict[str, Any]] = []
    for lap in base_pool:
        s = lap.get("specs") or {}
        dm = lap.get("derived_metrics") or {}
        gpu_spec = s.get("gpu") or {}
        disp_spec = s.get("display") or {}
        mem_spec = s.get("memory") or {}
        cpu_spec = s.get("cpu") or {}

        if gates.get("require_dgpu") and gpu_spec.get("integrated", True):
            continue
        if gates.get("min_refresh_hz") and (disp_spec.get("refresh_rate_hz") or 60) < gates["min_refresh_hz"]:
            continue
        if gates.get("min_ram_gb") and (mem_spec.get("capacity_gb") or 0) < gates["min_ram_gb"]:
            continue
        if gates.get("min_cpu_cores") and (cpu_spec.get("cores") or 0) < gates["min_cpu_cores"]:
            continue
        if gates.get("require_creator_display"):
            gtier = str(dm.get("display", {}).get("color_gamut_tier", "")).lower()
            if "100% srgb" not in gtier and "dci-p3" not in gtier:
                continue
        if gates.get("max_weight_kg") and dm.get("mobility", {}).get("weight_kg", 2.0) > gates["max_weight_kg"]:
            continue

        persona_pool.append(lap)

    # Graceful relaxation: if strict gates left fewer than 3 options (or 0 options),
    # fall back to base pool so long as base pool has candidates
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
            l for l in persona_pool
            if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("effective_price_egp", 0.0) >= floor_60
        ]
        if len(pool_60) >= min_floor_candidates:
            scoped_pool = pool_60
            applied_floor_egp = floor_60
        else:
            floor_45 = round(max_budget_egp * 0.45, 0)
            pool_45 = [
                l for l in persona_pool
                if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("effective_price_egp", 0.0) >= floor_45
            ]
            if len(pool_45) >= min_floor_candidates:
                scoped_pool = pool_45
                applied_floor_egp = floor_45

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
        )

    # 6. Build Decision Matrix (M x 9) and Run Vector TOPSIS
    mat = np.array(
        [[l["derived_metrics"]["topsis_inputs"][k] for k in TOPSIS_CRITERIA_KEYS] for l in scoped_pool],
        dtype=float,
    )
    scores = run_topsis_vector(mat, weights_vec, IS_BENEFIT_CRITERION)

    # 7. Sort and Format Top-K Results
    ranked_indices = np.argsort(-scores)[:top_k]
    results: list[RankedLaptopResult] = []

    for rank_idx, idx in enumerate(ranked_indices, start=1):
        lap = scoped_pool[int(idx)]
        score_val = float(scores[int(idx)])
        ti = lap["derived_metrics"]["topsis_inputs"]
        why = build_why_recommended(lap, p_key)

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
                effective_price_egp=float(ti.get("effective_price_egp", 0.0)),
                cheapest_store=cheapest_store,
                cheapest_offer_url=cheapest_offer_url,
                available_stores=lap.get("available_stores") or [],
                prices_by_store=lap.get("prices_by_store") or {},
                urls_by_store=urls_by_store,
                offers=raw_offers,
                why_recommended_ar=why["ar"],
                why_recommended_en=why["en"],
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
    )


def enrich_catalog_with_persona_scores(catalog_dict: dict[str, Any]) -> dict[str, Any]:
    """Calculate and attach `derived_metrics.persona_scores` across all personas.

    - hardware_fit: 0-100 score using only the 8 hardware benefit metrics (price-independent).
    - value_fit: 0-100 score combining the 8 hardware metrics + value_score.
    Allows static landing pages to do instant SQL ORDER BY without running dynamic TOPSIS.
    """
    laptops = catalog_dict.get("laptops", [])
    if not laptops:
        return catalog_dict

    hw_keys = TOPSIS_CRITERIA_KEYS[:8]  # The 8 hardware benefit criteria
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
        w_hw = np.array([p_cfg["weights"][k] for k in hw_keys], dtype=float)
        w_val = np.array(
            [p_cfg["weights"][k] for k in hw_keys] + [p_cfg["weights"]["effective_price_egp"] * 1.5],
            dtype=float,
        )

        hw_scores = run_topsis_vector(hw_mat, w_hw, [True] * 8)
        val_scores = run_topsis_vector(hw_plus_val_mat, w_val, [True] * 9)

        for i, lap in enumerate(laptops):
            dm = lap.setdefault("derived_metrics", {})
            ps = dm.setdefault("persona_scores", {})
            ps[p_key] = {
                "hardware_fit": float(hw_scores[i]),
                "value_fit": float(val_scores[i]),
            }

    return catalog_dict
