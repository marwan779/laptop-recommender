import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuextract_sandbox.scraper import PDPScraper
from nuextract_sandbox.hybrid_nuextract import HybridNuExtractPipeline

DEFAULT_URL = "https://www.compumarts.com/collections/laptop/products/acer-nitro-v-15-core-i9-13900h-rtx-5050-165hz-egypt"

def main():
    parser = argparse.ArgumentParser(description="Test Hybrid Tier 1 + NuExtract Fallback pipeline on live PDP.")
    parser.add_argument("--url", type=str, default=DEFAULT_URL, help="Live laptop PDP URL to scrape and extract.")
    parser.add_argument("--model", type=str, default="numind/NuExtract-v1.5", help="HuggingFace model name.")
    args = parser.parse_args()

    print("=" * 70)
    print("HYBRID PIPELINE: TIER 1 DETERMINISTIC + NUEXTRACT FALLBACK + VALIDATORS")
    print("=" * 70)
    print(f"Target URL: {args.url}")
    print(f"Model:      {args.model}\n")

    # Step 1: Live Scraping
    print("[Layer 1] Scraping live PDP HTML...")
    scraper = PDPScraper()
    scraped_data = scraper.fetch_pdp(args.url)
    print(f"-> Title: '{scraped_data['title']}'")
    print(f"-> Raw specs count: {len(scraped_data['raw_specs'])} rows\n")

    # Step 2: Hybrid Pipeline
    pipeline = HybridNuExtractPipeline(model_name=args.model)
    structured, metrics = pipeline.run(
        raw_specs=scraped_data["raw_specs"],
        title=scraped_data["title"],
        metadata=scraped_data["metadata"],
    )

    # Step 3: Save Output
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "hybrid_nuextract_result.json"

    final_payload = {
        "url": args.url,
        "title": scraped_data["title"],
        "metadata": scraped_data["metadata"],
        "metrics": metrics,
        "structured": structured,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print(f"SUCCESS! Output saved to {out_file}")
    print("=" * 70)
    print(f"Total Latency: {metrics['total_latency_seconds']}s")
    print(f"Tier 1 Latency: {metrics['tier1_latency_seconds'] * 1000:.2f}ms")
    print(f"NuExtract Latency: {metrics['nuextract_latency_seconds']}s across {metrics['nuextract_calls_count']} calls")
    print(f"Missing Areas Targeted: {metrics['missing_areas_targeted']}\n")

    print("--- SAMPLE EXTRACTED SPECS ---")
    print("Identity:", json.dumps(structured.get("identity"), indent=2))
    print("CPU:", json.dumps(structured.get("cpu"), indent=2))
    print("GPU:", json.dumps(structured.get("gpu"), indent=2))
    print("Memory:", json.dumps(structured.get("memory"), indent=2))
    print("Storage:", json.dumps(structured.get("storage"), indent=2))
    print("Display:", json.dumps(structured.get("display"), indent=2))
    print("Power:", json.dumps(structured.get("power_battery"), indent=2))
    print("Physical:", json.dumps(structured.get("physical"), indent=2))
    print("Field Sources:", json.dumps(structured.get("extraction_meta", {}).get("field_sources"), indent=2))

if __name__ == "__main__":
    main()

