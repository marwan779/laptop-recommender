"""Vector-Normalized TOPSIS Multi-Criteria Decision Making (MCDM) Engine.

Implements dynamic budget-scoped TOPSIS ranking in < 1ms:
1. Implicit Persona Gates with automatic graceful relaxation for low budgets.
2. Smart 60% Budget Floor to prevent cheap laptops from distorting the price vector.
3. Bilingual prompt parsing integration with dynamic criteria weight boosts.
4. Explainable recommendation badge generation.
5. In-memory pre-computation of static `persona_scores` (hardware_fit and value_fit).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
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


def _effective_topsis_inputs(
    lap: dict[str, Any],
    chroma_adjusted_nlp_scores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return a copy of a laptop's TOPSIS inputs with review-score overrides applied.

    The input laptop dictionary is never mutated. Missing ``community_nlp_score``
    values fall back to the neutral 75.0 baseline.
    """
    raw_inputs = (lap.get("derived_metrics") or {}).get("topsis_inputs") or {}
    inputs = dict(raw_inputs)
    if inputs.get("community_nlp_score") is None:
        inputs["community_nlp_score"] = 75.0

    if chroma_adjusted_nlp_scores:
        canonical_id = lap.get("canonical_id")
        if canonical_id in chroma_adjusted_nlp_scores:
            inputs["community_nlp_score"] = float(chroma_adjusted_nlp_scores[canonical_id])

    return inputs


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
    chroma_adjusted_nlp_scores: Mapping[str, float] | None = None,
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
    eff_require_dgpu = (
        require_dgpu if require_dgpu is not None else ext_filters.get("require_dgpu")
    )
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

    # 6. Zero-Candidate Edge Case: return the cheapest active alternatives instead
    # of an empty list so the front-end can still suggest something actionable.
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
            branded_fallback = [
                l for l in fallback_pool
                if str(l.get("brand") or "").lower().strip() in brands_norm
            ]
            if branded_fallback:
                fallback_pool = branded_fallback

        persona_fallback = [lap for lap in fallback_pool if _passes_persona_gates(lap, gates)]
        if eff_require_dgpu is True:
            dgpu_fallback = [
                lap for lap in (persona_fallback or fallback_pool)
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

    # 7. Build Decision Matrix (M x 10) with optional Chroma review-score overrides
    decision_inputs = [
        _effective_topsis_inputs(lap, chroma_adjusted_nlp_scores) for lap in scoped_pool
    ]
    mat = np.array(
        [[ti[k] for k in TOPSIS_CRITERIA_KEYS] for ti in decision_inputs],
        dtype=float,
    )
    scores = run_topsis_vector(mat, weights_vec, IS_BENEFIT_CRITERION)

    # 8. Sort and Format Top-K Results
    ranked_indices = np.argsort(-scores)[:top_k]
    results: list[RankedLaptopResult] = []

    for rank_idx, idx in enumerate(ranked_indices, start=1):
        lap = scoped_pool[int(idx)]
        score_val = float(scores[int(idx)])
        ti = decision_inputs[int(idx)]
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
                effective_price_egp=float(ti.get("effective_price_egp", 0.0)),
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
                reviews_evidence_count=_normalize_evidence_count(
                    community_reviews.get("evidence_count")
                ),
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
    """Calculate and attach `derived_metrics.persona_scores` across all personas.

    - hardware_fit: 0-100 score using the 9 benefit criteria (8 hardware metrics + community NLP).
    - value_fit: 0-100 score combining the 9 benefit criteria + value_score.
    Allows static landing pages to do instant SQL ORDER BY without running dynamic TOPSIS.
    """
    laptops = catalog_dict.get("laptops", [])
    if not laptops:
        return catalog_dict

    hw_keys = TOPSIS_CRITERIA_KEYS[:9]  # 8 hardware benefit criteria + community_nlp_score

    def _hw_row(lap: dict[str, Any]) -> list[float]:
        inputs = lap["derived_metrics"]["topsis_inputs"]
        return [
            float(inputs[k]) if inputs.get(k) is not None else (75.0 if k == "community_nlp_score" else 0.0)
            for k in hw_keys
        ]

    hw_mat = np.array([_hw_row(lap) for lap in laptops], dtype=float)
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

        hw_scores = run_topsis_vector(hw_mat, w_hw, [True] * 9)
        val_scores = run_topsis_vector(hw_plus_val_mat, w_val, [True] * 10)

        for i, lap in enumerate(laptops):
            dm = lap.setdefault("derived_metrics", {})
            ps = dm.setdefault("persona_scores", {})
            ps[p_key] = {
                "hardware_fit": float(hw_scores[i]),
                "value_fit": float(val_scores[i]),
            }

    return catalog_dict
