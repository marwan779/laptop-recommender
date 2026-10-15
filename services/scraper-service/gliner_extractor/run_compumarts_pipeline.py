"""Full End-to-End CompuMarts Scraping and Hybrid Extraction Pipeline.

Flow:
1. Discovers and scrapes raw specification tables for all in-stock PDPs from CompuMarts Egypt
   using production CompumartsStoreScraper.
2. Filters out non-laptop items (accessories, bags, monitors, desktops).
3. Extracts specifications through dedicated CompumartsExtractor (Tier 1).
4. Hands off complex / unmapped fields with ContextEnvelopes to GLiNER (Tier 2).
5. Supports checkpoint streaming (.checkpoint.jsonl) and atomic file replace.
6. Emits structured results to hybrid_results.json and execution metrics to run_summary.json.

Usage:
    python gliner_extractor/run_compumarts_pipeline.py
    python gliner_extractor/run_compumarts_pipeline.py --live
    python gliner_extractor/run_compumarts_pipeline.py --resume
    python gliner_extractor/run_compumarts_pipeline.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.stores.compumarts import CompumartsStoreScraper
from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.hybrid_extractor import HybridLaptopExtractor

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hybrid_results.json")
DEFAULT_SUMMARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_summary.json")
CACHE_FILE = os.path.join(
    r"C:\Users\COMPUMARTS\.gemini\antigravity\brain\6c47eca0-37e4-4ea1-98d4-14195fc0dba0\scratch",
    "compumarts_fresh_live_pdp_cache.json"
)


def scrape_live_compumarts_pdps(limit: int | None = None) -> list[dict[str, Any]]:
    """Crawl live CompuMarts catalog and extract raw PDP tables using production scraper."""
    print("[*] Stage 1 & 2: Scraping live CompuMarts catalog with CompumartsStoreScraper...")
    scraper = CompumartsStoreScraper()
    products = scraper.scrape_catalog(level=2, limit=limit)

    laptops: list[dict[str, Any]] = []
    for p in products:
        laptops.append({
            "product_url": p.product_url,
            "title": p.title,
            "specs": p.specs or {},
            "metadata": {
                "mpn": p.mpn,
                "retailer_sku": p.retailer_sku,
                "price": p.price_egp,
                "price_egp": p.price_egp,
                "price_str": p.price_str,
                "in_stock": p.in_stock,
            },
        })
    print(f"[OK] Live scrape finished: {len(laptops)} products retrieved.")
    return laptops


def load_cached_compumarts_pdps(limit: int | None = None) -> list[dict[str, Any]]:
    """Load from freshly crawled raw specs or store results."""
    # 1. Check local_extractor/my_raw_specs.json
    raw_specs_file = os.path.join(PROJECT_ROOT, "local_extractor", "my_raw_specs.json")
    if os.path.exists(raw_specs_file):
        try:
            with open(raw_specs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                laptops = []
                for p in data:
                    laptops.append({
                        "product_url": p.get("product_url", ""),
                        "title": p.get("title", ""),
                        "specs": p.get("specs", {}),
                        "metadata": {
                            "mpn": p.get("mpn") or p.get("retailer_sku"),
                            "retailer_sku": p.get("retailer_sku"),
                            "price_egp": p.get("price_egp"),
                            "price": p.get("price_egp"),
                            "brand": p.get("brand"),
                            "in_stock": p.get("in_stock", True),
                        },
                    })
                    if limit and len(laptops) >= limit:
                        break
                if laptops:
                    return laptops
        except Exception as e:
            logger.warning("Failed loading my_raw_specs.json: %s", e)

    # 2. Check store_compumarts.json
    store_file = os.path.join(PROJECT_ROOT, "scraping-results", "stores", "store_compumarts.json")
    if os.path.exists(store_file):
        try:
            with open(store_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            prods = data.get("products", [])
            laptops = []
            for p in prods:
                laptops.append({
                    "product_url": p.get("product_url", ""),
                    "title": p.get("title", ""),
                    "specs": p.get("specs", {}),
                    "metadata": {
                        "mpn": p.get("mpn") or p.get("retailer_sku"),
                        "retailer_sku": p.get("retailer_sku"),
                        "price_egp": p.get("price_egp"),
                        "price": p.get("price_egp"),
                        "brand": p.get("brand"),
                        "in_stock": p.get("in_stock", True),
                    },
                })
                if limit and len(laptops) >= limit:
                    break
            if laptops:
                return laptops
        except Exception as e:
            logger.warning("Failed loading store_compumarts.json: %s", e)

    # 3. Check scratch cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            laptops = []
            for url, data in cache_data.items():
                laptops.append({
                    "product_url": url,
                    "title": data.get("title", ""),
                    "specs": data.get("specs", {}),
                    "metadata": data.get("metadata", {}),
                })
                if limit and len(laptops) >= limit:
                    break
            return laptops
        except Exception as e:
            logger.warning("Failed loading CACHE_FILE: %s", e)

    return []


def main():
    parser = argparse.ArgumentParser(
        description="Run robust end-to-end CompuMarts scraping and hybrid extraction pipeline."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform a fresh live crawl over CompuMarts website instead of using cache.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume execution from existing checkpoint (.checkpoint.jsonl).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Output path for structured JSON results (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--summary",
        type=str,
        default=DEFAULT_SUMMARY,
        help=f"Output path for execution summary JSON (default: {DEFAULT_SUMMARY}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of laptops to process.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="urchade/gliner_base",
        help="GLiNER model name on Hugging Face for Tier 2 fallback.",
    )
    args = parser.parse_args()

    output_path = os.path.abspath(args.output)
    summary_path = os.path.abspath(args.summary)
    checkpoint_path = f"{output_path}.checkpoint.jsonl"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("=" * 80)
    print("🚀 COMPUMARTS ROBUST HYBRID PIPELINE (TIER 1 + TIER 2 GLINER)")
    print(f"[*] Target Output:     {output_path}")
    print(f"[*] Checkpoint File:   {checkpoint_path}")
    print(f"[*] Summary Output:    {summary_path}")
    print("=" * 80)

    # 1. Ingest raw tables
    laptops: list[dict[str, Any]] = []
    if args.live:
        laptops = scrape_live_compumarts_pdps(limit=args.limit)
    else:
        print("[*] Loading cached raw PDP tables...")
        laptops = load_cached_compumarts_pdps(limit=args.limit)
        if not laptops:
            print("[*] Cache not found. Running live crawl...")
            laptops = scrape_live_compumarts_pdps(limit=args.limit)

    if not laptops:
        print("[ERROR] No items found to process.")
        sys.exit(1)

    print(f"\n[OK] Retrieved {len(laptops)} items from catalog.")

    # 2. Filter non-laptop products
    helper_extractor = CompumartsExtractor()
    valid_laptops: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []

    for item in laptops:
        title = item.get("title", "")
        specs = item.get("specs", {})
        p_type = helper_extractor.detect_product_type(specs, title)
        if p_type != "laptop":
            skipped_items.append({
                "title": title,
                "url": item.get("product_url", ""),
                "detected_type": p_type,
                "reason": f"Filtered out non-laptop category ({p_type})",
            })
        else:
            valid_laptops.append(item)

    print(f"[OK] Filtered catalog: {len(valid_laptops)} valid laptops ({len(skipped_items)} non-laptop items skipped).")
    print("=" * 80)

    # 3. Checkpoint handling (--resume)
    results: list[dict[str, Any]] = []
    processed_urls: set[str] = set()

    if args.resume and os.path.exists(checkpoint_path):
        print(f"[*] Resuming from checkpoint: {checkpoint_path}...")
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_s = line.strip()
                    if line_s:
                        record = json.loads(line_s)
                        rec_status = record.get("structured", {}).get("extraction_meta", {}).get("status")
                        if rec_status == "failed":
                            # Skip failed records so they are re-processed
                            continue
                        results.append(record)
                        if record.get("product_url"):
                            processed_urls.add(record["product_url"])
            # Rewrite checkpoint to exclude failed records
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                for r in results:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"[OK] Loaded {len(results)} valid previously processed records from checkpoint (failed records queued for retry).")
        except Exception as e:
            logger.warning("Error reading checkpoint file: %s", e)

    # 4. Initialize Hybrid Extractor
    print("[*] Initializing Hybrid Laptop Extractor (CompumartsExtractor + GLiNER)...")
    extractor = HybridLaptopExtractor(model_name=args.model)
    print("[*] Warming up GLiNER model...")
    try:
        extractor.gliner.extract_entities("Warmup CPU Intel Core i7 16GB RAM", ["processor model", "ram capacity"], threshold=0.35)
        print("[OK] GLiNER warmed up successfully.")
    except Exception as w_exc:
        logger.warning("GLiNER warmup warning: %s", w_exc)

    # 5. Extraction Loop
    latencies: list[float] = []
    total_envelopes = 0
    total_gliner_calls = 0
    status_counts = {"ok": 0, "partial": 0, "failed": 0}

    # Count statuses from previously loaded results
    for r in results:
        r_st = r.get("structured", {}).get("extraction_meta", {}).get("status", "ok")
        status_counts[r_st] = status_counts.get(r_st, 0) + 1

    print(f"\n[*] Processing laptops through 2-Tier Pipeline...")
    t_start = time.perf_counter()

    def flush_and_save_final() -> tuple[float, float]:
        t_dur = time.perf_counter() - t_start
        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

        # Atomic File Replace on Write for hybrid_results.json
        temp_output_path = f"{output_path}.tmp"
        with open(temp_output_path, "w", encoding="utf-8") as out_f:
            json.dump(results, out_f, indent=2, ensure_ascii=False)
        os.replace(temp_output_path, output_path)

        # Write run_summary.json
        run_summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_catalog_discovered": len(laptops),
            "valid_laptops_count": len(valid_laptops),
            "skipped_items_count": len(skipped_items),
            "processed_results_count": len(results),
            "status_breakdown": status_counts,
            "runtime_seconds": round(t_dur, 2),
            "average_latency_ms": round(avg_lat, 2),
            "min_latency_ms": round(min(latencies), 2) if latencies else 0.0,
            "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
            "total_envelopes_created": total_envelopes,
            "total_gliner_calls": total_gliner_calls,
            "gliner_tokens": {
                "max_tokens_seen": extractor.gliner.max_tokens_seen,
                "truncations_prevented": extractor.gliner.truncations_prevented,
            },
            "skipped_items": skipped_items,
        }
        with open(summary_path, "w", encoding="utf-8") as sum_f:
            json.dump(run_summary, sum_f, indent=2, ensure_ascii=False)

        return t_dur, avg_lat

    try:
        # Open checkpoint in append mode
        with open(checkpoint_path, "a", encoding="utf-8") as checkpoint_f:
            for idx, laptop in enumerate(valid_laptops):
                url = laptop.get("product_url", "")
                title = laptop.get("title", "")
                specs = laptop.get("specs", {})

                if url in processed_urls:
                    continue

                try:
                    structured, meta = extractor.extract(
                        title=title,
                        specs=specs,
                        metadata=laptop.get("metadata", laptop),
                        store="compumarts",
                    )
                except Exception as exc:
                    logger.exception("Catastrophic error in laptop extraction for %s: %s", url, exc)
                    from gliner_extractor.schema import empty_structured
                    structured = empty_structured()
                    structured["extraction_meta"]["status"] = "failed"
                    structured["extraction_meta"]["warnings"].append(f"fatal_loop_error: {str(exc)}")
                    meta = {
                        "total_time_ms": 0.0,
                        "layer1_time_ms": 0.0,
                        "gliner_time_ms": 0.0,
                        "gliner_calls_count": 0,
                        "envelopes_count": 0,
                    }

                dur_ms = meta["total_time_ms"]
                latencies.append(dur_ms)
                total_envelopes += meta.get("envelopes_count", 0)
                total_gliner_calls += meta.get("gliner_calls_count", 0)
                rec_status = structured.get("extraction_meta", {}).get("status", "ok")
                status_counts[rec_status] = status_counts.get(rec_status, 0) + 1

                record = {
                    "index": len(results),
                    "title": title,
                    "product_url": url,
                    "latency_ms": round(dur_ms, 2),
                    "structured": structured,
                }
                results.append(record)
                processed_urls.add(url)

                # Stream immediately to checkpoint
                checkpoint_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                checkpoint_f.flush()

                # Compact progress log
                brand = structured["identity"].get("brand") or "N/A"
                cpu_name = (
                    structured["cpu"].get("full_name")
                    or f"{structured['cpu'].get('line') or ''} {structured['cpu'].get('model') or ''}".strip()
                    or "N/A"
                )
                gpu_name = structured["gpu"].get("model") or "N/A"
                ram_cap = structured["memory"].get("capacity_gb")
                st_cap = structured["storage"].get("capacity_gb")
                res_str = (
                    structured["display"].get("resolution")
                    or (f"{structured['display'].get('size_inches')}\"" if structured['display'].get('size_inches') else "N/A")
                )

                print(
                    f"  [{len(results):03d}/{len(valid_laptops):03d}] {dur_ms:6.1f}ms | "
                    f"Status: {rec_status.upper():<7} | "
                    f"Brand: {brand[:8]:<8} | "
                    f"CPU: {cpu_name[:24]:<24} | "
                    f"GPU: {gpu_name[:18]:<18} | "
                    f"RAM: {ram_cap}GB | "
                    f"SSD: {st_cap}GB | "
                    f"Disp: {res_str[:11]}"
                )
    except KeyboardInterrupt:
        print("\n[!] KeyboardInterrupt caught: flushing checkpoint and saving final results...")
    finally:
        total_time_s, avg_latency = flush_and_save_final()

    print("\n" + "=" * 80)
    print("🎯 FULL PIPELINE EXECUTION SUMMARY:")
    print(f"  - Total catalog items:                {len(laptops)}")
    print(f"  - Valid laptops processed:            {len(results)}")
    print(f"  - Non-laptop items skipped:           {len(skipped_items)}")
    print(f"  - Status breakdown:                   {status_counts}")
    print(f"  - Total pipeline time:                {total_time_s:.2f}s")
    print(f"  - Average latency per laptop:         {avg_latency:.2f} ms")
    print(f"  - ContextEnvelopes created:           {total_envelopes}")
    print(f"  - GLiNER fallback calls:              {total_gliner_calls}")
    print(f"  - GLiNER max tokens observed:         {extractor.gliner.max_tokens_seen}")
    print(f"  - Output JSON saved to:               {output_path}")
    print(f"  - Run summary saved to:               {summary_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
