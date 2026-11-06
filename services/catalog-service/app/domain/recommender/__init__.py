"""Recommender domain package.

Exposes TOPSIS multi-criteria decision making, persona profiles, bilingual prompt parsing,
and explainability badge generators.
"""

from app.domain.recommender.explainer import build_why_recommended
from app.domain.recommender.personas import (
    IS_BENEFIT_CRITERION,
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    PersonaType,
    get_persona_db_query_spec,
    parse_user_text_prompt,
)
from app.domain.recommender.topsis import (
    RankedLaptopResult,
    TopsisExecutionResult,
    enrich_catalog_with_persona_scores,
    rank_laptops_topsis,
    run_topsis_vector,
)

__all__ = [
    "IS_BENEFIT_CRITERION",
    "PERSONA_CONFIGS",
    "TOPSIS_CRITERIA_KEYS",
    "PersonaType",
    "RankedLaptopResult",
    "TopsisExecutionResult",
    "build_why_recommended",
    "enrich_catalog_with_persona_scores",
    "get_persona_db_query_spec",
    "parse_user_text_prompt",
    "rank_laptops_topsis",
    "run_topsis_vector",
]
