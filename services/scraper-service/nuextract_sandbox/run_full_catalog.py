"""Complete Live Catalog Extraction Runner: Isolated HybridNuExtractPipeline.

Crawls 100% of live CompuMarts laptops over the network, extracts all 36+ fields
(including cpu.cache_mb) using Tier 1 Deterministic Backbone + Area-by-Area NuExtract Fallback + Strict Validators,
and streams progress with atomic checkpointing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.stores.compumarts import CompumartsStoreScraper
from nuextract_sandbox.scraper import PDPScraper
from nuextract_sandbox.hybrid_nuextract import HybridNuExtractPipeline

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_OUTPUT = OUTPUT_DIR / "compumarts_all_laptops_nuextract.json"
CHECKPOINT_FILE = OUTPUT_DIR / "compumarts_all_laptops_checkpoint.jsonl"
SUMMARY_FILE = OUTPUT_DIR / "run_summary.json"


def save_final_results(results: list[dict[str, Any]], elapsed_total: float) -> dict[str, Any]:
    """Save complete structured results and summary metrics."""
    # Write JSON results atomically
    temp_file = DEFAULT_OUTPUT.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    temp_file.replace(DEFAULT_OUTPUT)
    print(f"\n[OK] Saved {len(results)} laptops to {DEFAULT_OUTPUT}")

    # Build summary metrics
    status_counts: dict[str, int] = {}
    field_counts: dict[str, int] = {}
    nuextract_sources: dict[str, int] = {}
    cache_mb_extracted = 0

    for item in results:
        struct = item.get("structured", {})
        meta = struct.get("extraction_meta", {})
        st = meta.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

        cpu = struct.get("cpu", {})
        if cpu.get("cache_mb") is not None:
            cache_mb_extracted += 1

        fs = meta.get("field_sources", {})
        for field_name, source in fs.items():
            field_counts[field_name] = field_counts.get(field_name, 0) + 1
            if source == "nuextract":
                nuextract_sources[field_name] = nuextract_sources.get(field_name, 0) + 1

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_laptops": len(results),
        "total_elapsed_seconds": round(elapsed_total, 2),
        "avg_latency_per_laptop_s": round(elapsed_total / max(1, len(results)), 2),
        "status_distribution": status_counts,
        "cpu_cache_mb_extracted_count": cache_mb_extracted,
        "cpu_cache_mb_extraction_rate": f"{cache_mb_extracted / max(1, len(results)) * 100:.1f}%",
        "nuextract_augmented_fields": nuextract_sources,
        "field_population_counts": field_counts,
    }

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[OK] Run summary written to {SUMMARY_FILE}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run complete isolated HybridNuExtractPipeline on all live CompuMarts laptops.")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint file.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for debug runs.")
    parser.add_argument("--model", type=str, default="numind/NuExtract-v1.5", help="NuExtract model name.")
    args = parser.parse_args()

    print("=" * 80)
    print("HYBRID NUEXTRACT PIPELINE: COMPLETE LIVE COMPUMARTS CATALOG RUN")
    print("=" * 80)

    # 1. Discover all live catalog products from CompuMarts listing pages
    print("[1/3] Crawling live listing pages from CompuMarts...")
    store_scraper = CompumartsStoreScraper()
    catalog_cards = store_scraper.scrape_catalog(level=1)
    print(f"[OK] Found {len(catalog_cards)} live catalog products.")

    if args.limit:
        catalog_cards = catalog_cards[:args.limit]
        print(f"[*] Limiting crawl to {len(catalog_cards)} laptops.")

    # 2. Checkpoint handling
    completed_urls: set[str] = set()
    results: list[dict[str, Any]] = []

    if args.resume and CHECKPOINT_FILE.exists():
        print(f"[*] Resuming from checkpoint: {CHECKPOINT_FILE}")
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        results.append(record)
                        completed_urls.add(record["url"])
                    except json.JSONDecodeError:
                        pass
        print(f"[*] Loaded {len(results)} existing checkpoint records.")

    # 3. Initialize Scraper and HybridNuExtractPipeline
    pdp_scraper = PDPScraper()
    pipeline = HybridNuExtractPipeline(model_name=args.model)

    start_total = time.time()
    checkpoint_handle = open(CHECKPOINT_FILE, "a" if args.resume else "w", encoding="utf-8")

    try:
        for idx, card in enumerate(catalog_cards, 1):
            url = card.product_url
            if url in completed_urls:
                print(f"[{idx}/{len(catalog_cards)}] Skipping already processed: {url}")
                continue

            print("-" * 80)
            print(f"[{idx}/{len(catalog_cards)}] Fetching PDP: {card.title[:65]}...")
            print(f"URL: {url}")

            t0_lap = time.time()
            try:
                scraped = pdp_scraper.fetch_pdp(url)
            except Exception as e:
                print(f"[!] Scraper failed for {url}: {e}")
                # Record error fallback
                continue

            structured, metrics = pipeline.run(
                raw_specs=scraped["raw_specs"],
                title=scraped["title"],
                metadata=scraped["metadata"],
            )

            lap_elapsed = time.time() - t0_lap

            record = {
                "index": idx,
                "url": url,
                "title": scraped["title"],
                "metadata": scraped["metadata"],
                "metrics": metrics,
                "total_elapsed_s": round(lap_elapsed, 2),
                "structured": structured,
            }

            results.append(record)
            completed_urls.add(url)

            # Stream to checkpoint
            checkpoint_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            checkpoint_handle.flush()

            cpu = structured.get("cpu", {})
            gpu = structured.get("gpu", {})
            mem = structured.get("memory", {})
            st = structured.get("storage", {})
            print(
                f"[Summary #{idx}] CPU: {cpu.get('model')} (Cache: {cpu.get('cache_mb')}MB) | "
                f"GPU: {gpu.get('model')} | RAM: {mem.get('capacity_gb')}GB | "
                f"Storage: {st.get('capacity_gb')}GB | Latency: {lap_elapsed:.2f}s"
            )

    except KeyboardInterrupt:
        print("\n[!] KeyboardInterrupt received. Flushing checkpoint and saving results...")
    finally:
        checkpoint_handle.close()
        total_time = time.time() - start_total
        save_final_results(results, total_time)


if __name__ == "__main__":
    main()

