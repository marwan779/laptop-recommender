"""Pure unit tests for recommendation (TOPSIS + workloads) and metrics domain layers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

from app.domain.metrics import compute_laptop_metrics
from app.domain.recommendation import (
    apply_persona_scores_to_catalog,
    evaluate_workloads,
    parse_user_text_prompt,
    rank_laptops_topsis,
)
from app.services.recommendation_service import RecommendationService


def _sample_laptop(
    *,
    cid: str,
    cpu_model: str = "Core i7-13650HX",
    gpu_model: str = "GeForce RTX 4060",
    integrated: bool = False,
    vram_gb: int = 8,
    tdp_w: float = 115.0,
    ram_gb: int = 16,
    price_egp: float = 55000.0,
    refresh_hz: int = 165,
) -> Dict[str, Any]:
    return {
        "canonical_id": cid,
        "brand": "Lenovo",
        "laptop_family": "Legion 5",
        "laptop_model": "16IRX9",
        "title": f"Lenovo Legion 5 ({cid})",
        "cheapest_store": "Sigma",
        "available_stores": ["Sigma", "CompuMarts"],
        "price_spread_egp": 2500.0,
        "specs": {
            "identity": {"release_year": 2024},
            "cpu": {
                "manufacturer": "Intel",
                "line": "Core i7",
                "model": cpu_model,
                "cores": 14,
                "threads": 20,
                "clock_boost_ghz": 4.9,
                "base_power_w": 55.0,
            },
            "gpu": {
                "manufacturer": "Intel" if integrated else "NVIDIA",
                "model": gpu_model,
                "integrated": integrated,
                "vram_gb": 0 if integrated else vram_gb,
                "tdp_w": tdp_w,
            },
            "memory": {
                "capacity_gb": ram_gb,
                "memory_type": "DDR5",
                "speed": "4800 MHz",
                "slot_count": 2,
                "max_supported_gb": 64,
            },
            "storage": {
                "capacity_gb": 1024,
                "interface": "PCIe 4.0 NVMe",
                "slot_count": 2,
            },
            "display": {
                "size_inches": 16.0,
                "resolution_width": 2560,
                "resolution_height": 1600,
                "refresh_rate_hz": refresh_hz,
                "panel_type": "IPS",
                "color_gamut": "100% sRGB",
            },
            "power_battery": {"battery_capacity_wh": 80.0, "power_adapter_w": 230.0},
            "physical": {"weight_kg": 2.35, "height_mm": 21.9},
            "build_security": {"has_backlit_keyboard": True, "has_fingerprint": False},
            "audio_webcam": {"webcam_resolution": "1080p", "speaker_count": 2},
            "connectivity": {"wifi": "Wi-Fi 6E", "ethernet": True, "ports": ["2x USB-C", "3x USB-A", "HDMI 2.1"]},
        },
        "offers": [{"is_valid_price": True, "in_stock": True, "price_egp": price_egp}],
    }


def test_metrics_domain_computes_all_sections_purely() -> None:
    laptop = _sample_laptop(cid="legion-4060")
    metrics = compute_laptop_metrics(laptop)

    ti = metrics["topsis_inputs"]
    assert ti["in_stock_active"] is True
    assert ti["effective_price_egp"] == 55000.0
    assert 0.0 < ti["cpu_score"] <= 100.0
    assert 0.0 < ti["gpu_score"] <= 100.0
    assert metrics["power"]["electrical_status"] == "UNCONSTRAINED_HEADROOM"
    assert metrics["longevity"]["upgradeability_tier"] == "MAXIMUM_UPGRADEABLE"


def test_topsis_and_workloads_rank_candidates_deterministically() -> None:
    gaming_lap = _sample_laptop(cid="lap-gaming", price_egp=62000.0)
    office_lap = _sample_laptop(
        cid="lap-office",
        cpu_model="Core i5-1335U",
        gpu_model="Intel Iris Xe Graphics",
        integrated=True,
        vram_gb=0,
        tdp_w=15.0,
        price_egp=32000.0,
        refresh_hz=60,
    )
    for lap in (gaming_lap, office_lap):
        lap["derived_metrics"] = compute_laptop_metrics(lap)

    parsed = parse_user_text_prompt(" عايز لاب 16gb للألعاب والتبريد القوي ")
    assert parsed["extracted_filters"]["min_ram_gb"] == 16
    assert "gpu_score" in parsed["weight_boosts"]

    ranked = rank_laptops_topsis(
        laptops=[gaming_lap, office_lap],
        max_budget_egp=70000.0,
        persona="gaming",
        user_text_prompt="ألعاب وتبريد قوي",
        top_k=5,
    )
    assert len(ranked["results"]) == 1
    assert ranked["results"][0]["canonical_id"] == "lap-gaming"
    assert ranked["results"][0]["topsis_match_score"] == 100.0

    workloads = evaluate_workloads(gaming_lap)
    assert len(workloads["games_1080p"]) == 6
    assert len(workloads["software_benchmarks"]) == 6
    assert len(workloads["career_tracks"]) == 5

    catalog_with_personas = apply_persona_scores_to_catalog({"laptops": [gaming_lap, office_lap]})
    assert "gaming" in catalog_with_personas["laptops"][0]["derived_metrics"]["persona_scores"]


def test_recommendation_service_end_to_end_without_disk_or_chroma(tmp_path: Path) -> None:
    from app.services.recommendation_service import LaptopRecommenderService

    # Isolate singleton for unit testing without loading ./chroma_reviews_db or JSON snapshots.
    prev_instance = LaptopRecommenderService._instance
    LaptopRecommenderService._instance = None
    try:
        recommender = LaptopRecommenderService(
            chroma_dir=str(tmp_path / "missing_chroma"),
            catalog_fallback_path=str(tmp_path / "missing_catalog.json"),
            reviews_fallback_path=str(tmp_path / "missing_reviews.json"),
        )
        svc = RecommendationService(recommender=recommender)

        lap = _sample_laptop(cid="lap-1", price_egp=52000.0)
        lap["derived_metrics"] = compute_laptop_metrics(lap)

        res = svc.recommend(
            laptops=[lap],
            max_budget_egp=60000.0,
            persona="gaming",
            include_workloads=True,
        )
        assert res["status"] == "OK"
        assert res["results"][0]["canonical_id"] == "lap-1"
        assert "workloads" in res["results"][0]
    finally:
        LaptopRecommenderService._instance = prev_instance


def test_domain_layer_has_no_framework_or_io_client_imports() -> None:
    domain_root = Path(__file__).resolve().parent.parent / "app" / "domain"
    forbidden = {
        "fastapi",
        "starlette",
        "sqlalchemy",
        "asyncpg",
        "httpx",
        "requests",
        "boto3",
        "botocore",
        "aio_pika",
        "redis",
        "chromadb",
        "sentence_transformers",
        "torch",
    }
    for py_file in domain_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, f"{py_file} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, f"{py_file} imports {node.module}"
