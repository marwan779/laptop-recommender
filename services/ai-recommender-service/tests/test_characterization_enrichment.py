"""Characterization tests for the review enrichment & recalibration behaviour.

These tests pin the exact pre-refactor behaviour of the enrichment pipeline with
zero network calls and zero model downloads.  All ML/LLM boundaries are faked.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

import chroma_reviews_engine as cre
import raw_reviews_enricher as rre


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

VALID_AR = "مراجعة عربية دقيقة للجهاز والمواصفات"


def _valid_profile(score: float = 80.0) -> Dict[str, Any]:
    return {
        "aspect_scores": {k: score for k in rre.ASPECT_KEYS},
        "pros_en": ["Solid cooling under sustained gaming loads", "Bright 100% sRGB display"],
        "pros_ar": [
            "نظام تبريد ممتاز وحرارة منخفضة تحت الضغط",
            "شاشة مشرقة بألوان دقيقة وتغطية كاملة",
        ],
        "cons_en": ["Fans get loud in turbo mode", "Plastic deck has some flex"],
        "cons_ar": [
            "صوت المراوح يرتفع بوضوح في وضع الأداء الأقصى",
            "خامات بلاستيكية تظهر بعض المرونة في الهيكل",
        ],
    }


def _evidence_pack() -> Dict[str, Any]:
    return {
        "chassis_key": "asus-rog-strix-scar-18",
        "doc_count": 2,
        "candidate_count": 3,
        "snippets": [
            {
                "text": "The vapor chamber keeps the CPU cool at only 78C under load.",
                "source": "YT:TestChannel",
                "aspect": "thermals_score",
                "polarity": "pro",
                "relevance": 1.4,
            },
            {
                "text": "The fans get extremely loud in turbo mode, like a jet engine.",
                "source": "YT_Comment",
                "aspect": "acoustics_score",
                "polarity": "con",
                "relevance": 1.1,
            },
        ],
        "jina_aspect_pro_mean": {k: 0.41 for k in rre.ASPECT_KEYS},
        "jina_aspect_con_mean": {k: 0.33 for k in rre.ASPECT_KEYS},
        "jina_aspect_scores_raw": {
            "thermals_score": 81.5,
            "acoustics_score": 66.4,
            "build_and_hinges_score": 88.0,
            "keyboard_and_trackpad_score": 76.2,
            "real_battery_and_reliability_score": 62.7,
        },
        "specs_summary": {
            "brand": "Asus",
            "laptop_family": "ROG Strix Scar",
            "laptop_model": "G834JY",
            "category": "gaming",
            "cpu": "Intel Core i9-13980HX",
            "gpu": "NVIDIA RTX 4090",
            "gpu_tgp_w": 175,
            "ram_gb": 32,
            "storage_gb": 2048,
            "display_panel": "Mini LED",
            "display_srgb_pct": 100,
            "battery_whr": 90,
            "chassis_material": "Aluminum",
            "verified_metal_chassis": True,
        },
    }


def _item() -> Dict[str, Any]:
    return {
        "chassis_key": "asus-rog-strix-scar-18",
        "identity": {
            "brand": "Asus",
            "laptop_family": "ROG Strix Scar",
            "laptop_model": "G834JY",
        },
        "matched_canonical_ids": ["lap_test_001"],
        "primary_canonical_id": "lap_test_001",
    }


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def test_detect_format_a_raw_with_youtube_and_communities() -> None:
    payload = {
        "laptops": [
            {
                **_item(),
                "youtube": {"videos": [{"video_id": "v1", "transcript_text": "Cooling is good."}]},
                "communities": {"reddit": [{"post_title": "Owner thread", "post_body": "Battery lasts."}]},
            }
        ]
    }
    assert rre.detect_reviews_format(payload) == "format_a_raw"


def test_detect_format_b1_enriched() -> None:
    payload = {"laptops": [{**_item(), "nlp_review_profile": _valid_profile()}]}
    assert rre.detect_reviews_format(payload) == "format_b1_enriched"


def test_detect_format_b2_deduplicated() -> None:
    payload = {"chassis_reviews": [{"chassis_key": "x"}]}
    assert rre.detect_reviews_format(payload) == "format_b2_deduplicated"


def test_detect_format_rejects_unknown_payload() -> None:
    with pytest.raises(ValueError):
        rre.detect_reviews_format({"unexpected": []})


# ---------------------------------------------------------------------------
# Candidate gathering & filtering
# ---------------------------------------------------------------------------

def test_gather_candidates_filters_noise_questions_desktop_and_brand_mismatch() -> None:
    item = {
        "chassis_key": "asus-zenbook-14",
        "identity": {"brand": "Asus", "laptop_family": "Zenbook", "laptop_model": "UX3405"},
        "youtube": {
            "videos": [
                {
                    "video_id": "v1",
                    "title": "ASUS Zenbook 14 long term review",
                    "channel_name": "NotebookCheck",
                    "transcript_source": "AUTO_CAPTIONS",
                    "transcript_text": (
                        "The aluminum chassis feels rigid and the hinges are sturdy. "
                        "Please subscribe to my channel and hit the bell for more videos. "
                        "The OLED display is bright with accurate colors and great battery life. "
                        "Can anyone help me with the fingerprint driver on Ubuntu?"
                    ),
                    "top_comments": [
                        {"comment_text": "Battery life is around ten hours of light office work.", "like_count": 12},
                        {"comment_text": "Which laptop should i get for programming?", "like_count": 3},
                    ],
                },
                {
                    "video_id": "v2",
                    "title": "Unavailable",
                    "transcript_source": "TRANSCRIPT_UNAVAILABLE",
                    "transcript_text": "The cooling is amazing and temperatures stay low.",
                },
                {
                    "video_id": "v3",
                    "title": "Synthesized",
                    "transcript_text": "[Synthesized from metadata] The keyboard is comfortable to type on.",
                },
            ]
        },
        "communities": {
            "reddit": [
                {
                    "post_title": "Experience with the Zenbook 14 after six months",
                    "post_body": "The keyboard has comfortable key travel and the trackpad is smooth glass. "
                    "Battery endurance remains excellent for travel.",
                },
                {
                    "post_title": "My new B850M motherboard and RTX desktop build",
                    "post_body": "The AM5 motherboard supports PCIe 5.0 and the desktop GPU is huge.",
                },
                {
                    "post_title": "Alienware m18 review roundup",
                    "post_body": "The Alienware laptop has a massive 18 inch display and heavy chassis.",
                },
            ],
            "discussions": [
                {
                    "post_title": "Zenbook 14 discussion",
                    "post_body": "Thermals are good and the fan noise is quiet during everyday tasks.",
                    "comments": [
                        {"comment_text": "The screen brightness is excellent outdoors at 500 nits."},
                        {"comment_text": "Is this model good for video editing?"},
                    ],
                }
            ],
        },
    }

    candidates, doc_count = rre._gather_raw_candidate_chunks(item)
    texts = " || ".join(c["text"] for c in candidates).lower()

    # Real evidence survives (transcript, comment, community post + comment).
    assert "aluminum chassis feels rigid" in texts
    assert "battery life is around ten hours" in texts
    assert "comfortable key travel" in texts
    assert "screen brightness is excellent" in texts
    assert doc_count == 3  # one YT transcript + one reddit post + one discussion post

    # Noise, desktop parts, mismatched brands, and questions are dropped.
    assert "subscribe" not in texts
    assert "hit the bell" not in texts
    assert "can anyone help" not in texts
    assert "b850m" not in texts
    assert "alienware" not in texts
    assert "video editing?" not in texts

    # Sources and weights are preserved exactly.
    sources = {c["source"] for c in candidates}
    assert "YT:NotebookCheck" in sources
    assert "YT_Comment" in sources
    assert "Comm:reddit" in sources
    assert "Comm_Cmt:discussions" in sources


def test_select_top_candidates_dedupes_and_caps() -> None:
    cands = [
        {"text": "  The cooling system keeps temperatures low under load.  ", "source": "YT:A", "source_weight": 1.15},
        {"text": "The cooling system keeps temperatures low under load.", "source": "YT:B", "source_weight": 1.0},
        {"text": "short", "source": "YT:A", "source_weight": 1.0},
    ]
    picked = rre._select_top_candidates_for_jina(cands, max_candidates=24)
    assert len(picked) == 1
    assert picked[0]["text"] == "The cooling system keeps temperatures low under load."
    assert picked[0]["source"] == "YT:A"


# ---------------------------------------------------------------------------
# Profile validation
# ---------------------------------------------------------------------------

def test_validate_enriched_profile_accepts_valid_payload() -> None:
    ok, errors = rre.validate_enriched_profile(_valid_profile())
    assert ok is True
    assert errors == []
    assert rre.is_valid_nlp_profile(_valid_profile()) is True


def test_validate_enriched_profile_rejects_score_outside_bounds() -> None:
    prof = _valid_profile()
    prof["aspect_scores"]["thermals_score"] = 99.0
    ok, errors = rre.validate_enriched_profile(prof)
    assert ok is False
    assert any("out of range" in e for e in errors)

    prof["aspect_scores"]["thermals_score"] = 34.9
    ok, errors = rre.validate_enriched_profile(prof)
    assert ok is False
    assert any("out of range" in e for e in errors)


def test_validate_enriched_profile_rejects_short_arabic() -> None:
    prof = _valid_profile()
    prof["pros_ar"][0] = "Setup مراجعة"
    ok, errors = rre.validate_enriched_profile(prof)
    assert ok is False
    assert any("Arabic chars" in e for e in errors)


def test_validate_enriched_profile_enforces_bullet_count_2_to_6() -> None:
    prof = _valid_profile()
    prof["cons_en"] = ["Only one con"]
    ok, errors = rre.validate_enriched_profile(prof)
    assert ok is False
    assert any("expected 2..6" in e for e in errors)

    prof = _valid_profile()
    prof["cons_en"] = ["A sufficiently long con sentence number one.", "A sufficiently long con sentence number two."] * 4
    ok, errors = rre.validate_enriched_profile(prof)
    assert ok is False
    assert any("expected 2..6" in e for e in errors)


# ---------------------------------------------------------------------------
# Delta hash
# ---------------------------------------------------------------------------

def test_compute_chassis_delta_hash_is_deterministic_and_sensitive() -> None:
    item = {
        **_item(),
        "youtube": {
            "videos": [
                {
                    "video_id": "v1",
                    "transcript_source": "AUTO_CAPTIONS",
                    "transcript_text": "Cooling is excellent and the fans stay quiet.",
                    "top_comments": [{"comment_text": "Battery lasts all day."}],
                },
                {
                    "video_id": "v0",
                    "transcript_source": "MANUAL",
                    "transcript_text": "The keyboard is comfortable.",
                },
            ]
        },
        "communities": {
            "reddit": [
                {"post_id": "p1", "post_title": "Owner thread", "post_body": "Sturdy metal chassis."},
                {"post_id": "p0", "post_title": "Second thread", "post_body": "Good display."},
            ]
        },
    }
    h1 = rre.compute_chassis_delta_hash(item)
    h2 = rre.compute_chassis_delta_hash(item)
    assert h1 == h2
    assert len(h1) == 64
    assert int(h1, 16) >= 0

    changed = {**item, "youtube": {"videos": [{**item["youtube"]["videos"][0], "transcript_text": "Different."}]}}
    assert rre.compute_chassis_delta_hash(changed) != h1


# ---------------------------------------------------------------------------
# LLM primary -> fallback -> zero_llm chain
# ---------------------------------------------------------------------------

def _fake_caller_factory(
    behaviours: List[Optional[Dict[str, Any]]],
    calls: List[str],
):
    def _caller(model: str, messages: List[Dict[str, str]], **kwargs: Any):
        calls.append(model)
        index = min(len(calls) - 1, len(behaviours) - 1)
        parsed = behaviours[index]
        telemetry = {
            "model": model,
            "latency_sec": 0.5,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "reasoning_tokens": 10,
            "total_tokens": 150,
            "estimated_cost_egp": 0.01,
            "http_status": 200,
            "error": None if parsed is not None else "offline",
        }
        return parsed, telemetry

    return _caller


def test_enrich_with_fallback_primary_path() -> None:
    calls: List[str] = []
    prof, tel = rre.enrich_chassis_with_fallback(
        item=_item(),
        cat_map=None,
        evidence_pack=_evidence_pack(),
        primary_model="primary-model",
        fallback_model="fallback-model",
        llm_caller=_fake_caller_factory([_valid_profile()], calls),
    )
    assert calls == ["primary-model"]
    assert tel["path_taken"] == "primary"
    assert tel["fallback_triggered"] is False
    assert tel["model_used"] == "primary-model"
    assert tel["valid"] is True
    assert prof["community_nlp_score"] == pytest.approx(80.0)
    assert set(prof["aspect_scores"]) == set(rre.ASPECT_KEYS)
    assert "Aspect Ratings ->" in prof["synthesized_review_en"]


def test_enrich_with_fallback_fallback_path() -> None:
    calls: List[str] = []
    bad = _valid_profile()
    bad["aspect_scores"]["real_battery_and_reliability_score"] = 99.0
    prof, tel = rre.enrich_chassis_with_fallback(
        item=_item(),
        cat_map=None,
        evidence_pack=_evidence_pack(),
        primary_model="primary-model",
        fallback_model="fallback-model",
        llm_caller=_fake_caller_factory([bad, _valid_profile(76.0)], calls),
    )
    assert calls == ["primary-model", "fallback-model"]
    assert tel["path_taken"] == "fallback"
    assert tel["fallback_triggered"] is True
    assert tel["model_used"] == "fallback-model"
    assert len(tel["attempts"]) == 2
    assert tel["attempts"][0]["valid"] is False
    assert tel["attempts"][1]["valid"] is True


def test_enrich_with_fallback_zero_llm_fallback_path() -> None:
    calls: List[str] = []
    prof, tel = rre.enrich_chassis_with_fallback(
        item=_item(),
        cat_map=None,
        evidence_pack=_evidence_pack(),
        primary_model="primary-model",
        fallback_model="fallback-model",
        llm_caller=_fake_caller_factory([None], calls),
    )
    assert calls == ["primary-model", "fallback-model"]
    assert tel["path_taken"] == "zero_llm_fallback"
    assert tel["fallback_triggered"] is True
    assert tel["model_used"] == "zero_llm"
    assert tel["prompt_tokens"] == 200
    assert len(tel["attempts"]) == 2
    # Raw Jina baseline is preserved inside the synthesized text for idempotency.
    assert "Thermals: 81.5/100" in prof["synthesized_review_en"]
    assert 2 <= len(prof["pros_en"]) <= 4
    assert 2 <= len(prof["cons_en"]) <= 4


def test_enrich_zero_llm_mode_stays_offline() -> None:
    calls: List[str] = []
    prof, tel = rre.enrich_chassis_with_fallback(
        item=_item(),
        cat_map=None,
        evidence_pack=_evidence_pack(),
        mode="zero_llm",
        llm_caller=_fake_caller_factory([_valid_profile()], calls),
    )
    assert calls == []
    assert tel["path_taken"] == "zero_llm"
    assert prof["aspect_scores"] == _evidence_pack()["jina_aspect_scores_raw"]


# ---------------------------------------------------------------------------
# Recalibration exact outputs
# ---------------------------------------------------------------------------

def _catalog_entry(
    *,
    integrated: bool,
    base_power_w: float,
    tgp_w: float,
    battery_hours: float,
    chassis_tier: str,
) -> Dict[str, Any]:
    return {
        "canonical_id": "lap_test_001",
        "brand": "Test",
        "laptop_family": "Test",
        "laptop_model": "Test",
        "specs": {
            "gpu": {"integrated": integrated},
            "cpu": {"base_power_w": base_power_w},
        },
        "derived_metrics": {
            "silicon": {"inferred_tgp_w": tgp_w},
            "mobility": {"battery_hours_estimate": battery_hours},
            "longevity": {"chassis_tier": chassis_tier},
        },
    }


BASE = {
    "thermals_score": 78.0,
    "acoustics_score": 78.0,
    "build_and_hinges_score": 78.0,
    "keyboard_and_trackpad_score": 78.0,
    "real_battery_and_reliability_score": 78.0,
}


def test_recalibrate_gaming_hx_dgpu_exact() -> None:
    ident = {"brand": "Asus", "laptop_family": "ROG Strix Scar", "laptop_model": "G834JY"}
    cat = {"lap_test_001": _catalog_entry(integrated=False, base_power_w=55.0, tgp_w=175.0, battery_hours=4.0, chassis_tier="Metal")}
    out = cre._recalibrate_item(ident, ["lap_test_001"], "lap_test_001", dict(BASE), cat)
    assert out == {
        "community_nlp_score": 75.9,
        "aspect_scores": {
            "thermals_score": 78.8,
            "acoustics_score": 72.5,
            "build_and_hinges_score": 89.0,
            "keyboard_and_trackpad_score": 78.8,
            "real_battery_and_reliability_score": 48.8,
        },
    }


def test_recalibrate_igpu_ultrabook_exact() -> None:
    ident = {"brand": "Asus", "laptop_family": "Zenbook 14", "laptop_model": "UX3405"}
    cat = {"lap_test_001": _catalog_entry(integrated=True, base_power_w=15.0, tgp_w=0.0, battery_hours=10.0, chassis_tier="Metal")}
    out = cre._recalibrate_item(ident, ["lap_test_001"], "lap_test_001", {k: 80.0 for k in BASE}, cat)
    assert out == {
        "community_nlp_score": 84.77,
        "aspect_scores": {
            "thermals_score": 81.2,
            "acoustics_score": 81.2,
            "build_and_hinges_score": 89.0,
            "keyboard_and_trackpad_score": 81.2,
            "real_battery_and_reliability_score": 92.0,
        },
    }


def test_recalibrate_metal_chassis_exact() -> None:
    ident = {"brand": "Lenovo", "laptop_family": "ThinkBook 14", "laptop_model": "G6"}
    cat = {"lap_test_001": _catalog_entry(integrated=True, base_power_w=28.0, tgp_w=0.0, battery_hours=5.5, chassis_tier="Metal")}
    out = cre._recalibrate_item(ident, ["lap_test_001"], "lap_test_001", {k: 70.0 for k in BASE}, cat)
    assert out == {
        "community_nlp_score": 72.47,
        "aspect_scores": {
            "thermals_score": 68.8,
            "acoustics_score": 68.8,
            "build_and_hinges_score": 89.0,
            "keyboard_and_trackpad_score": 68.8,
            "real_battery_and_reliability_score": 59.6,
        },
    }


def test_recalibrate_plastic_budget_laptop_exact() -> None:
    ident = {"brand": "Acer", "laptop_family": "Aspire 3", "laptop_model": "A315"}
    cat = {"lap_test_001": _catalog_entry(integrated=True, base_power_w=15.0, tgp_w=0.0, battery_hours=6.0, chassis_tier="Plastic")}
    out = cre._recalibrate_item(ident, ["lap_test_001"], "lap_test_001", {k: 80.0 for k in BASE}, cat)
    assert out == {
        "community_nlp_score": 76.08,
        "aspect_scores": {
            "thermals_score": 81.2,
            "acoustics_score": 81.2,
            "build_and_hinges_score": 71.5,
            "keyboard_and_trackpad_score": 81.2,
            "real_battery_and_reliability_score": 63.2,
        },
    }


def test_recalibrate_without_catalog_uses_defaults() -> None:
    out = cre._recalibrate_item({}, [], None, dict(BASE), {})
    assert out == {
        "community_nlp_score": 75.92,
        "aspect_scores": {
            "thermals_score": 78.8,
            "acoustics_score": 78.8,
            "build_and_hinges_score": 78.8,
            "keyboard_and_trackpad_score": 78.8,
            "real_battery_and_reliability_score": 59.6,
        },
    }


# ---------------------------------------------------------------------------
# Baseline extraction / synthesized text
# ---------------------------------------------------------------------------

def test_extract_baseline_aspects_prefers_synthesized_text() -> None:
    prof = {
        "synthesized_review_en": (
            "Aspect Ratings -> Thermals: 81.5/100, Fan Noise/Acoustics: 66.4/100, "
            "Chassis Build & Hinges: 88.0/100, Keyboard & Trackpad: 76.2/100, "
            "Real Battery & Reliability: 62.7/100."
        ),
        "aspect_scores": {k: 50.0 for k in BASE},
    }
    out = cre._extract_baseline_aspects(prof, prof["aspect_scores"])
    assert out == _evidence_pack()["jina_aspect_scores_raw"]


def test_extract_baseline_aspects_falls_back() -> None:
    out = cre._extract_baseline_aspects({}, {"thermals_score": 70.0})
    assert out["thermals_score"] == 70.0
    assert out["acoustics_score"] == 78.0


def test_build_synthesized_texts_exact_format() -> None:
    en, ar = rre._build_synthesized_texts(
        model_label="G834JY",
        specs={"cpu": "i9", "gpu": "RTX 4090"},
        base_aspects=BASE,
        pros_en=["pro one"],
        pros_ar=["ميزة أولى"],
        cons_en=["con one"],
        cons_ar=["عيب أول"],
    )
    assert en == (
        "Technical Review Summary for G834JY (i9, RTX 4090): "
        "Pros: pro one. Cons & Trade-offs: con one. "
        "Aspect Ratings -> Thermals: 78.0/100, Fan Noise/Acoustics: 78.0/100, "
        "Chassis Build & Hinges: 78.0/100, Keyboard & Trackpad: 78.0/100, "
        "Real Battery & Reliability: 78.0/100."
    )
    assert ar == (
        "ملخص المراجعة العملية وتجربة الاستخدام لجهاز G834JY: "
        "المميزات العملية: ميزة أولى. العيوب والملاحظات: عيب أول."
    )


# ---------------------------------------------------------------------------
# Sealed Format A `specs` envelope fallback (new laptops absent from cat_map)
# ---------------------------------------------------------------------------

def _format_a_specs_envelope() -> Dict[str, Any]:
    return {
        "identity": {"primary_category": "gaming"},
        "cpu": {"raw": "Intel Core i9-14900HX", "model": "Core i9-14900HX", "base_power_w": 55},
        "gpu": {"raw": "GeForce RTX 4080", "model": "GeForce RTX 4080", "tgp_watts": 175, "integrated": False},
        "memory": {"capacity_gb": 32, "upgradeable": True, "max_supported_gb": 64},
        "storage": {"capacity_gb": 1000, "slot_count": 2},
        "display": {
            "size_inches": 16.0,
            "panel_type": "IPS",
            "refresh_rate_hz": 240,
            "brightness_nits": 500,
            "srgb_percent": 100.0,
            "color_gamut": "100% sRGB",
        },
        "battery": {"capacity_whr": 90.0},
        "derived_metrics": {
            "silicon": {"inferred_tgp_w": 175.0},
            "display": {"color_gamut_tier": "100% sRGB"},
            "mobility": {"weight_kg": 2.5, "battery_whr": 90.0, "battery_hours_estimate": 4.0},
            "longevity": {"total_m2_slots": 2, "max_ram_gb": 64, "chassis_tier": "Metal"},
        },
    }


def test_format_catalog_specs_summary_falls_back_to_item_specs_envelope() -> None:
    item = {
        "chassis_key": "asus:rog:G634JZR",
        "primary_canonical_id": "new-unseen-sku",
        "matched_canonical_ids": ["new-unseen-sku"],
        "identity": {"brand": "Asus", "laptop_family": "ROG Strix", "laptop_model": "G634JZR"},
        "specs": _format_a_specs_envelope(),
    }

    summary = rre._format_catalog_specs_summary(item, cat_map=None)

    assert summary["brand"] == "Asus"
    assert summary["category"] == "gaming"
    assert summary["cpu"] == "Intel Core i9-14900HX"
    assert summary["gpu"] == "GeForce RTX 4080"
    assert summary["gpu_tgp_w"] == 175
    assert summary["ram_gb"] == 32
    assert summary["storage_gb"] == 1000
    assert summary["display_hz"] == 240
    assert summary["display_srgb_pct"] == 100.0
    assert summary["battery_whr"] == 90.0
    assert summary["weight_kg"] == 2.5


def test_recalibrate_uses_item_specs_envelope_when_absent_from_catalog() -> None:
    ident = {"brand": "Asus", "laptop_family": "ROG Strix", "laptop_model": "G834JY"}
    out = cre._recalibrate_item(
        ident,
        ["new-unseen-sku"],
        "new-unseen-sku",
        dict(BASE),
        {},
        item_specs=_format_a_specs_envelope(),
    )
    assert out == {
        "community_nlp_score": 75.9,
        "aspect_scores": {
            "thermals_score": 78.8,
            "acoustics_score": 72.5,
            "build_and_hinges_score": 89.0,
            "keyboard_and_trackpad_score": 78.8,
            "real_battery_and_reliability_score": 48.8,
        },
    }


def test_finalize_profile_recalibrates_with_item_specs_even_without_cat_map() -> None:
    item = {
        "chassis_key": "asus:rog:G834JY",
        "primary_canonical_id": "new-unseen-sku",
        "matched_canonical_ids": ["new-unseen-sku"],
        "identity": {"brand": "Asus", "laptop_family": "ROG Strix", "laptop_model": "G834JY"},
        "specs": _format_a_specs_envelope(),
    }

    prof = rre._finalize_profile_with_recalibration(
        item=item,
        base_aspects=dict(BASE),
        pros_en=["Strong RTX 4080 sustained TGP.", "Clean 240Hz display calibration."],
        pros_ar=["أداء قوي ومستقر مع كارت الشاشة.", "شاشة ممتازة بمعدل تحديث 240Hz."],
        cons_en=["Audible fans in Turbo mode.", "Heavy 2.5kg gaming chassis."],
        cons_ar=["صوت المراوح مرتفع في وضع الأداء العالي.", "وزن الجهاز ثقيل نسبياً للتنقل."],
        evidence_count=8,
        cat_map=None,
    )

    assert prof["community_nlp_score"] == 75.9
    assert prof["aspect_scores"]["acoustics_score"] == 72.5
    assert prof["aspect_scores"]["real_battery_and_reliability_score"] == 48.8
    assert "Intel Core i9-14900HX" in prof["synthesized_review_en"]
