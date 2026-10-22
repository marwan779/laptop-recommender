"""Generic Catalog Extraction Pipeline.

Executes the 8-layer hardware extraction pipeline across any store's scraped products:
- Layer 1: Scraped raw catalog products (store-specific scraper)
- Layer 2: Text Sanitizer
- Layer 3: CPU Anchor extraction (ground-truth silicon database)
- Layer 4: Deterministic extraction & table key routing
- Layer 5: Gate 1 Physical validation
- Layer 6: AI Fallback extraction (NuExtract-2.0-2B ONNX)
- Layer 7: Gate 2 Physical validation
- Layer 8: Universal Ground-Truth LLM Auditor (failover chain)
"""

from __future__ import annotations

import json
from common.logger import get_logger
import time
from pathlib import Path
from typing import Any
from collections.abc import Callable

from app.schemas.laptop import RetailerProduct
from pipeline.ai_fallback.base import IAIFallbackExtractor
from pipeline.ai_fallback.gliner_onnx import GLiNERONNXFallbackExtractor
from pipeline.ai_fallback.nuextract import NuExtractFallbackExtractor
from pipeline.llm_auditor import LLMAuditor
from pipeline.orchestrator import LaptopExtractionPipeline
from pipeline.schema import RawScrapedProduct

logger = get_logger("pipeline.catalog")


def setup_ai_fallback(
    ai_type: str = "nuextract",
    use_onnx: bool = True,
    onnx_dir: str | None = None,
    device: str = "auto",
) -> IAIFallbackExtractor | None:
    """Initialize the chosen AI fallback model safely."""
    if ai_type == "none":
        logger.info("AI fallback disabled. Running deterministic + CPU anchor only.")
        return None

    if ai_type == "gliner":
        try:
            return GLiNERONNXFallbackExtractor(
                model_id="onnx-community/gliner_large-v2.1",
                load_onnx_model=use_onnx,
                onnx_model_file="onnx/model_int8.onnx" if use_onnx else None,
                threshold=0.35,
                lazy_load=False,
            )
        except Exception as e:
            logger.warning("Could not load GLiNER ONNX (%s). Using base fallback...", e)
            try:
                return GLiNERONNXFallbackExtractor(
                    model_id="urchade/gliner_base",
                    load_onnx_model=False,
                    lazy_load=False,
                )
            except Exception:
                return None

    elif ai_type == "nuextract":
        try:
            import torch

            has_cuda = torch.cuda.is_available()
        except ImportError:
            has_cuda = False
        exec_provider = (
            "CUDAExecutionProvider" if device == "cuda" or (device == "auto" and has_cuda) else "CPUExecutionProvider"
        )
        logger.info("Initializing NuExtract-2.0 (2B) fallback (provider=%s)...", exec_provider)
        try:
            return NuExtractFallbackExtractor(
                onnx_model_dir=onnx_dir,
                execution_provider=exec_provider,
                lazy_load=False,
            )
        except Exception as e:
            logger.warning("Could not initialize NuExtract fallback (%s). Running without AI fallback.", e)
            return None

    return None


def retailer_product_to_raw_scraped(
    prod: RetailerProduct,
    store_key: str = "compumarts",
) -> RawScrapedProduct:
    """Convert a store-specific RetailerProduct into the generic RawScrapedProduct contract."""
    prod_specs = dict(prod.specs or {})
    final_sku = prod.retailer_sku or prod.mpn
    final_mpn = prod.mpn or prod.retailer_sku
    if final_sku and "SKU" not in prod_specs:
        prod_specs["SKU"] = final_sku
    if final_mpn and "Part Number" not in prod_specs:
        prod_specs["Part Number"] = final_mpn

    return RawScrapedProduct(
        url=prod.product_url,
        store=store_key,
        title=prod.title,
        raw_html="",
        raw_tables={"specs": prod_specs},
        raw_sections={"Description": prod.raw_description or ""},
        price=prod.price_egp,
        currency="EGP",
        in_stock=prod.in_stock,
        retailer_sku=final_sku,
        mpn=final_mpn,
    )


