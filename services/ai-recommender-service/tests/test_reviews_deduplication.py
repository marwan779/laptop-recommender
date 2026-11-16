"""Unit tests for Clean Architecture review deduplication, gap reports, and Jina embedder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock

from app.domain.reviews.deduplication import (
    audit_and_deduplicate_payload,
    dedup_chunks_cosine,
    format_youtube_gap_tasks_md,
)
from app.infrastructure.jina_embedder import JinaV3EmbeddingFunction
from app.services.reviews_audit_service import run_audit_and_dedup


def test_dedup_chunks_cosine_drops_exact_and_near_duplicates() -> None:
    chunks = [
        {"text": "The cooling fans stay remarkably quiet even under sustained heavy gaming workloads.", "polarity": "pro"},
        {"text": "The cooling   fans stay remarkably quiet even under sustained heavy gaming workloads.", "polarity": "pro"},
        {"text": "The cooling fans stay remarkably quiet even during sustained heavy gaming workloads.", "polarity": "pro"},
        {"text": "Battery drains quickly when rendering video on battery.", "polarity": "con"},
    ]

    kept, exact_rem, near_rem = dedup_chunks_cosine(chunks, threshold=0.90)

    assert len(kept) == 2
    assert exact_rem == 1
    assert near_rem == 1


def test_audit_and_deduplicate_payload_preserves_scores_and_generates_gap_plan() -> None:
    reviews_payload = {
        "laptops": [
            {
                "chassis_key": "lenovo:loq:15irx9",
                "primary_canonical_id": "cid-loq-1",
                "matched_canonical_ids": ["cid-loq-1"],
                "identity": {
                    "brand": "Lenovo",
                    "laptop_family": "LOQ",
                    "laptop_model": "LOQ 15IRX9",
                },
                "youtube": {"videos": []},
                "communities": {
                    "editorial": [
                        {
                            "source": "LaptopMag",
                            "review_url": "https://example.com/loq-review",
                            "pros": ["Strong cooling thermals under sustained gaming."],
                            "cons": ["Plastic chassis flexes slightly near the keyboard."],
                            "verdict": "Great value gaming laptop with average battery endurance.",
                        }
                    ],
                    "discussions": [],
                },
                "nlp_review_profile": {
                    "community_nlp_score": 84.5,
                    "aspect_scores": {
                        "thermals_score": 86.0,
                        "acoustics_score": 78.0,
                        "build_and_hinges_score": 74.0,
                        "keyboard_and_trackpad_score": 80.0,
                        "real_battery_and_reliability_score": 68.0,
                    },
                    "pros_en": ["Strong cooling thermals under sustained gaming."],
                    "pros_ar": ["تبريد قوي تحت الضغط المستمر."],
                    "cons_en": ["Average battery life when unplugged."],
                    "cons_ar": ["عمر البطارية متوسط خارج الشاحن."],
                },
            }
        ]
    }
    catalog_payload = {
        "laptops": [
            {"canonical_id": "cid-loq-1", "brand": "Lenovo", "laptop_family": "LOQ", "laptop_model": "LOQ 15IRX9"},
            {"canonical_id": "cid-missing", "brand": "HP", "laptop_family": "Victus", "laptop_model": "Victus 15"},
        ]
    }

    output = audit_and_deduplicate_payload(reviews_payload, catalog_payload)

    assert len(output["chassis_reviews"]) == 2
    loq_entry = next(c for c in output["chassis_reviews"] if c["chassis_key"] == "lenovo:loq:15irx9")
    assert loq_entry["community_nlp_score"] == 84.5
    assert loq_entry["aspect_scores"]["thermals_score"] == 86.0
    assert loq_entry["audit_metrics"]["exact_duplicates_removed"] == 1

    md = format_youtube_gap_tasks_md(output)
    assert "# 3-Person YouTube Review Search & Gap Fill Plan" in md
    assert "cid-missing" in md


def test_run_audit_and_dedup_writes_json_and_markdown(tmp_path: Path) -> None:
    rev_path = tmp_path / "b1.json"
    cat_path = tmp_path / "cat.json"
    dedup_path = tmp_path / "b2.json"
    md_path = tmp_path / "gap.md"

    rev_path.write_text(
        json.dumps(
            {
                "laptops": [
                    {
                        "chassis_key": "asus:vivobook:16",
                        "primary_canonical_id": "cid-1",
                        "matched_canonical_ids": ["cid-1"],
                        "identity": {"brand": "ASUS", "laptop_family": "Vivobook", "laptop_model": "Vivobook 16"},
                        "youtube": {"videos": []},
                        "communities": {"editorial": [], "discussions": []},
                        "nlp_review_profile": {
                            "community_nlp_score": 79.0,
                            "aspect_scores": {"thermals_score": 76.0},
                            "pros_en": ["Bright IPS display for office work."],
                            "pros_ar": ["شاشة IPS ساطعة للعمل المكتبي."],
                            "cons_en": ["Limited discrete GPU gaming performance."],
                            "cons_ar": ["أداء الألعاب محدود بدون كارت منفصل."],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cat_path.write_text(
        json.dumps({"laptops": [{"canonical_id": "cid-1", "brand": "ASUS", "laptop_model": "Vivobook 16"}]}),
        encoding="utf-8",
    )

    result = run_audit_and_dedup(
        reviews_in=str(rev_path),
        catalog_in=str(cat_path),
        dedup_out=str(dedup_path),
        tasks_md_out=str(md_path),
    )

    assert dedup_path.exists()
    assert md_path.exists()
    assert len(result["chassis_reviews"]) == 1
    assert result["chassis_reviews"][0]["community_nlp_score"] == 79.0


def test_jina_embedder_passes_lowercase_prompt_name(monkeypatch: Any) -> None:
    fake_model = MagicMock()
    fake_vecs = MagicMock()
    fake_vecs.tolist.return_value = [[0.1, 0.2, 0.3]]
    fake_model.encode.return_value = fake_vecs
    monkeypatch.setattr(JinaV3EmbeddingFunction, "_model_instance", fake_model)
    monkeypatch.setattr(JinaV3EmbeddingFunction, "__init__", lambda self, model_name="", task="retrieval.passage": setattr(self, "task", task))

    fn = JinaV3EmbeddingFunction(model_name="fake", task="retrieval.passage")
    out: List[List[float]] = fn(["Good thermal cooling"])

    assert len(out) == 1
    encode_kwargs = fake_model.encode.call_args.kwargs
    assert encode_kwargs["prompt_name"] == "retrieval.passage"
    assert "Prompt_name" not in encode_kwargs


def test_audit_and_dedup_preserves_compact_review_sources() -> None:
    reviews_data = {
        "laptops": [
            {
                "chassis_key": "asus:tuf:a16",
                "primary_canonical_id": "cid-a16",
                "matched_canonical_ids": ["cid-a16"],
                "identity": {"brand": "ASUS", "laptop_family": "TUF", "laptop_model": "TUF A16"},
                "youtube": {
                    "videos": [
                        {
                            "video_id": "v1",
                            "title": "ASUS TUF A16 Full Review",
                            "channel_name": "Crimson Tech",
                            "channel_url": "https://www.youtube.com/@crimsontechyt",
                            "video_url": "https://www.youtube.com/watch?v=A0Qui0XNn7Q",
                            "view_count": 306267,
                            "published_at": "2025-05-01T10:00:00Z",
                            "transcript_text": "Cool gaming laptop with great thermals.",
                            "top_comments": [{"comment_text": "Solid laptop overall for the price!"}],
                        },
                        {
                            "video_id": "v1-dup",
                            "title": "Duplicate URL",
                            "video_url": "https://www.youtube.com/watch?v=A0Qui0XNn7Q/",
                            "view_count": 100,
                        },
                        {
                            "video_id": "v-bad",
                            "title": "Invalid scheme",
                            "video_url": "javascript:alert(1)",
                        },
                    ]
                },
                "communities": {
                    "editorial": [
                        {
                            "source": "Notebookcheck",
                            "review_url": "https://www.notebookcheck.net/asus-tuf-a16-review.1234.0.html",
                            "rating": 86.5,
                            "verdict": "Well balanced mid-range gaming notebook.",
                            "pros": ["Low fan noise"],
                            "cons": ["Average speakers"],
                        }
                    ],
                    "discussions": [
                        {
                            "platform": "level1techs",
                            "post_id": "3947688",
                            "author": "letio",
                            "post_title": "Battery charge limit question",
                            "post_url": "https://forum.level1techs.com/t/tuf-a16/226768/1",
                            "post_body": "Full discussion body that should not bloat review_sources.",
                            "score": 14,
                            "published_at": "2025-02-28T22:44:18Z",
                        }
                    ],
                },
                "nlp_review_profile": {
                    "community_nlp_score": 81.2,
                    "pros_en": ["Quiet fans"],
                    "pros_ar": ["مراوح هادئة"],
                    "cons_en": ["Average speakers"],
                    "cons_ar": ["سماعات متوسطة"],
                },
            }
        ]
    }

    out = audit_and_deduplicate_payload(
        reviews_data=reviews_data,
        catalog_data={"laptops": [{"canonical_id": "cid-a16", "brand": "ASUS", "laptop_model": "TUF A16"}]},
        include_unmatched_catalog=False,
    )

    assert len(out["chassis_reviews"]) == 1
    sources = out["chassis_reviews"][0]["review_sources"]
    assert [s["source_type"] for s in sources] == ["editorial", "youtube", "community"]

    assert sources[0]["platform"] == "notebookcheck"
    assert sources[0]["rating"] == 86.5
    assert sources[1]["title"] == "ASUS TUF A16 Full Review"
    assert sources[1]["author_or_channel"] == "Crimson Tech"
    assert sources[1]["channel_url"] == "https://www.youtube.com/@crimsontechyt"
    assert sources[1]["score_or_views"] == 306267
    assert "transcript_text" not in sources[1]
    assert sources[2]["platform"] == "level1techs"
    assert sources[2]["score_or_views"] == 14
    assert "post_body" not in sources[2]
