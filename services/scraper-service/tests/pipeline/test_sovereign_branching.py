"""Tests for post-Level-1 Pipeline A / Pipeline B branching and isolation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.core.sovereign_config import SovereignConfig
from app.domain.catalog.sovereign_prompt import should_use_sovereign_pipeline
from app.infrastructure.sovereigneg_client import CallTelemetry
from app.pipeline.icecat.enricher import IcecatCatalogEnricher
from app.pipeline.schema import empty_laptop_specifications
from app.pipeline.sovereign_pipeline import SovereignSmallBatchPipeline
from app.schemas.laptop import RetailerProduct
from app.schemas.orchestrator import ScrapeRequest
from app.services.orchestrator import ScrapeOrchestrator


def _sample_product(idx: int, *, store_key: str = "compumarts") -> RetailerProduct:
    return RetailerProduct(
        store_name="Compumarts" if store_key == "compumarts" else "Sigma Computer",
        store_key=store_key,
        store_domain=f"{store_key}.com",
        title=f"Lenovo IdeaPad Slim 3 {idx} - Core i5-13420H, 16GB RAM DDR5, 512GB SSD",
        product_url=f"https://{store_key}.com/products/lenovo-ideapad-{idx}",
        price_egp=29000.0 + idx,
        in_stock=True,
        mpn=f"83K10{idx}ERED",
        specs={
            "Processor": "Intel Core i5-13420H",
            "Memory": "16GB DDR5 4800Hz | Max Memory: Not upgradable",
            "Storage": "512GB SSD M.2 2242",
            "Display": "15.3 inch WUXGA IPS",
        },
        raw_description="16GB DDR5 4800Hz, Not upgradable.",
    )


def test_branching_predicate_rules() -> None:
    assert should_use_sovereign_pipeline(0, threshold=60, has_key=True, mode="auto") is True
    assert should_use_sovereign_pipeline(55, threshold=60, has_key=True, mode="auto") is True
    assert should_use_sovereign_pipeline(60, threshold=60, has_key=True, mode="auto") is True
    assert should_use_sovereign_pipeline(61, threshold=60, has_key=True, mode="auto") is False
    assert should_use_sovereign_pipeline(10, threshold=60, has_key=False, mode="auto") is False
    assert should_use_sovereign_pipeline(10, threshold=60, has_key=False, mode="sovereign") is False
    assert should_use_sovereign_pipeline(120, threshold=60, has_key=True, mode="sovereign") is True
    assert should_use_sovereign_pipeline(5, threshold=60, has_key=True, mode="legacy") is False


def test_orchestrator_routes_small_batch_after_combiner_without_onnx(tmp_path) -> None:
    # Two overlapping store listings combine into 1 unique laptop -> <= threshold (1) selects Pipeline B!
    comp_item = _sample_product(1, store_key="compumarts")
    sigma_item = _sample_product(1, store_key="sigma")

    mock_comp = MagicMock()
    mock_comp.store_name = "Compumarts"
    mock_comp.store_key = "compumarts"
    mock_comp.base_domain = "compumarts.com"
    mock_comp.scrape_catalog.return_value = [comp_item]
    mock_comp.skipped_laptops = []

    mock_sigma = MagicMock()
    mock_sigma.store_name = "Sigma Computer"
    mock_sigma.store_key = "sigma"
    mock_sigma.base_domain = "sigma-computer.com"
    mock_sigma.scrape_catalog.return_value = [sigma_item]
    mock_sigma.skipped_laptops = []

    cfg = SovereignConfig(
        base_url="https://backend.sovereigneg.com/v1",
        primary_api_key="key-1",
        fallback_api_key="key-2",
        batch_threshold=1,  # Raw count is 2 (>1), combined unique count is 1 (<=1) -> Pipeline B wins!
        micro_batch_size=2,
        max_concurrency=2,
    )

    mock_client = MagicMock()
    extracted_specs = empty_laptop_specifications()
    extracted_specs["cpu"]["model"] = "Core i5-13420H"
    extracted_specs["memory"]["capacity_gb"] = 16
    extracted_specs["memory"]["is_soldered"] = True
    extracted_specs["memory"]["max_supported_gb"] = 16
    mock_client.complete_json.return_value = (
        extracted_specs,
        CallTelemetry(model_used="claude-haiku-5.5", key_slot_used="primary", prompt_tokens=100, completion_tokens=50),
    )

    mock_enricher = MagicMock(spec=IcecatCatalogEnricher)
    mock_enricher.matches_cache = {}
    mock_enricher.search_service = MagicMock()
    mock_enricher.search_service.match_laptop.return_value = {"match_status": "NOT_FOUND"}

    out_dir = tmp_path / "out"
    orchestrator = ScrapeOrchestrator(
        email_service=MagicMock(),
        upload_to_bucket=False,
        no_audit=False,
        sovereign_config=cfg,
        sovereign_pipeline_factory=lambda c, d: SovereignSmallBatchPipeline(
            config=c,
            client=mock_client,
            icecat_enricher=mock_enricher,
            cache_path=d / "sovereign_extract_cache.json",
            allow_live_icecat_search=False,
        ),
    )

    req = ScrapeRequest(
        target_type="store",
        targets=["compumarts", "sigma"],
        level=2,
        output_dir=str(out_dir),
        upload_to_bucket=False,
        send_email=False,
    )

    def _get_store(k, _eng):
        return mock_comp if k == "compumarts" else mock_sigma

    with (
        patch("app.services.orchestrator.get_store_scraper", side_effect=_get_store),
        patch("app.services.orchestrator.setup_ai_fallback") as mock_onnx_setup,
    ):
        res = orchestrator.execute(req)

    # Combined unique count is 1 (<= threshold 1), even though raw count was 2 -> ONNX never loaded!
    assert mock_comp.scrape_catalog.call_args.kwargs["level"] == 2
    assert mock_sigma.scrape_catalog.call_args.kwargs["level"] == 2
    mock_onnx_setup.assert_not_called()
    assert mock_client.complete_json.call_count == 1
    assert res.unified_total_laptops == 1
    assert (out_dir / "sovereign_extract_cache.json").is_file()
    assert (out_dir / "unified_catalog_latest.json").is_file()


def test_orchestrator_routes_large_batch_to_legacy_pipeline_a(tmp_path) -> None:
    l1_items = [_sample_product(i) for i in range(5)]
    mock_scraper = MagicMock()
    mock_scraper.store_name = "Compumarts"
    mock_scraper.store_key = "compumarts"
    mock_scraper.base_domain = "compumarts.com"
    mock_scraper.scrape_catalog.return_value = l1_items
    mock_scraper.hydrate_products_level2.return_value = l1_items
    mock_scraper.skipped_laptops = []

    cfg = SovereignConfig(
        base_url="https://backend.sovereigneg.com/v1",
        primary_api_key="key-1",
        batch_threshold=3,
    )

    sovereign_factory = MagicMock()
    orchestrator = ScrapeOrchestrator(
        email_service=MagicMock(),
        upload_to_bucket=False,
        no_audit=False,
        ai_type="none",
        sovereign_config=cfg,
        sovereign_pipeline_factory=sovereign_factory,
    )
    req = ScrapeRequest(
        target_type="store",
        targets=["compumarts"],
        level=2,
        output_dir=str(tmp_path / "out_large"),
        upload_to_bucket=False,
        send_email=False,
    )

    with (
        patch("app.services.orchestrator.get_store_scraper", return_value=mock_scraper),
        patch("app.pipeline.icecat.enricher.IcecatCatalogEnricher.enrich_catalog", side_effect=lambda c: c) as mock_ice,
    ):
        res = orchestrator.execute(req)

    sovereign_factory.assert_not_called()
    mock_ice.assert_called_once()
    assert res.unified_total_laptops is not None and res.unified_total_laptops >= 1


def test_sovereign_pipeline_cache_isolation_and_per_item_fallback(tmp_path) -> None:
    icecat_cache_file = tmp_path / "icecat_specs_cache.json"
    sentinel_llm_cache = {"existing_id": {"verification_status": "LLM_EXTRACTED", "specs": {"sentinel": True}}}
    icecat_cache_file.write_text(
        json.dumps({"matches": {}, "specs_by_id": {}, "llm_cache": sentinel_llm_cache}),
        encoding="utf-8",
    )

    cfg = SovereignConfig(primary_api_key="k1", micro_batch_size=1, max_concurrency=1)
    mock_client = MagicMock()
    extracted = empty_laptop_specifications()
    extracted["memory"]["capacity_gb"] = 16
    extracted["memory"]["is_soldered"] = True

    # First item succeeds, second item returns None -> fail-open per item
    mock_client.complete_json.side_effect = [
        (extracted, CallTelemetry(model_used="claude-haiku-5.5", key_slot_used="primary")),
        (None, CallTelemetry(error="all_models_and_keys_failed")),
    ]

    pipeline = SovereignSmallBatchPipeline(
        config=cfg,
        client=mock_client,
        cache_path=tmp_path / "sovereign_extract_cache.json",
        allow_live_icecat_search=False,
    )

    p1 = _sample_product(1)
    p2 = RetailerProduct(
        store_name="Sigma Computer",
        store_key="sigma",
        store_domain="sigma-computer.com",
        title="HP Victus 15 FA1093DX Gaming Laptop - Core i7-13700H, 16GB RAM, RTX 4050 6GB",
        product_url="https://sigma.com/products/hp-victus-15-fa1093dx",
        price_egp=42000.0,
        in_stock=True,
        mpn="FA1093DX",
        specs={
            "Processor": "Intel Core i7-13700H",
            "Memory": "16GB DDR4 3200MHz",
            "Graphics": "NVIDIA GeForce RTX 4050 6GB",
            "Storage": "512GB NVMe SSD",
            "Display": "15.6 inch FHD IPS 144Hz",
        },
        raw_description="HP Victus 15 RTX 4050",
    )
    s1, _ = pipeline.run_lightweight_store_pipeline([p1], "compumarts")
    s2, _ = pipeline.run_lightweight_store_pipeline([p2], "sigma")
    store_cats = [
        {"store_key": "compumarts", "structured_products": s1, "latest_pointers": [p1.title]},
        {"store_key": "sigma", "structured_products": s2, "latest_pointers": [p2.title]},
    ]

    unified = pipeline.run(store_cats, out_dir=tmp_path)
    assert pipeline.last_summary.llm_extracted == 1
    assert pipeline.last_summary.fallback_count == 1
    assert len(unified.laptops) == 2

    # Second run with identical inputs hits sovereign_extract_cache for the first extracted laptop
    mock_client.complete_json.reset_mock(side_effect=True)
    mock_client.complete_json.side_effect = None
    mock_client.complete_json.return_value = (None, CallTelemetry(error="still_offline"))
    pipeline.run(store_cats, out_dir=tmp_path)
    assert pipeline.last_summary.cache_hits == 1
    assert mock_client.complete_json.call_count == 1

    # Icecat's llm_cache remained completely untouched
    ice_after = json.loads(icecat_cache_file.read_text(encoding="utf-8"))
    assert ice_after["llm_cache"] == sentinel_llm_cache
