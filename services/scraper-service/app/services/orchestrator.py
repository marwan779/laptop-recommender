"""Scrape Orchestrator — the unified hardware scraping & extraction orchestrator.

This module is the **single entry-point** for every scraping operation.
It connects store-specific scraping to the generic 8-layer hardware pipeline:
  1. Store Crawling (CompuMarts)
  2. Generic Hardware Extraction Pipeline (Layers 2-7: Sanitizer -> CPU Anchor -> Deterministic -> Gate 1 -> NuExtract -> Gate 2)
  3. Universal Ground-Truth LLM Auditor (Layer 8: Groq failover chain)
  4. S3 Object Storage persistence & background email reporting

Usage::

    from app.schemas.orchestrator import ScrapeRequest
    from app.services.orchestrator import ScrapeOrchestrator

    request = ScrapeRequest(
        target_type="store",
        targets=["compumarts"],
        level=2,
        output_dir="./output",
        send_email=True,
    )
    response = ScrapeOrchestrator().execute(request)
"""

from __future__ import annotations

import json
from app.common.logger import get_logger
from app.common.resilience import ErrorCategory, resilient_boundary
from pathlib import Path
import time
from typing import Any

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.email import ScraperFinishedReport
from app.schemas.laptop import StoreCatalogResult, utcnow_str
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult
from app.notifications.service import ScraperNotificationService
from app.common.storage.base import IObjectStorageService
from app.common.storage.factory import get_storage_service
from app.core.sovereign_config import SovereignConfig
from app.domain.catalog.sovereign_prompt import should_use_sovereign_pipeline
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.elbadr import ElBadrStoreScraper
from app.stores.sigma import SigmaComputerStoreScraper

from app.pipeline.catalog_pipeline import GenericCatalogPipeline, setup_ai_fallback
from app.pipeline.sovereign_pipeline import SovereignSmallBatchPipeline

logger = get_logger("scraper.orchestrator")


# ---------------------------------------------------------------------------
# Store Registry (Integrated stores active via the generic 8-layer pipeline)
# ---------------------------------------------------------------------------
STORE_REGISTRY: dict[str, type] = {
    "compumarts": CompumartsStoreScraper,
    "elbadr": ElBadrStoreScraper,
    "sigma": SigmaComputerStoreScraper,
}

# Decommissioned brand registry retained for backward-compatible imports
BRAND_SERVICE_REGISTRY: dict[str, type] = {}


def get_store_scraper(store_key: str, engine: IScraperEngine) -> Any:
    """Instantiate a registered store scraper by key."""
    scraper_cls = STORE_REGISTRY.get(store_key.lower())
    if not scraper_cls:
        active_stores = ", ".join(f"'{k}'" for k in STORE_REGISTRY.keys())
        raise ValueError(
            f"Unknown store '{store_key}'. Only {active_stores} via the 8-layer hardware pipeline are currently active. "
            f"Available stores: {list(STORE_REGISTRY.keys())}"
        )
    return scraper_cls(engine=engine)