class GenericCatalogPipeline:
    """Universal 8-layer extraction runner for any retailer store catalog."""

    def __init__(
        self,
        ai_fallback: IAIFallbackExtractor | None = None,
        auditor: LLMAuditor | None = None,
        no_audit: bool = False,
        audit_batch_size: int = 1,
        log_envelopes: bool = False,
    ) -> None:
        self.pipeline = LaptopExtractionPipeline(
            ai_fallback=ai_fallback,
            log_envelopes=log_envelopes,
        )
        self.no_audit = no_audit
        self.audit_batch_size = max(1, audit_batch_size)
        self.auditor: LLMAuditor | None = None
        if not no_audit:
            try:
                self.auditor = auditor or LLMAuditor()
                logger.info(
                    "Layer 8 Streaming LLM Auditor active (batch_size=%d, model=%s).",
                    self.audit_batch_size,
                    self.auditor.model,
                )
            except Exception as e:
                logger.warning("Layer 8 LLM Auditor disabled (%s). Running pipeline without audit.", e)

    def process_single(
        self,
        prod: RetailerProduct | RawScrapedProduct,
        store_key: str = "compumarts",
    ) -> dict[str, Any]:
        """Process a single product through layers 2 to 7, plus optional Layer 8 audit."""
        if isinstance(prod, RetailerProduct):
            raw_prod = retailer_product_to_raw_scraped(prod, store_key=store_key)
        else:
            raw_prod = prod

        t0 = time.time()
        pipeline_res = self.pipeline.process_raw_product(raw_prod)
        elapsed = time.time() - t0

        record: dict[str, Any] = {
            "url": raw_prod.url,
            "title": raw_prod.title,
            "price_egp": raw_prod.price,
            "in_stock": getattr(prod, "in_stock", True),
            "thumbnail_url": getattr(prod, "thumbnail_url", None),
            "retailer_sku": getattr(prod, "retailer_sku", None),
            "mpn": getattr(prod, "mpn", None),
            "cpu_key": pipeline_res.cpu_key,
            "is_audited": False,
            "audit_status": "skipped" if (self.no_audit or not self.auditor) else "pending",
            "audit_meta": {
                "provider": None,
                "has_contradictions": False,
                "corrections_count": 0,
                "applied_corrections": [],
            },
            "specs": pipeline_res.specs,
            "source_table": raw_prod.raw_tables.get("specs", {}),
            "envelopes_count": len(pipeline_res.component_envelopes_generated),
            "rejections_count": len(pipeline_res.validation_rejections),
            "elapsed_s": round(elapsed, 3),
        }

        # Optional single-product Layer 8 audit
        if self.auditor and not self.no_audit:
            if getattr(self.auditor, "is_circuit_broken", False):
                record["is_audited"] = False
                record["audit_status"] = "circuit_broken"
                record["audit_meta"]["reason"] = "circuit_breaker_tripped"
            else:
                try:
                    batch_res = self.auditor.audit_batch([record])
                    if batch_res.audited_laptops and batch_res.audited_laptops[0].is_audited:
                        p_res = batch_res.audited_laptops[0]
                        record["is_audited"] = True
                        record["audit_status"] = "audited"
                        record["audit_meta"]["provider"] = batch_res.provider
                        record["audit_meta"]["has_contradictions"] = p_res.has_contradictions
                        if p_res.corrections:
                            applied = self.auditor.apply_corrections(record, p_res.corrections)
                            record["audit_meta"]["corrections_count"] = len(applied)
                            record["audit_meta"]["applied_corrections"] = applied
                    else:
                        record["is_audited"] = False
                        record["audit_status"] = getattr(batch_res, "status", "failed")
                        record["audit_meta"]["reason"] = getattr(batch_res, "error", None) or "audit_failed"
                except Exception as e:
                    logger.warning("Layer 8 single product audit failed: %s", e)
                    record["is_audited"] = False
                    record["audit_status"] = "failed"
                    record["audit_meta"]["reason"] = str(e)
        else:
            record["is_audited"] = False
            record["audit_status"] = "skipped"

        return record

    def process_catalog(
        self,
        products: list[RetailerProduct],
        store_key: str = "compumarts",
        checkpoint_file: Path | str | None = None,
        trace_file: Path | str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Process an entire catalog through the 8 layers with streaming audit and checkpoints."""
        total = len(products)
        results: list[dict[str, Any]] = []
        audit_buffer: list[dict[str, Any]] = []

        ckpt_path = Path(checkpoint_file) if checkpoint_file else None
        trace_path = Path(trace_file) if trace_file else None

        if ckpt_path:
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
        if trace_path:
            trace_path.parent.mkdir(parents=True, exist_ok=True)

        def flush_buffer():
            if not audit_buffer:
                return

            if self.auditor and not self.no_audit:
                if getattr(self.auditor, "is_circuit_broken", False):
                    for item in audit_buffer:
                        item["is_audited"] = False
                        item["audit_status"] = "circuit_broken"
                        item["audit_meta"]["reason"] = "circuit_breaker_tripped"
                else:
                    idents = [it.get("url") or f"lap_{i}" for i, it in enumerate(audit_buffer)]
                    try:
                        batch_res = self.auditor.audit_batch(audit_buffer, identifiers=idents)
                        res_map = {r.laptop_id: r for r in batch_res.audited_laptops}
                        for ident, it in zip(idents, audit_buffer):
                            p_res = res_map.get(ident)
                            if p_res and p_res.is_audited:
                                it["is_audited"] = True
                                it["audit_status"] = "audited"
                                it["audit_meta"]["provider"] = batch_res.provider
                                it["audit_meta"]["has_contradictions"] = p_res.has_contradictions
                                if p_res.corrections:
                                    applied = self.auditor.apply_corrections(it, p_res.corrections)
                                    it["audit_meta"]["corrections_count"] = len(applied)
                                    it["audit_meta"]["applied_corrections"] = applied
                            else:
                                it["is_audited"] = False
                                it["audit_status"] = getattr(p_res, "status", getattr(batch_res, "status", "failed"))
                                it["audit_meta"]["reason"] = getattr(batch_res, "error", None) or "audit_failed"
                    except Exception as e:
                        logger.warning("Layer 8 streaming audit failed: %s", e)
                        for item in audit_buffer:
                            item["is_audited"] = False
                            item["audit_status"] = "failed"
                            item["audit_meta"]["reason"] = str(e)
            else:
                for item in audit_buffer:
                    item["is_audited"] = False
                    item["audit_status"] = "skipped"

            for item in audit_buffer:
                results.append(item)
                if ckpt_path:
                    with ckpt_path.open("a", encoding="utf-8") as cf:
                        cf.write(json.dumps(item, ensure_ascii=False) + "\n")
            audit_buffer.clear()

        for idx, prod in enumerate(products, start=1):
            if progress_callback:
                progress_callback(idx, total, prod.title)
            else:
                logger.info("[%d/%d] Processing %s...", idx, total, prod.title[:60])

            raw_prod = retailer_product_to_raw_scraped(prod, store_key=store_key)
            t_item = time.time()
            pipeline_res = self.pipeline.process_raw_product(raw_prod)
            elapsed = time.time() - t_item

            item_record: dict[str, Any] = {
                "url": prod.product_url,
                "title": prod.title,
                "price_egp": prod.price_egp,
                "in_stock": getattr(prod, "in_stock", True),
                "thumbnail_url": getattr(prod, "thumbnail_url", None),
                "retailer_sku": getattr(prod, "retailer_sku", None),
                "mpn": getattr(prod, "mpn", None),
                "cpu_key": pipeline_res.cpu_key,
                "is_audited": False,
                "audit_status": "skipped" if (self.no_audit or not self.auditor) else "pending",
                "audit_meta": {
                    "provider": None,
                    "has_contradictions": False,
                    "corrections_count": 0,
                    "applied_corrections": [],
                },
                "specs": pipeline_res.specs,
                "source_table": prod.specs or {},
                "envelopes_count": len(pipeline_res.component_envelopes_generated),
                "rejections_count": len(pipeline_res.validation_rejections),
                "elapsed_s": round(elapsed, 3),
            }

            audit_buffer.append(item_record)

            if not self.auditor or len(audit_buffer) >= self.audit_batch_size:
                flush_buffer()

            if trace_path and pipeline_res.provenance_record:
                with trace_path.open("a", encoding="utf-8") as tf:
                    tf.write(json.dumps(pipeline_res.provenance_record, ensure_ascii=False) + "\n")

        # Flush any remaining items in buffer
        if audit_buffer:
            flush_buffer()

        return results
