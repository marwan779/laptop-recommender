"""Pure domain modules for TOPSIS ranking and deterministic workload evaluation."""

from app.domain.recommendation.topsis import (
    CRITERIA_SEMANTIC_ANCHORS,
    IS_BENEFIT_CRITERION,
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    apply_persona_scores_to_catalog,
    build_budget_too_low_fallback,
    compute_semantic_weight_boosts,
    get_persona_db_query_spec,
    parse_user_text_prompt,
    rank_laptops_topsis,
    score_dual_review_vectors,
)
from app.domain.recommendation.workloads import evaluate_workloads

__all__ = [
    "CRITERIA_SEMANTIC_ANCHORS",
    "IS_BENEFIT_CRITERION",
    "PERSONA_CONFIGS",
    "TOPSIS_CRITERIA_KEYS",
    "apply_persona_scores_to_catalog",
    "build_budget_too_low_fallback",
    "compute_semantic_weight_boosts",
    "evaluate_workloads",
    "get_persona_db_query_spec",
    "parse_user_text_prompt",
    "rank_laptops_topsis",
    "score_dual_review_vectors",
]
