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
from datetime import datetime, timezone
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
from pipeline.provenance import ProvenanceTracker
from pipeline.raw_storage import RawScrapeStorage
from pipeline.schema import RawScrapedProduct

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("compumarts_pipeline")


def setup_ai_fallback(
    ai_type: str, use_onnx: bool, onnx_dir: Optional[str] = None, device: str = "auto"
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
        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except ImportError:
            has_cuda = False
        exec_provider = "CUDAExecutionProvider" if device == "cuda" or (device == "auto" and has_cuda) else "CPUExecutionProvider"
        logger.info("Initializing NuExtract-2.0 (2B) fallback (provider=%s)...", exec_provider)
        return NuExtractFallbackExtractor(
            onnx_model_dir=onnx_dir,
            execution_provider=exec_provider,
            lazy_load=False,
        )

    return None


def run_pipeline(
    limit: Optional[int] = None,
    target_url: Optional[str] = None,
    ai_type: str = "gliner",
    use_onnx: bool = True,
    onnx_dir: Optional[str] = None,
    device: str = "auto",
    output_file: str = "pipeline_results_compumarts.json",
    checkpoint_file: str = "pipeline_results_compumarts.checkpoint.jsonl",
    trace_file: str = "pipeline_trace_compumarts.jsonl",
    envelope_log_file: str = "pipeline_envelopes.txt",
    log_envelopes: bool = False,
) -> None:
    """Execute live scraping and pipeline processing."""
    ai_backend = setup_ai_fallback(ai_type, use_onnx, onnx_dir=onnx_dir, device=device)
    enable_env_logging = log_envelopes or (target_url is not None)
    pipeline = LaptopExtractionPipeline(ai_fallback=ai_backend, log_envelopes=enable_env_logging)
    storage = RawScrapeStorage()

    out_path = Path(output_file)
    ckpt_path = Path(checkpoint_file)
    trace_path = Path(trace_file)
    env_log_path = Path(envelope_log_file) if envelope_log_file else None

    # 1. Single URL Mode
    if target_url:
        logger.info("Running single URL live extraction: %s", target_url)
        t0 = time.time()
        result = pipeline.extract_from_url(target_url, store_name="compumarts")
        elapsed = time.time() - t0

        logger.info("Completed in %.2fs!", elapsed)
        logger.info("Identified CPU: %s", result.cpu_key)
        logger.info("Component Envelopes generated: %d", len(result.component_envelopes_generated))
        logger.info("Component AI results resolved: %d", len(result.component_results))
        logger.info("Validation rejections: %d", len(result.validation_rejections))

        if result.provenance_record:
            with trace_path.open("a", encoding="utf-8") as tf:
                tf.write(json.dumps(result.provenance_record, ensure_ascii=False) + "\n")
            logger.info("Saved provenance trace to %s", trace_path)

        if env_log_path:
            raw_target_prod = result.raw_product or RawScrapedProduct(
                url=target_url,
                store="compumarts",
                title=result.specs.get("identity", {}).get("laptop_model") or target_url,
                raw_html="",
            )
            report = ProvenanceTracker.format_component_envelope_text_report(
                raw_product=raw_target_prod,
                component_envelopes=result.component_envelopes_generated,
                component_results=result.component_results,
                validation_rejections=result.validation_rejections,
                final_specs=result.specs,
                product_index=1,
                total_products=1,
            )
            env_log_path.write_text(report, encoding="utf-8")
            logger.info("Saved full envelope audit text file to %s", env_log_path)

        if result.component_envelopes_generated:
            print("\n" + "-" * 60)
            print("COMPONENT ENVELOPE & FALLBACK RESOLUTION SUMMARY:")
            print("-" * 60)
            comp_res_by_name = {r.component_name: r for r in result.component_results}
            gate2_rej_by_field = {
                r["field_path"]: r for r in result.validation_rejections if r.get("gate") == 2
            }
            for env in result.component_envelopes_generated:
                comp_res = comp_res_by_name.get(env.component_name)
                print(f"  Subsystem:  {env.component_name.upper()}")
                print(f"  Anchors:    {list(env.locked_fields)}")
                print(f"  Targets:    {[k for k, v in env.sub_schema.items() if v is None]}")
                if comp_res:
                    print(f"  AI Model:   {comp_res.model_name}")
                    print(f"  Extracted:  {comp_res.extracted_fields}")
                else:
                    print(f"  AI Model:   None")
                for k, v in env.sub_schema.items():
                    if v is None:
                        full_k = f"{env.component_name}.{k}"
                        if full_k in gate2_rej_by_field:
                            print(f"    - {k}: REJECTED at Gate 2 ({gate2_rej_by_field[full_k].get('reason')})")
                        elif comp_res and comp_res.extracted_fields.get(k) is not None:
                            print(f"    - {k}: ACCEPTED ({comp_res.extracted_fields.get(k)})")
                        else:
                            print(f"    - {k}: UNRESOLVED / NULL")
                print()
            print("-" * 60)

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

    # Open checkpoint, trace, and envelope text streams
    with ckpt_path.open("w", encoding="utf-8") as ckpt_f, \
         trace_path.open("w", encoding="utf-8") as trace_f, \
         (env_log_path.open("w", encoding="utf-8") if env_log_path else open(os.devnull, "w")) as env_f:

        if env_log_path:
            env_f.write(
                "=" * 80 + "\n"
                + "COMPUMARTS SPECIFICATION EXTRACTION - DETAILED ENVELOPE AUDIT LOG\n"
                + f"Generated At: {datetime.now(timezone.utc).isoformat()}\n"
                + f"AI Fallback Backend: {ai_type} (onnx={use_onnx})\n"
                + "=" * 80 + "\n\n"
            )

        for idx, prod in enumerate(catalog_products, start=1):
            logger.info("[%d/%d] Processing %s...", idx, total_found, prod.title[:60])
            t_item = time.time()

            prod_specs = dict(prod.specs or {})
            final_sku = prod.retailer_sku or prod.mpn
            final_mpn = prod.mpn or prod.retailer_sku
            if final_sku and "SKU" not in prod_specs:
                prod_specs["SKU"] = final_sku
            if final_mpn and "Part Number" not in prod_specs:
                prod_specs["Part Number"] = final_mpn

            raw_prod = RawScrapedProduct(
                url=prod.product_url,
                store="compumarts",
                title=prod.title,
                raw_html="",  # raw HTML already archived during scraper crawl
                raw_tables={"specs": prod_specs},
                raw_sections={"Description": prod.raw_description or ""},
                price=prod.price_egp,
                currency="EGP",
                in_stock=prod.in_stock,
                retailer_sku=final_sku,
                mpn=final_mpn,
            )

            res = pipeline.process_raw_product(raw_prod)
            elapsed = time.time() - t_item

            stats["processed"] += 1
            if res.cpu_key:
                stats["cpu_identified"] += 1
            stats["envelopes_total"] += len(res.component_envelopes_generated)
            stats["ai_resolved"] += len(res.component_results)
            stats["gate1_rejections"] += sum(1 for r in res.validation_rejections if r.get("gate") == 1)
            stats["gate2_rejections"] += sum(1 for r in res.validation_rejections if r.get("gate") == 2)

            item_record = {
                "url": prod.product_url,
                "title": prod.title,
                "price_egp": prod.price_egp,
                "cpu_key": res.cpu_key,
                "specs": res.specs,
                "source_table": prod.specs or {},
                "envelopes_count": len(res.component_envelopes_generated),
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

            # Stream detailed envelope audit text if envelopes were generated
            if env_log_path and res.component_envelopes_generated:
                report = ProvenanceTracker.format_component_envelope_text_report(
                    raw_product=raw_prod,
                    component_envelopes=res.component_envelopes_generated,
                    component_results=res.component_results,
                    validation_rejections=res.validation_rejections,
                    final_specs=res.specs,
                    product_index=idx,
                    total_products=total_found,
                )
                env_f.write(report + "\n\n")
                env_f.flush()

        if env_log_path:
            env_f.write(
                "\n" + "=" * 80 + "\n"
                + "ENVELOPE AUDIT SUMMARY:\n"
                + f"Total Laptops Processed:     {stats['processed']}\n"
                + f"Total Component Envelopes:   {stats['envelopes_total']}\n"
                + f"AI Fallback Resolved:        {stats['ai_resolved']}\n"
                + f"Gate 2 AI Rejections:        {stats['gate2_rejections']}\n"
                + "=" * 80 + "\n"
            )

    # Save final output
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d structured products to %s", len(results), out_path)
    logger.info("Saved provenance audit traces to %s", trace_path)
    if env_log_path:
        logger.info("Saved detailed envelope audit file to %s", env_log_path)

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
    if env_log_path:
        print(f"Envelope Audit File:         {env_log_path.resolve()}")
    print("=" * 60 + "\n")


def export_envelopes_from_results(
    results_path: str = "pipeline_results_compumarts.json",
    envelope_log_file: str = "pipeline_envelopes.txt",
    ai_type: str = "gliner",
    use_onnx: bool = True,
    onnx_dir: Optional[str] = None,
) -> None:
    """Generate comprehensive pipeline_envelopes.txt from existing results file using captured source tables."""
    rf = Path(results_path)
    if not rf.exists():
        logger.error("Results file %s not found.", rf)
        return

    logger.info("Generating envelope audit log from %s...", rf)
    products_data = json.loads(rf.read_text(encoding="utf-8"))
    logger.info("Loaded %d products from %s", len(products_data), rf)

    ai_backend = setup_ai_fallback(ai_type, use_onnx, onnx_dir=onnx_dir)
    pipeline = LaptopExtractionPipeline(ai_fallback=ai_backend, log_envelopes=False)
    env_log_path = Path(envelope_log_file)

    envelopes_count = 0
    resolved_count = 0
    rejected_count = 0
    laptops_with_envelopes = 0

    with env_log_path.open("w", encoding="utf-8") as env_f:
        env_f.write(
            "=" * 80 + "\n"
            + "COMPUMARTS SPECIFICATION EXTRACTION - DETAILED ENVELOPE AUDIT LOG\n"
            + f"Generated At: {datetime.now(timezone.utc).isoformat()}\n"
            + f"Source Results File: {rf.resolve()}\n"
            + f"Total Catalog Laptops: {len(products_data)}\n"
            + f"AI Fallback Backend: {ai_type} (onnx={use_onnx})\n"
            + "=" * 80 + "\n\n"
        )

        for idx, item in enumerate(products_data, start=1):
            raw_prod = RawScrapedProduct(
                url=item.get("url", ""),
                store="compumarts",
                title=item.get("title", ""),
                raw_html="",
                raw_tables={"specs": item.get("source_table", {})},
                raw_sections={},
                price=item.get("price_egp"),
                currency="EGP",
            )
            res = pipeline.process_raw_product(raw_prod)
            if res.component_envelopes_generated:
                laptops_with_envelopes += 1
                envelopes_count += len(res.component_envelopes_generated)
                resolved_count += len([
                    r for r in res.component_results
                    if any(v is not None for v in r.extracted_fields.values())
                ])
                rejected_count += sum(1 for r in res.validation_rejections if r.get("gate") == 2)

                report = ProvenanceTracker.format_component_envelope_text_report(
                    raw_product=raw_prod,
                    component_envelopes=res.component_envelopes_generated,
                    component_results=res.component_results,
                    validation_rejections=res.validation_rejections,
                    final_specs=res.specs,
                    product_index=idx,
                    total_products=len(products_data),
                )
                env_f.write(report + "\n\n")

        env_f.write(
            "\n" + "=" * 80 + "\n"
            + "ENVELOPE AUDIT SUMMARY:\n"
            + f"Total Catalog Laptops Evaluated:  {len(products_data)}\n"
            + f"Laptops Generating Envelopes:     {laptops_with_envelopes}\n"
            + f"Laptops 100% Deterministic:       {len(products_data) - laptops_with_envelopes}\n"
            + f"Total Component Envelopes:        {envelopes_count}\n"
            + f"Component AI Fallbacks Extracted: {resolved_count}\n"
            + f"Gate 2 AI Rejections:             {rejected_count}\n"
            + "=" * 80 + "\n"
        )

    logger.info("Saved complete envelope audit log to %s (%d laptops generated %d envelopes).", env_log_path, laptops_with_envelopes, envelopes_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live CompuMarts Laptop Extraction Pipeline")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of laptops to scrape/process")
    parser.add_argument("--url", type=str, default=None, help="Process a single laptop PDP URL directly")
    parser.add_argument("--ai", choices=["gliner", "nuextract", "none"], default="gliner", help="AI Fallback backend")
    parser.add_argument("--no-onnx", action="store_true", help="Disable ONNX and run GLiNER with PyTorch")
    parser.add_argument("--output", type=str, default="pipeline_results_compumarts.json", help="Output JSON path")
    parser.add_argument("--onnx-dir", type=str, default=None, help="Path to local ONNX model directory (e.g. for NuExtract ONNX GenAI)")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto", help="Execution device for AI fallback (auto/cuda/cpu)")
    parser.add_argument("--checkpoint", type=str, default="pipeline_results_compumarts.checkpoint.jsonl", help="Checkpoint JSONL path")
    parser.add_argument("--trace-file", type=str, default="pipeline_trace_compumarts.jsonl", help="Provenance audit trace JSONL path")
    parser.add_argument(
        "--envelope-log",
        type=str,
        default="pipeline_envelopes.txt",
        help="Path to write exhaustive human-readable envelope details text file",
    )
    parser.add_argument(
        "--export-envelopes",
        action="store_true",
        default=False,
        help="Generate pipeline_envelopes.txt directly from existing pipeline_results_compumarts.json without scraping",
    )
    parser.add_argument(
        "--log-envelopes",
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Log created extraction envelopes, AI fallback predictions, and Gate 2 decisions in real-time",
    )

    args = parser.parse_args()

    if args.export_envelopes:
        export_envelopes_from_results(
            results_path=args.output,
            envelope_log_file=args.envelope_log,
            ai_type=args.ai,
            use_onnx=not args.no_onnx,
            onnx_dir=args.onnx_dir,
        )
        return

    run_pipeline(
        limit=args.limit,
        target_url=args.url,
        ai_type=args.ai,
        use_onnx=not args.no_onnx,
        onnx_dir=args.onnx_dir,
        device=args.device,
        output_file=args.output,
        checkpoint_file=args.checkpoint,
        trace_file=args.trace_file,
        envelope_log_file=args.envelope_log,
        log_envelopes=args.log_envelopes,
    )


if __name__ == "__main__":
    main()

