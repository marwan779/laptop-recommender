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
from common.logger import get_logger
from pathlib import Path
import time
from typing import Any

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.email import ScraperFinishedReport
from app.schemas.laptop import StoreCatalogResult, utcnow_str
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult
from app.services.email_service import EmailService
from app.storage.base import IObjectStorageService
from app.storage.factory import get_storage_service
from app.stores.compumarts import CompumartsStoreScraper
from pipeline.catalog_pipeline import GenericCatalogPipeline, setup_ai_fallback

logger = get_logger("scraper.orchestrator")


# ---------------------------------------------------------------------------
# Store Registry (Currently locked to CompuMarts with generic 8-layer pipeline)
# ---------------------------------------------------------------------------
STORE_REGISTRY: dict[str, type] = {
    "compumarts": CompumartsStoreScraper,
}

# Decommissioned brand registry retained for backward-compatible imports
BRAND_SERVICE_REGISTRY: dict[str, type] = {}


def get_store_scraper(store_key: str, engine: IScraperEngine) -> Any:
    """Instantiate a registered store scraper by key."""
    scraper_cls = STORE_REGISTRY.get(store_key.lower())
    if not scraper_cls:
        raise ValueError(
            f"Unknown store '{store_key}'. Only 'compumarts' via the 8-layer hardware pipeline is currently active. "
            f"Available stores: {list(STORE_REGISTRY.keys())}"
        )
    return scraper_cls(engine=engine)


class ScrapeOrchestrator:
    """Master Orchestrator executing store scraping and the 8-layer extraction pipeline."""

    def __init__(
        self,
        engine: IScraperEngine | None = None,
        email_service: EmailService | None = None,
        send_email: bool = False,
        storage_service: IObjectStorageService | None = None,
        upload_to_bucket: bool = False,
        ai_type: str = "nuextract",
        use_onnx: bool = True,
        no_audit: bool = False,
        audit_batch_size: int = 1,
    ) -> None:
        self.engine = engine or ScraplingEngine()
        self.email_service = email_service or EmailService()
        self.send_email = send_email
        self.storage_service = storage_service or get_storage_service()
        self.upload_to_bucket = upload_to_bucket
        self.ai_type = ai_type
        self.use_onnx = use_onnx
        self.no_audit = no_audit
        self.audit_batch_size = audit_batch_size

    # ── public API ──────────────────────────────────────────────────────

    def execute(self, request: ScrapeRequest) -> ScrapeResponse:
        """Run the requested scraping operations and return an aggregate result."""
        started_at = utcnow_str()
        results: list[ScrapeTargetResult] = []

        should_send_email = request.send_email or self.send_email
        should_upload_to_bucket = request.upload_to_bucket or self.upload_to_bucket
        target_tasks = self._resolve_targets(request)

        for target_type, key in target_tasks:
            start_time = time.perf_counter()

            if target_type == "brand":
                result = self._scrape_brand(key, request)
            else:
                result = self._scrape_store(key, request)

            elapsed_time = time.perf_counter() - start_time
            results.append(result)

            # 1. Primary: Upload JSON results to object storage bucket first (if enabled and no error)
            if should_upload_to_bucket:
                self._upload_target_to_storage(result, target_type, key)

            # 2. Auxiliary: Fire non-blocking background email report after storage persistence (if enabled)
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

        total_items = sum(r.items_scraped for r in results)

        return ScrapeResponse(
            results=results,
            total_targets=len(results),
            total_items_scraped=total_items,
            started_at=started_at,
            finished_at=utcnow_str(),
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

    # ── store dispatch with generic 8-layer hardware pipeline ──────────

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

        output_file = self._output_path(req, f"store_{key}.json")
        checkpoint_file = self._output_path(req, f"store_{key}.checkpoint.jsonl") if req.output_dir else None

        try:
            # Step 1: Store-specific crawl (Level 1 cards or Level 2 PDP specs)
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

        structured_products: list[dict[str, Any]] = []

        # Step 2: Generic 8-Layer Hardware Pipeline (on Level 2 deep PDP extraction)
        if req.level == 2 and products:
            logger.info(
                "[Orchestrator] Running generic 8-layer hardware pipeline on %d products from '%s'...",
                len(products),
                key,
            )
            ai_backend = setup_ai_fallback(self.ai_type, use_onnx=self.use_onnx)
            generic_pipeline = GenericCatalogPipeline(
                ai_fallback=ai_backend,
                no_audit=self.no_audit,
                audit_batch_size=self.audit_batch_size,
            )
            structured_products = generic_pipeline.process_catalog(
                products=products,
                store_key=key,
                checkpoint_file=checkpoint_file,
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
            products=[] if is_level2 else products,
            structured_products=structured_products,
            skipped_laptops=skipped_list,
        )

        if output_file:
            self._save_json(store_catalog, output_file)

        return ScrapeTargetResult(
            target_type="store",
            target_key=key,
            target_name=store_scraper.store_name,
            level=req.level,
            items_scraped=len(structured_products) if is_level2 else len(products),
            output_file=str(output_file) if output_file else None,
            store_result=store_catalog,
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

        try:
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
        except Exception as exc:
            print(f"[Orchestrator] Warning: Failed to upload '{key}' JSON to object storage: {exc}")
