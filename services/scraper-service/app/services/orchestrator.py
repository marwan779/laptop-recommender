"""Scrape Orchestrator — the unified abstraction layer.

This module is the **single entry-point** for every scraping operation.
It replaces the branching logic that used to live in the CLI and provides
a programmatic API that can be called by:

  * The CLI  (``python -m app.cli``)
  * A FastAPI controller endpoint
  * The catalog-service cron job (via HTTP or direct import)

Usage::

    from app.schemas.orchestrator import ScrapeRequest
    from app.services.orchestrator import ScrapeOrchestrator

    request = ScrapeRequest(
        target_type="store",
        targets=["compumarts", "sigma"],
        level=2,
        output_dir="./output",
        send_email=True,
    )
    response = ScrapeOrchestrator().execute(request)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Type

logger = logging.getLogger("scraper.orchestrator")

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.email import ScraperFinishedReport
from app.schemas.laptop import BrandCatalogResult, StoreCatalogResult, utcnow_str
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult
from app.services.asus_scraper_service import AsusScraperService
from app.services.email_service import EmailService
from app.services.gigabyte_scraper_service import GigabyteScraperService
from app.services.hp_scraper_service import HpScraperService
from app.services.lenovo_scraper_service import LenovoScraperService
from app.storage.base import IObjectStorageService
from app.storage.factory import get_storage_service
from app.stores.registry import STORE_REGISTRY, get_store_scraper


# ---------------------------------------------------------------------------
# Brand Service Registry
# ---------------------------------------------------------------------------
# Maps brand keys (matching ``BRAND_CATALOGS`` in constants.py) to their
# corresponding service classes.  Adding a new brand is a one-liner here.

BRAND_SERVICE_REGISTRY: dict[str, Type] = {
    "asus": AsusScraperService,
    "hp": HpScraperService,
    "lenovo": LenovoScraperService,
    "gigabyte": GigabyteScraperService,
}


class ScrapeOrchestrator:
    """Facade that turns a single ``ScrapeRequest`` into a ``ScrapeResponse``.

    It delegates to the existing brand services and store scrapers without
    modifying their internal logic — it only *accumulates* their calls.
    """

    def __init__(
        self,
        engine: IScraperEngine | None = None,
        email_service: EmailService | None = None,
        send_email: bool = False,
        storage_service: IObjectStorageService | None = None,
        upload_to_bucket: bool = False,
    ) -> None:
        self.engine = engine or ScraplingEngine()
        self.email_service = email_service or EmailService()
        self.send_email = send_email
        self.storage_service = storage_service or get_storage_service()
        self.upload_to_bucket = upload_to_bucket

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
                    print(f"[Orchestrator] Warning: Failed to dispatch background email report for {key}: {exc}")

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

        if request.target_type == "brand":
            keys = list(BRAND_SERVICE_REGISTRY.keys()) if request.targets == "all" else request.targets
            items.extend([("brand", k.strip().lower()) for k in keys if k.strip()])

        elif request.target_type == "store":
            keys = list(STORE_REGISTRY.keys()) if request.targets == "all" else request.targets
            items.extend([("store", k.strip().lower()) for k in keys if k.strip()])

        elif request.target_type == "both":
            if request.targets == "all":
                items.extend([("brand", k) for k in BRAND_SERVICE_REGISTRY.keys()])
                items.extend([("store", k) for k in STORE_REGISTRY.keys()])
            else:
                for t in request.targets:
                    k = t.strip().lower()
                    if not k:
                        continue
                    if k in BRAND_SERVICE_REGISTRY:
                        items.append(("brand", k))
                    elif k in STORE_REGISTRY:
                        items.append(("store", k))
                    else:
                        # Unknown target - default to brand so error handling captures it cleanly
                        items.append(("brand", k))

        return items

    # ── brand dispatch ──────────────────────────────────────────────────

    def _scrape_brand(self, key: str, req: ScrapeRequest) -> ScrapeTargetResult:
        service_cls = BRAND_SERVICE_REGISTRY.get(key)
        if service_cls is None:
            return ScrapeTargetResult(
                target_type="brand",
                target_key=key,
                target_name=key,
                level=req.level,
                items_scraped=0,
                error=f"Unknown brand '{key}'. Available: {list(BRAND_SERVICE_REGISTRY.keys())}",
            )

        service = service_cls(engine=self.engine)
        output_file = self._output_path(req, f"brand_{key}.json")

        try:
            catalog: BrandCatalogResult = service.scrape(
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
            target_name=catalog.brand,
            level=req.level,
            items_scraped=catalog.total_laptops,
            output_file=str(output_file) if output_file else None,
            brand_result=catalog,
        )

    # ── store dispatch ──────────────────────────────────────────────────

    def _scrape_store(self, key: str, req: ScrapeRequest) -> ScrapeTargetResult:
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
                target_name=store_scraper.store_name,
                level=req.level,
                items_scraped=0,
                error=str(exc),
            )

        latest_pointers = [p.title for p in products[:3]]
        skipped_list = list(getattr(store_scraper, "skipped_laptops", []))

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
            total_products=len(products),
            total_skipped=len(skipped_list),
            products=products,
            skipped_laptops=skipped_list,
        )

        if output_file:
            self._save_json(store_catalog, output_file)

        return ScrapeTargetResult(
            target_type="store",
            target_key=key,
            target_name=store_scraper.store_name,
            level=req.level,
            items_scraped=len(products),
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
            print(
                f"[Orchestrator] Warning: Failed to upload '{key}' JSON to object storage: {exc}"
            )

