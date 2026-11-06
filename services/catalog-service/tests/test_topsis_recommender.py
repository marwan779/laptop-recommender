import json
from pathlib import Path
import pytest
import numpy as np

from app.domain.recommender import (
    PersonaType,
    enrich_catalog_with_persona_scores,
    get_persona_db_query_spec,
    parse_user_text_prompt,
    rank_laptops_topsis,
    run_topsis_vector,
)

CATALOG_PATH = Path(__file__).resolve().parent.parent / "scraping input" / "unified_catalog_latest.json"


@pytest.fixture(scope="module")
def real_catalog_laptops() -> list[dict]:
    """Load the clean 295-laptop catalog for domain simulation tests."""
    if not CATALOG_PATH.exists():
        pytest.skip(f"Unified catalog not found at {CATALOG_PATH}")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("laptops", [])


# =============================================================================
# 1. BILINGUAL TEXT PARSER TESTS
# =============================================================================
def test_parse_user_text_prompt_english():
    prompt = "I need 32GB RAM and 1TB SSD with an OLED screen for heavy coding and Docker"
    parsed = parse_user_text_prompt(prompt)

    filters = parsed["extracted_filters"]
    boosts = parsed["weight_boosts"]

    assert filters.get("min_ram_gb") == 32
    assert filters.get("min_storage_gb") == 1024
    assert filters.get("require_oled") is True
    assert boosts.get("cpu_score", 0.0) > 0.10
    assert boosts.get("display_score", 0.0) > 0.10


def test_parse_user_text_prompt_arabic():
    prompt = "عايز بطارية تقعد كتير ووزن خفيف وشاشة اوليد"
    parsed = parse_user_text_prompt(prompt)

    filters = parsed["extracted_filters"]
    boosts = parsed["weight_boosts"]

    assert filters.get("require_oled") is True
    assert boosts.get("mobility_score", 0.0) > 0.10
    assert boosts.get("display_score", 0.0) > 0.10


def test_parse_user_text_prompt_empty():
    assert parse_user_text_prompt(None) == {"extracted_filters": {}, "weight_boosts": {}}
    assert parse_user_text_prompt("   ") == {"extracted_filters": {}, "weight_boosts": {}}


# =============================================================================
# 2. PURE VECTOR TOPSIS MATHEMATICAL TESTS
# =============================================================================
def test_run_topsis_vector_empty():
    res = run_topsis_vector(np.empty((0, 3)), np.array([0.3, 0.3, 0.4]), [True, True, False])
    assert len(res) == 0


def test_run_topsis_vector_single_candidate():
    res = run_topsis_vector(np.array([[80.0, 90.0, 30000.0]]), np.array([0.4, 0.4, 0.2]), [True, True, False])
    assert len(res) == 1
    assert res[0] == 100.0


def test_run_topsis_vector_multi_candidates():
    # 3 laptops, 3 criteria: Perf 1 (Benefit), Perf 2 (Benefit), Price (Cost)
    # Laptop A: [90, 90, 50000] - high perf, high price
    # Laptop B: [50, 50, 20000] - low perf, cheap
    # Laptop C: [85, 85, 25000] - high perf, cheap (Clear Winner)
    mat = np.array([
        [90.0, 90.0, 50000.0],
        [50.0, 50.0, 20000.0],
        [85.0, 85.0, 25000.0],
    ])
    weights = np.array([0.4, 0.4, 0.2])
    is_benefit = [True, True, False]

    scores = run_topsis_vector(mat, weights, is_benefit)
    assert len(scores) == 3
    # Laptop C (index 2) should score highest
    assert scores[2] > scores[0]
    assert scores[2] > scores[1]


# =============================================================================
# 3. LIVE SIMULATION SCENARIO TESTS (5 REAL-WORLD SCENARIOS)
# =============================================================================
def test_scenario_1_gaming_70k(real_catalog_laptops):
    """Scenario 1: Gaming budget 70,000 EGP (no extra text)."""
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=70000.0,
        persona=PersonaType.GAMING,
        top_k=5,
    )

    assert result.persona == "gaming"
    assert result.gates_relaxed_for_low_budget is False
    assert len(result.results) > 0
    assert result.applied_budget_window_egp[0] >= 40000.0  # 60% floor applied

    winner = result.results[0]
    assert winner.rank == 1
    assert winner.effective_price_egp <= 70000.0
    assert winner.topsis_match_score > 70.0
    assert len(winner.why_recommended_ar) > 0
    assert len(winner.why_recommended_en) > 0