class ScrapeOrchestrator:
    """Master Orchestrator executing store scraping and the 8-layer extraction pipeline."""

    def __init__(
        self,
        engine: IScraperEngine | None = None,
        email_service: ScraperNotificationService | None = None,
        send_email: bool = False,
        storage_service: IObjectStorageService | None = None,
        upload_to_bucket: bool = False,
        ai_type: str = "nuextract",
        use_onnx: bool = True,
        no_audit: bool = False,
        audit_batch_size: int = 1,
        sovereign_config: SovereignConfig | None = None,
        sovereign_pipeline_factory: Any = None,
    ) -> None:
        self.engine = engine or ScraplingEngine()
        self.email_service = email_service or ScraperNotificationService()
        self.send_email = send_email
        self.storage_service = storage_service or get_storage_service()
        self.upload_to_bucket = upload_to_bucket
        self.ai_type = ai_type
        self.use_onnx = use_onnx
        self.no_audit = no_audit
        self.audit_batch_size = audit_batch_size
        self.sovereign_config = sovereign_config
        self.sovereign_pipeline_factory = sovereign_pipeline_factory

    # ── public API ──────────────────────────────────────────────────────

    def execute(self, request: ScrapeRequest) -> ScrapeResponse:
        """Run the requested scraping operations and return an aggregate result."""
        started_at = utcnow_str()
        results: list[ScrapeTargetResult] = []

        should_send_email = request.send_email or self.send_email
        should_upload_to_bucket = request.upload_to_bucket or self.upload_to_bucket
        target_tasks = self._resolve_targets(request)

        brand_tasks = [(t, k) for t, k in target_tasks if t == "brand"]
        store_tasks = [(t, k) for t, k in target_tasks if t == "store"]

        for _, key in brand_tasks:
            start_time = time.perf_counter()
            result = self._scrape_brand(key, request)
            elapsed_time = time.perf_counter() - start_time
            results.append(result)
            self._persist_and_notify_target(
                result,
                "brand",
                key,
                request,
                elapsed_time,
                should_upload_to_bucket=should_upload_to_bucket,
                should_send_email=should_send_email,
            )

        use_sovereign = False
        has_custom_scrape_store = "_scrape_store" in self.__dict__
        precombined_unified: Any = None
        out_dir = Path(request.output_dir) if request.output_dir else Path("scraping results")

        if store_tasks and request.level == 2 and not has_custom_scrape_store:
            # Phase 1: Scrape Level 2 PDPs + run lightweight pre-combiner extraction (ZERO ONNX loaded).
            staged_stores: list[tuple[str, Any, list[Any], ScrapeTargetResult, float]] = []
            for _, key in store_tasks:
                store_start = time.perf_counter()
                scraper, products, err_result = self._crawl_store_for_level2(key, request)
                if err_result is not None:
                    results.append(err_result)
                    self._persist_and_notify_target(
                        err_result,
                        "store",
                        key,
                        request,
                        time.perf_counter() - store_start,
                        should_upload_to_bucket=should_upload_to_bucket,
                        should_send_email=should_send_email,
                    )
                    continue

                lightweight_res = self._run_store_pipeline_and_build_result(
                    key=key,
                    store_scraper=scraper,
                    products=products,
                    req=request,
                    use_ai_fallback=False,
                    save_output=False,
                )
                staged_stores.append((key, scraper, products, lightweight_res, store_start))

            # Phase 2: Run CatalogCombiner FIRST so overlapping multi-store listings deduplicate
            # before evaluating the batch-size threshold.
            from app.matching.combiner import CatalogCombiner

            lightweight_targets = [res for _, _, _, res, _ in staged_stores if res.store_result is not None]
            lightweight_catalogs = self._collect_store_catalogs(lightweight_targets, out_dir)
            precombined_unified = (
                CatalogCombiner().combine_catalogs(lightweight_catalogs) if lightweight_catalogs else None
            )
            combined_unique_count = precombined_unified.total_unique_laptops if precombined_unified is not None else 0

            cfg = self.sovereign_config or SovereignConfig.from_env()
            effective_mode = "legacy" if (self.no_audit and request.pipeline_mode == "auto") else request.pipeline_mode
            use_sovereign = should_use_sovereign_pipeline(
                level1_count=combined_unique_count,
                threshold=cfg.batch_threshold,
                has_key=cfg.has_configured_key(),
                mode=effective_mode,
            )

            logger.info(
                "[Orchestrator] Post-Combiner routing decision: combined_unique=%d, threshold=%d, mode=%s, selected=%s",
                combined_unique_count,
                cfg.batch_threshold,
                effective_mode,
                "PIPELINE_B_SOVEREIGN" if use_sovereign else "PIPELINE_A_LEGACY",
            )

            if use_sovereign:
                # Pipeline B keeps lightweight sanitized store outputs (no ONNX ever loaded)
                for key, _, _, res, store_start in staged_stores:
                    output_file = self._output_path(request, f"store_{key}.json")
                    if output_file and res.store_result is not None:
                        self._save_json(res.store_result, output_file)
                    results.append(res)
                    self._persist_and_notify_target(
                        res,
                        "store",
                        key,
                        request,
                        time.perf_counter() - store_start,
                        should_upload_to_bucket=should_upload_to_bucket,
                        should_send_email=should_send_email,
                    )
            else:
                # Pipeline A: upgrade staged stores with ONNX/AI fallback (when enabled) using
                # already-fetched PDP products (zero redundant store HTTP requests).
                if self.ai_type != "none" and any(prods for _, _, prods, _, _ in staged_stores):
                    upgraded_stores: list[ScrapeTargetResult] = []
                    for key, scraper, products, _, store_start in staged_stores:
                        full_res = self._run_store_pipeline_and_build_result(
                            key=key,
                            store_scraper=scraper,
                            products=products,
                            req=request,
                            use_ai_fallback=True,
                            save_output=True,
                        )
                        upgraded_stores.append(full_res)
                        results.append(full_res)
                        self._persist_and_notify_target(
                            full_res,
                            "store",
                            key,
                            request,
                            time.perf_counter() - store_start,
                            should_upload_to_bucket=should_upload_to_bucket,
                            should_send_email=should_send_email,
                        )
                    upgraded_catalogs = self._collect_store_catalogs(
                        [r for r in upgraded_stores if r.store_result is not None],
                        out_dir,
                    )
                    precombined_unified = (
                        CatalogCombiner().combine_catalogs(upgraded_catalogs) if upgraded_catalogs else None
                    )
                else:
                    for key, _, _, res, store_start in staged_stores:
                        output_file = self._output_path(request, f"store_{key}.json")
                        if output_file and res.store_result is not None:
                            self._save_json(res.store_result, output_file)
                        results.append(res)
                        self._persist_and_notify_target(
                            res,
                            "store",
                            key,
                            request,
                            time.perf_counter() - store_start,
                            should_upload_to_bucket=should_upload_to_bucket,
                            should_send_email=should_send_email,
                        )
        else:
            for _, key in store_tasks:
                start_time = time.perf_counter()
                result = self._scrape_store(key, request)
                elapsed_time = time.perf_counter() - start_time
                results.append(result)
                self._persist_and_notify_target(
                    result,
                    "store",
                    key,
                    request,
                    elapsed_time,
                    should_upload_to_bucket=should_upload_to_bucket,
                    should_send_email=should_send_email,
                )

        # Stage 2, 3 & 4: Multi-Store Unified Enrichment (Pipeline B vs Pipeline A)
        uploaded_key: str | None = None
        uploaded_bucket: str | None = None
        unified_total_laptops: int | None = None
        unified_error: str | None = None
        store_targets = [r for r in results if r.target_type == "store" and r.store_result is not None]
        if store_targets and request.level == 2:
            store_catalogs = self._collect_store_catalogs(store_targets, out_dir)

            if len(store_catalogs) >= 1 or precombined_unified is not None:
                logger.info(
                    "[Orchestrator] Running Stage 3/4 (%s)...",
                    "SovereignEG Dual-Source Pipeline B" if use_sovereign else "Icecat Enrichment (Pipeline A)",
                )
                with resilient_boundary(
                    category=ErrorCategory.DOM_PARSING,
                    source_component="matching.combiner",
                    suppress=True,
                ) as boundary_ctx:
                    from app.matching.combiner import CatalogCombiner
                    from app.pipeline.icecat.enricher import IcecatCatalogEnricher

                    unified_catalog = precombined_unified or CatalogCombiner().combine_catalogs(store_catalogs)

                    if use_sovereign:
                        cfg = self.sovereign_config or SovereignConfig.from_env()
                        sovereign_pipeline = (
                            self.sovereign_pipeline_factory(cfg, out_dir)
                            if self.sovereign_pipeline_factory is not None
                            else SovereignSmallBatchPipeline(
                                config=cfg,
                                cache_path=out_dir / "sovereign_extract_cache.json",
                            )
                        )
                        unified_catalog = sovereign_pipeline.enrich_unified_catalog(unified_catalog, out_dir=out_dir)
                    else:
                        enricher = IcecatCatalogEnricher(
                            cache_path=out_dir / "icecat_specs_cache.json",
                            match_report_path=out_dir / "icecat_match_report.json",
                            run_llm_fallback=not self.no_audit,
                        )
                        unified_catalog = enricher.enrich_catalog(unified_catalog)

                    unified_total_laptops = unified_catalog.total_unique_laptops
                    unified_path = out_dir / "unified_catalog_latest.json"
                    if unified_catalog.total_unique_laptops > 0:
                        unified_catalog.save_json(unified_path)
                        logger.info("[Orchestrator] Saved enriched unified catalog to: %s", unified_path.resolve())

                    # Upload to object storage if configured (both immutable snapshot and latest pointer)
                    if self._should_upload(request):
                        if unified_catalog.total_unique_laptops <= 0:
                            unified_error = (
                                "Unified catalog produced 0 unique laptops; skipping S3 upload "
                                "to preserve existing catalogs/catalog_latest.json."
                            )
                            logger.warning("[Orchestrator] %s", unified_error)
                        else:
                            try:
                                from datetime import UTC, datetime

                                if request.batch_id:
                                    batch_key = f"catalogs/catalog_{request.batch_id}.json"
                                else:
                                    timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                                    batch_key = f"catalogs/catalog_{timestamp_str}.json"

                                latest_key = "catalogs/catalog_latest.json"
                                upload_meta = {
                                    "total_unique_laptops": str(unified_catalog.total_unique_laptops),
                                    "stores_included": ",".join(unified_catalog.stores_included),
                                    "batch_id": request.batch_id or "",
                                }

                                # 1. Primary: Upload immutable batch artifact
                                self.storage_service.upload_json(
                                    data=unified_catalog.model_dump(),
                                    object_key=batch_key,
                                    metadata=upload_meta,
                                )
                                # 2. Convenience: Overwrite latest pointer
                                self.storage_service.upload_json(
                                    data=unified_catalog.model_dump(),
                                    object_key=latest_key,
                                    metadata=upload_meta,
                                )
                                uploaded_key = batch_key
                                uploaded_bucket = getattr(self.storage_service, "bucket_name", None)
                                logger.info(
                                    "[Orchestrator] [+] Uploaded unified catalog to S3: '%s' and '%s'",
                                    batch_key,
                                    latest_key,
                                )
                            except Exception as s3_exc:
                                unified_error = f"Failed to upload unified catalog to S3: {s3_exc}"
                                logger.warning("[Orchestrator] %s", unified_error)

                if boundary_ctx.has_error and not unified_error:
                    unified_error = (
                        getattr(boundary_ctx.error_record, "error_message", None)
                        or getattr(boundary_ctx.error_record, "message", None)
                        or "Unified catalog combining or enrichment failed."
                    )

        total_items = sum(r.items_scraped for r in results)

        return ScrapeResponse(
            results=results,
            total_targets=len(results),
            total_items_scraped=total_items,
            started_at=started_at,
            finished_at=utcnow_str(),
            unified_storage_key=uploaded_key,
            unified_storage_bucket=uploaded_bucket,
            unified_total_laptops=unified_total_laptops,
            unified_error=unified_error,
        )

    # ── private helpers ─────────────────────────────────────────────────

    def _resolve_targets(self, request: ScrapeRequest) -> list[tuple[str, str]]:
        """Expand target keys into concrete (target_type, key) pairs."""
        items: list[tuple[str, str]] = []

        if request.target_type == "store":
            if request.targets == "all":
                items.extend([("store", k) for k in STORE_REGISTRY.keys()])
            else:
                for k in request.targets:
                    k_clean = k.strip().lower()
                    if k_clean:
                        items.append(("store", k_clean))

        elif request.target_type == "brand":
            keys = (
                list(BRAND_SERVICE_REGISTRY.keys()) if BRAND_SERVICE_REGISTRY else ["asus", "hp", "lenovo", "gigabyte"]
            )
            items_keys = keys if request.targets == "all" else request.targets
            items.extend([("brand", k.strip().lower()) for k in items_keys if k.strip()])

        elif request.target_type == "both":
            if request.targets == "all":
                keys = (
                    list(BRAND_SERVICE_REGISTRY.keys())
                    if BRAND_SERVICE_REGISTRY
                    else ["asus", "hp", "lenovo", "gigabyte"]
                )
                items.extend([("brand", k) for k in keys])
                items.extend([("store", k) for k in STORE_REGISTRY.keys()])
            else:
                known_stores = set(STORE_REGISTRY.keys()) | {
                    "elbadr",
                    "sigma",
                    "twob",
                    "tradeline",
                    "amazon",
                    "noon",
                    "btech",
                }
                for t in request.targets:
                    k = t.strip().lower()
                    if not k:
                        continue
                    if k in known_stores:
                        items.append(("store", k))
                    else:
                        items.append(("brand", k))

        return items

    # ── brand dispatch (decommissioned / legacy compatibility) ──────────

    def _scrape_brand(self, key: str, req: ScrapeRequest) -> ScrapeTargetResult:
        """Execute brand scraping (decommissioned / legacy compatibility)."""
        service_cls = BRAND_SERVICE_REGISTRY.get(key)
        if service_cls is None:
            return ScrapeTargetResult(
                target_type="brand",
                target_key=key,
                target_name=key,
                level=req.level,
                items_scraped=0,
                error=f"Unknown brand '{key}'. Brand scraping is decommissioned; only 'compumarts' via the 8-layer hardware pipeline is active. Available: {list(BRAND_SERVICE_REGISTRY.keys())}",
            )

        service = service_cls(engine=self.engine)
        output_file = self._output_path(req, f"brand_{key}.json")

        try:
            catalog = service.scrape(
                mode=f"level{req.level}",
                until_model=req.until_model,
                max_pages=req.max_pages,
                limit=req.limit,
                output_file=output_file,
            )
        except Exception as exc:
            return ScrapeTargetResult(
                target_type="brand",
                target_key=key,
                target_name=key,
                level=req.level,
                items_scraped=0,
                error=str(exc),
            )

        return ScrapeTargetResult(
            target_type="brand",
            target_key=key,
            target_name=getattr(catalog, "brand", key),
            level=req.level,
            items_scraped=getattr(catalog, "total_laptops", 0),
            output_file=str(output_file) if output_file else None,
            brand_result=catalog,
        )

    # ── store dispatch helpers (Pipeline A + Pipeline B) ─────────────────

    def _persist_and_notify_target(
        self,
        result: ScrapeTargetResult,
        target_type: str,
        key: str,
        request: ScrapeRequest,
        elapsed_time: float,
        *,
        should_upload_to_bucket: bool,
        should_send_email: bool,
    ) -> None:
        if should_upload_to_bucket:
            self._upload_target_to_storage(result, target_type, key)

        if should_send_email:
            try:
                watermark = (
                    request.until_model
                    if isinstance(request.until_model, str)
                    else (", ".join(request.until_model) if request.until_model else None)
                )
                report = ScraperFinishedReport.from_target_result(
                    result,
                    duration_seconds=elapsed_time,
                    until_model=watermark,
                )
                self.email_service.send_scraper_finished_background(report)
            except Exception as exc:
                logger.warning("[Orchestrator] Failed to dispatch background email report for %s: %s", key, exc)

    @staticmethod
    def _collect_store_catalogs(
        store_targets: list[ScrapeTargetResult],
        out_dir: Path,
    ) -> list[dict[str, Any]]:
        in_memory_by_store = {
            r.target_key.lower(): r.store_result.model_dump() for r in store_targets if r.store_result
        }
        store_catalogs: list[dict[str, Any]] = []
        for reg_store_key in STORE_REGISTRY.keys():
            if reg_store_key in in_memory_by_store:
                store_catalogs.append(in_memory_by_store[reg_store_key])
            else:
                candidates = [
                    out_dir / f"store_{reg_store_key}.json",
                    out_dir / f"{reg_store_key}_catalog_latest.json",
                    out_dir / f"{reg_store_key}_latest.json",
                ]
                for cand_path in candidates:
                    if cand_path.is_file():
                        try:
                            with open(cand_path, encoding="utf-8") as cf:
                                store_catalogs.append(json.load(cf))
                            break
                        except Exception as disk_exc:
                            logger.warning("[Orchestrator] Failed to load cached store '%s': %s", cand_path, disk_exc)
        return store_catalogs

    def _crawl_store_for_level2(
        self,
        key: str,
        req: ScrapeRequest,
    ) -> tuple[Any, list[Any], ScrapeTargetResult | None]:
        """Execute store-level Level-2 PDP crawl for one store target before post-combiner routing."""
        try:
            store_scraper = get_store_scraper(key, self.engine)
        except ValueError as exc:
            return (
                None,
                [],
                ScrapeTargetResult(
                    target_type="store",
                    target_key=key,
                    target_name=key,
                    level=req.level,
                    items_scraped=0,
                    error=str(exc),
                ),
            )

        try:
            products = store_scraper.scrape_catalog(
                level=2,
                until_model=req.until_model,
                max_pages=req.max_pages,
                limit=req.limit,
            )
            return store_scraper, list(products or []), None
        except Exception as exc:
            return (
                store_scraper,
                [],
                ScrapeTargetResult(
                    target_type="store",
                    target_key=key,
                    target_name=getattr(store_scraper, "store_name", key),
                    level=req.level,
                    items_scraped=0,
                    error=str(exc),
                ),
            )

    def _run_store_pipeline_and_build_result(
        self,
        key: str,
        store_scraper: Any,
        products: list[Any],
        req: ScrapeRequest,
        *,
        use_ai_fallback: bool = True,
        save_output: bool = True,
    ) -> ScrapeTargetResult:
        output_file = self._output_path(req, f"store_{key}.json")
        checkpoint_file = self._output_path(req, f"store_{key}.checkpoint.jsonl") if req.output_dir else None

        structured_products: list[dict[str, Any]] = []
        quarantine_file: str | None = None
        quarantined_count = 0

        if req.level == 2 and products:
            if not use_ai_fallback:
                logger.info(
                    "[Orchestrator] Running lightweight pre-combiner sanitizer (no ONNX) on %d products from '%s'...",
                    len(products),
                    key,
                )
                ai_backend = None
            else:
                logger.info(
                    "[Orchestrator] Running generic 8-layer hardware pipeline on %d products from '%s'...",
                    len(products),
                    key,
                )
                ai_backend = setup_ai_fallback(self.ai_type, use_onnx=self.use_onnx)

            generic_pipeline = GenericCatalogPipeline(
                ai_fallback=ai_backend,
                no_audit=True,  # Cloud LLM audit runs post-combiner & post-Icecat in Stage 4
                audit_batch_size=self.audit_batch_size,
                core_only_ai=True,
            )
            structured_products = generic_pipeline.process_catalog(
                products=products,
                store_key=key,
                checkpoint_file=checkpoint_file,
            )

            quarantine_file = generic_pipeline.last_quarantine_file
            if generic_pipeline.last_quarantine:
                quarantined_count = generic_pipeline.last_quarantine.error_count
                if quarantined_count > 0:
                    logger.warning(
                        "[Orchestrator] Target '%s' had %d quarantined items. DLQ report: %s",
                        key,
                        quarantined_count,
                        quarantine_file,
                    )

        if products:
            latest_pointers = [p.title for p in products[:3]]
        elif req.until_model:
            latest_pointers = [req.until_model] if isinstance(req.until_model, str) else list(req.until_model[:3])
        else:
            latest_pointers = []
        skipped_list = list(getattr(store_scraper, "skipped_laptops", []))
        is_level2 = req.level == 2

        store_catalog = StoreCatalogResult(
            store_name=store_scraper.store_name,
            store_key=store_scraper.store_key,
            store_domain=store_scraper.base_domain,
            scrape_mode=f"level{req.level}",
            until_model=(
                req.until_model
                if isinstance(req.until_model, str)
                else (", ".join(req.until_model) if req.until_model else None)
            ),
            latest_pointers=latest_pointers,
            total_products=len(structured_products) if is_level2 else len(products),
            total_skipped=len(skipped_list),
            total_quarantined=quarantined_count,
            products=[] if is_level2 else products,
            structured_products=structured_products,
            skipped_laptops=skipped_list,
        )

        if output_file and save_output:
            self._save_json(store_catalog, output_file)

        return ScrapeTargetResult(
            target_type="store",
            target_key=key,
            target_name=store_scraper.store_name,
            level=req.level,
            items_scraped=len(structured_products) if is_level2 else len(products),
            output_file=str(output_file) if (output_file and save_output) else None,
            quarantine_file=quarantine_file,
            errors_count=quarantined_count,
            store_result=store_catalog,
        )

    def _scrape_store(self, key: str, req: ScrapeRequest) -> ScrapeTargetResult:
        """Execute store scraping and invoke the generic 8-layer hardware pipeline."""
        try:
            store_scraper = get_store_scraper(key, self.engine)
        except ValueError as exc:
            return ScrapeTargetResult(
                target_type="store",
                target_key=key,
                target_name=key,
                level=req.level,
                items_scraped=0,
                error=str(exc),
            )

        try:
            products = store_scraper.scrape_catalog(
                level=req.level,
                until_model=req.until_model,
                max_pages=req.max_pages,
                limit=req.limit,
            )
        except Exception as exc:
            return ScrapeTargetResult(
                target_type="store",
                target_key=key,
                target_name=getattr(store_scraper, "store_name", key),
                level=req.level,
                items_scraped=0,
                error=str(exc),
            )

        return self._run_store_pipeline_and_build_result(
            key=key,
            store_scraper=store_scraper,
            products=products,
            req=req,
            use_ai_fallback=True,
            save_output=True,
        )

    def _should_upload(self, req: ScrapeRequest) -> bool:
        return bool(req.upload_to_bucket or self.upload_to_bucket)

    def _output_path(self, req: ScrapeRequest, filename: str) -> Path | None:
        if self._should_upload(req):
            if req.output_dir:
                msg = (
                    f"[Orchestrator] upload_to_bucket=True: Bypassing local disk persistence "
                    f"('{req.output_dir}') to preserve server disk space."
                )
                logger.info(msg)
                print(msg)
            return None
        if not req.output_dir:
            return None
        out_dir = Path(req.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / filename

    @staticmethod
    def _save_json(data: StoreCatalogResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"[Orchestrator] Saved store results to {path.resolve()}")

    def _upload_target_to_storage(
        self,
        result: ScrapeTargetResult,
        target_type: str,
        key: str,
    ) -> None:
        """Upload scraped JSON results for a single target to object storage."""
        if result.error:
            # Do not upload failed scrape attempts
            return

        object_key = f"{target_type}s/{target_type}_{key}.json"
        metadata = {
            "target_type": target_type,
            "target_key": key,
            "target_name": result.target_name,
            "items_scraped": str(result.items_scraped),
            "level": str(result.level),
        }

        with resilient_boundary(
            category=ErrorCategory.STORAGE,
            source_component="storage.orchestrator",
            context={"target_key": key, "target_type": target_type},
            suppress=True,
        ):
            if result.output_file and Path(result.output_file).is_file():
                storage_obj = self.storage_service.upload_file(
                    file_path=result.output_file,
                    object_key=object_key,
                    content_type="application/json",
                    metadata=metadata,
                )
            elif result.brand_result is not None:
                storage_obj = self.storage_service.upload_json(
                    data=result.brand_result.model_dump(),
                    object_key=object_key,
                    metadata=metadata,
                )
            elif result.store_result is not None:
                storage_obj = self.storage_service.upload_json(
                    data=result.store_result.model_dump(),
                    object_key=object_key,
                    metadata=metadata,
                )
            else:
                return

            result.storage_key = storage_obj.key
            print(
                f"[Orchestrator] [+] Successfully uploaded '{key}' JSON to "
                f"bucket '{self.storage_service.bucket_name}' as '{object_key}'"
            )

            # Upload DLQ quarantine file if present
            if result.quarantine_file and Path(result.quarantine_file).is_file():
                q_object_key = f"quarantine/{target_type}_{key}_quarantine.json"
                try:
                    q_storage_obj = self.storage_service.upload_file(
                        file_path=result.quarantine_file,
                        object_key=q_object_key,
                        content_type="application/json",
                        metadata={
                            "target_type": target_type,
                            "target_key": key,
                            "quarantined_errors": str(result.errors_count),
                        },
                    )
                    result.quarantine_storage_key = q_storage_obj.key
                    print(
                        f"[Orchestrator] [+] Successfully uploaded DLQ quarantine report for '{key}' "
                        f"to '{q_object_key}'"
                    )
                except Exception as q_exc:
                    logger.warning("[Orchestrator] Failed to upload DLQ quarantine report to storage: %s", q_exc)
