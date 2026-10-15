"""Live CompuMarts Pipeline CLI Runner.

Executes the rebuilt 7-layer extraction pipeline live against CompuMarts Egypt:
- Discovers in-stock laptop PDPs.
- Archives raw scraped HTML into raw_scrapes/ for auditability.
- Runs CPU Anchor extraction, Deterministic extraction, Physical validation,
  and AI fallback (GLiNER ONNX / NuExtract).
- Emits real-time checkpoints and final JSON catalog.

Usage:
    # Run a single laptop PDP URL:
    python -m pipeline.run_compumarts --url "https://www.compumarts.com/products/..."

    # Run on the first 5 live laptops:
    python -m pipeline.run_compumarts --limit 5

    # Run full live catalog with GLiNER ONNX fallback:
    python -m pipeline.run_compumarts

    # Run without AI fallback (deterministic + CPU anchor only):
    python -m pipeline.run_compumarts --limit 10 --ai none
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.stores.compumarts import CompumartsStoreScraper
from pipeline.ai_fallback.gliner_onnx import GLiNERONNXFallbackExtractor
from pipeline.ai_fallback.nuextract import NuExtractFallbackExtractor
from pipeline.orchestrator import LaptopExtractionPipeline, PipelineResult
from pipeline.raw_storage import RawScrapeStorage
from pipeline.schema import RawScrapedProduct

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("compumarts_pipeline")


def setup_ai_fallback(
    ai_type: str, use_onnx: bool, onnx_dir: Optional[str] = None
) -> Optional[Any]:
    """Initialize the chosen AI fallback model."""
    if ai_type == "none":
        logger.info("AI fallback disabled (--ai none). Running deterministic + CPU anchor only.")
        return None

    if ai_type == "gliner":
        logger.info(
            "Initializing GLiNER fallback (model: onnx-community/gliner_large-v2.1, onnx=%s)...",
            use_onnx,
        )
        try:
            extractor = GLiNERONNXFallbackExtractor(
                model_id="onnx-community/gliner_large-v2.1",
                load_onnx_model=use_onnx,
                onnx_model_file="onnx/model_int8.onnx" if use_onnx else None,
                threshold=0.35,
                lazy_load=False,
            )
            logger.info("GLiNER fallback ready! Backend: %s", extractor.model_name)
            return extractor
        except Exception as e:
            logger.warning(
                "Could not load onnx-community/gliner_large-v2.1 (%s). Falling back to urchade/gliner_base...",
                e,
            )
            return GLiNERONNXFallbackExtractor(
                model_id="urchade/gliner_base",
                load_onnx_model=False,
                lazy_load=False,
            )

    elif ai_type == "nuextract":
        logger.info("Initializing NuExtract-v1.5 (3.8B) ONNX fallback...")
        return NuExtractFallbackExtractor(
            onnx_model_dir=onnx_dir,
            lazy_load=False,
        )

    return None


def run_pipeline(
    limit: Optional[int] = None,
    target_url: Optional[str] = None,
    ai_type: str = "gliner",
    use_onnx: bool = True,
    onnx_dir: Optional[str] = None,
    output_file: str = "pipeline_results_compumarts.json",
    checkpoint_file: str = "pipeline_results_compumarts.checkpoint.jsonl",
    trace_file: str = "pipeline_trace_compumarts.jsonl",
) -> None:
    """Execute live scraping and pipeline processing."""
    ai_backend = setup_ai_fallback(ai_type, use_onnx, onnx_dir=onnx_dir)
    pipeline = LaptopExtractionPipeline(ai_fallback=ai_backend)
    storage = RawScrapeStorage()

    out_path = Path(output_file)
    ckpt_path = Path(checkpoint_file)
    trace_path = Path(trace_file)

    # 1. Single URL Mode
    if target_url:
        logger.info("Running single URL live extraction: %s", target_url)
        t0 = time.time()
        result = pipeline.extract_from_url(target_url, store_name="compumarts")
        elapsed = time.time() - t0

        logger.info("Completed in %.2fs!", elapsed)
        logger.info("Identified CPU: %s", result.cpu_key)
        logger.info("Envelopes generated: %d", len(result.envelopes_generated))
        logger.info("Validation rejections: %d", len(result.validation_rejections))

        if result.provenance_record:
            with trace_path.open("a", encoding="utf-8") as tf:
                tf.write(json.dumps(result.provenance_record, ensure_ascii=False) + "\n")
            logger.info("Saved provenance trace to %s", trace_path)

        print("\n" + "=" * 60)
        print("STRUCTURED EXTRACTION RESULT:")
        print("=" * 60)
        print(json.dumps(result.specs, indent=2, ensure_ascii=False))
        return

    # 2. Full or Limited Catalog Crawl
    logger.info("Crawling live CompuMarts catalog (limit=%s)...", limit or "ALL")
    store_scraper = CompumartsStoreScraper()
    catalog_products = store_scraper.scrape_catalog(level=2, limit=limit)
    total_found = len(catalog_products)
    logger.info("Discovered %d in-stock laptop products from CompuMarts.", total_found)

    results: List[Dict[str, Any]] = []
    stats = {
        "total": total_found,
        "processed": 0,
        "cpu_identified": 0,
        "envelopes_total": 0,
        "ai_resolved": 0,
        "gate1_rejections": 0,
        "gate2_rejections": 0,
    }

    # Open checkpoint and trace streams
    with ckpt_path.open("w", encoding="utf-8") as ckpt_f, trace_path.open("w", encoding="utf-8") as trace_f:
        for idx, prod in enumerate(catalog_products, start=1):
            logger.info("[%d/%d] Processing %s...", idx, total_found, prod.title[:60])
            t_item = time.time()

            raw_prod = RawScrapedProduct(
                url=prod.product_url,
                store="compumarts",
                title=prod.title,
                raw_html="",  # raw HTML already archived during scraper crawl
                raw_tables={"specs": prod.specs or {}},
                raw_sections={"Description": prod.raw_description or ""},
                price=prod.price_egp,
                currency="EGP",
                in_stock=prod.in_stock,
            )

            res = pipeline.process_raw_product(raw_prod)
            elapsed = time.time() - t_item

            stats["processed"] += 1
            if res.cpu_key:
                stats["cpu_identified"] += 1
            stats["envelopes_total"] += len(res.envelopes_generated)
            stats["ai_resolved"] += len(res.ai_results)
            stats["gate1_rejections"] += sum(1 for r in res.validation_rejections if r.get("gate") == 1)
            stats["gate2_rejections"] += sum(1 for r in res.validation_rejections if r.get("gate") == 2)

            item_record = {
                "url": prod.product_url,
                "title": prod.title,
                "price_egp": prod.price_egp,
                "cpu_key": res.cpu_key,
                "specs": res.specs,
                "source_table": prod.specs or {},
                "envelopes_count": len(res.envelopes_generated),
                "rejections_count": len(res.validation_rejections),
                "elapsed_s": round(elapsed, 3),
            }
            results.append(item_record)

            # Write stream checkpoint
            ckpt_f.write(json.dumps(item_record, ensure_ascii=False) + "\n")
            ckpt_f.flush()

            # Stream audit trace record to separate file
            if res.provenance_record:
                trace_f.write(json.dumps(res.provenance_record, ensure_ascii=False) + "\n")
                trace_f.flush()

    # Save final output
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d structured products to %s", len(results), out_path)
    logger.info("Saved provenance audit traces to %s", trace_path)

    # Print summary metrics
    print("\n" + "=" * 60)
    print("PIPELINE EXECUTION SUMMARY:")
    print("=" * 60)
    print(f"Total Laptops Processed:     {stats['processed']}")
    print(f"CPU Anchor Match Rate:       {stats['cpu_identified']} / {stats['processed']} ({stats['cpu_identified']/max(stats['processed'],1):.1%})")
    print(f"Total Envelopes Generated:   {stats['envelopes_total']}")
    print(f"AI Fallback Resolved:        {stats['ai_resolved']}")
    print(f"Gate 1 Physical Rejections:  {stats['gate1_rejections']}")
    print(f"Gate 2 AI Rejections:        {stats['gate2_rejections']}")
    print(f"Output File:                 {out_path.resolve()}")
    print(f"Audit Trace Log:             {trace_path.resolve()}")
    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live CompuMarts Laptop Extraction Pipeline")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of laptops to scrape/process")
    parser.add_argument("--url", type=str, default=None, help="Process a single laptop PDP URL directly")
    parser.add_argument("--ai", choices=["gliner", "nuextract", "none"], default="gliner", help="AI Fallback backend")
    parser.add_argument("--no-onnx", action="store_true", help="Disable ONNX and run GLiNER with PyTorch")
    parser.add_argument("--output", type=str, default="pipeline_results_compumarts.json", help="Output JSON path")
    parser.add_argument("--onnx-dir", type=str, default=None, help="Path to local ONNX model directory (e.g. for NuExtract ONNX GenAI)")
    parser.add_argument("--checkpoint", type=str, default="pipeline_results_compumarts.checkpoint.jsonl", help="Checkpoint JSONL path")
    parser.add_argument("--trace-file", type=str, default="pipeline_trace_compumarts.jsonl", help="Provenance audit trace JSONL path")

    args = parser.parse_args()
    run_pipeline(
        limit=args.limit,
        target_url=args.url,
        ai_type=args.ai,
        use_onnx=not args.no_onnx,
        onnx_dir=args.onnx_dir,
        output_file=args.output,
        checkpoint_file=args.checkpoint,
        trace_file=args.trace_file,
    )


if __name__ == "__main__":
    main()