def test_scenario_2_programming_55k(real_catalog_laptops):
    """Scenario 2: Programming budget 55,000 EGP."""
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=55000.0,
        persona=PersonaType.PROGRAMMING,
        top_k=5,
    )

    assert result.persona == "programming"
    assert len(result.results) > 0
    winner = result.results[0]
    assert winner.effective_price_egp <= 55000.0


def test_scenario_3_programming_arabic_oled_prompt(real_catalog_laptops):
    """Scenario 3: Programming 55,000 EGP + Arabic text: 'عايز بطارية تقعد كتير ووزن خفيف وشاشة اوليد'."""
    prompt = "عايز بطارية تقعد كتير ووزن خفيف وشاشة اوليد"
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=55000.0,
        persona=PersonaType.PROGRAMMING,
        user_text_prompt=prompt,
        top_k=5,
    )

    assert result.parsed_text_prompt["extracted_filters"].get("require_oled") is True
    assert len(result.results) > 0
    # Every recommended laptop MUST be OLED
    for item in result.results:
        matched_laptop = next(l for l in real_catalog_laptops if l["canonical_id"] == item.canonical_id)
        panel = matched_laptop["specs"]["display"].get("panel_type") or ""
        assert "OLED" in panel.upper()


def test_scenario_4_content_creation_65k(real_catalog_laptops):
    """Scenario 4: Content Creation budget 65,000 EGP."""
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=65000.0,
        persona=PersonaType.CONTENT_CREATION,
        top_k=5,
    )

    assert result.persona == "content_creation"
    assert len(result.results) > 0
    for item in result.results:
        matched = next(l for l in real_catalog_laptops if l["canonical_id"] == item.canonical_id)
        gamut = matched["derived_metrics"]["display"].get("color_gamut_tier", "").lower()
        assert "100% srgb" in gamut or "dci-p3" in gamut


def test_scenario_5_student_35k(real_catalog_laptops):
    """Scenario 5: Student & Office budget 35,000 EGP."""
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=35000.0,
        persona=PersonaType.STUDENT_AND_OFFICE,
        top_k=5,
    )

    assert result.persona == "student_and_office"
    assert len(result.results) > 0
    for item in result.results:
        assert item.effective_price_egp <= 35000.0


# =============================================================================
# 4. EDGE CASES & GRACEFUL RELAXATION
# =============================================================================
def test_low_budget_relaxation(real_catalog_laptops):
    """When budget is too low for strict gaming gates (e.g. 20,000 EGP), gates relax gracefully."""
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=25000.0,
        persona=PersonaType.GAMING,
        top_k=5,
    )
    # Should not crash or return empty; relaxes gates to show best available laptops
    assert result.gates_relaxed_for_low_budget is True
    assert len(result.results) > 0


def test_brand_filter(real_catalog_laptops):
    """Filtering by brand should only return that brand."""
    result = rank_laptops_topsis(
        laptops=real_catalog_laptops,
        max_budget_egp=100000.0,
        persona=PersonaType.BALANCED,
        brand_filter=["ASUS"],
        top_k=5,
    )
    assert len(result.results) > 0
    for item in result.results:
        assert item.brand.upper() == "ASUS"


def test_enrich_catalog_with_persona_scores(real_catalog_laptops):
    """Enriching catalog attaches hardware_fit and value_fit across all 7 personas."""
    sample_data = {"laptops": real_catalog_laptops[:10]}
    enriched = enrich_catalog_with_persona_scores(sample_data)

    for lap in enriched["laptops"]:
        ps = lap["derived_metrics"].get("persona_scores")
        assert ps is not None
        for p in PersonaType:
            assert p in ps
            assert "hardware_fit" in ps[p]
            assert "value_fit" in ps[p]
            assert 0.0 <= ps[p]["hardware_fit"] <= 100.0
            assert 0.0 <= ps[p]["value_fit"] <= 100.0


def test_get_persona_db_query_spec():
    spec = get_persona_db_query_spec("gaming", 70000.0)
    assert spec["persona_gates"]["require_dgpu"] is True
    assert spec["max_price_egp"] == 70000.0

    # Low budget relaxation check
    relaxed_spec = get_persona_db_query_spec("gaming", 25000.0)
    assert relaxed_spec["persona_gates"]["require_dgpu"] is False
