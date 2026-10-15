import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuextract_sandbox.scraper import PDPScraper
from nuextract_sandbox.combiner import SpecCombiner
from nuextract_sandbox.extractor import NuExtractor

DEFAULT_URL = "https://www.compumarts.com/collections/laptop/products/acer-nitro-v-15-core-i9-13900h-rtx-5050-165hz-egypt"

def main():
    parser = argparse.ArgumentParser(description="Test NuExtract 3-layer sandbox against a live PDP.")
    parser.add_argument("--url", type=str, default=DEFAULT_URL, help="Live laptop PDP URL to scrape and extract.")
    parser.add_argument("--model", type=str, default="numind/NuExtract-v1.5", help="HuggingFace model name.")
    parser.add_argument(
        "--strategy",
        type=str,
        default="area_by_area",
        choices=["area_by_area", "unified"],
        help="Extraction strategy: 'area_by_area' (isolated context per area) or 'unified' (single full-doc pass).",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("NUEXTRACT SANDBOX: 3-LAYER LIVE PDP TEST")
    print("=" * 70)
    print(f"Target URL: {args.url}")
    print(f"Model:      {args.model}")
    print(f"Strategy:   {args.strategy}\n")

    # -------------------------------------------------------------
    # Layer 1: Live PDP Scraper
    # -------------------------------------------------------------
    print("[Layer 1] Scraping live PDP HTML...")
    scraper = PDPScraper()
    t0_scrape = time.time()
    try:
        scraped_data = scraper.fetch_pdp(args.url)
        scrape_time = time.time() - t0_scrape
        print(f"-> Scraped title: '{scraped_data['title']}'")
        print(f"-> Raw specs count: {len(scraped_data['raw_specs'])} rows in {scrape_time:.2f}s")
    except Exception as e:
        print(f"Scraper error: {e}")
        return

    # -------------------------------------------------------------
    # Layer 2: Spec Combiner
    # -------------------------------------------------------------
    print("\n[Layer 2] Combining raw fields into clean context...")
    combiner = SpecCombiner()
    area_blocks = combiner.combine_area_blocks(scraped_data)
    markdown_doc = combiner.combine_unified_markdown(scraped_data)

    print(f"-> Formed {len(area_blocks)} component area blocks.")
    for area, blk in area_blocks.items():
        row_count = len(blk.splitlines())
        print(f"   [{area:16}]: {row_count} lines of context")

    # -------------------------------------------------------------
    # Layer 3: NuExtract Schema Extraction
    # -------------------------------------------------------------
    print(f"\n[Layer 3] Extracting structured JSON via NuExtract ({args.strategy})...")
    extractor = NuExtractor(model_name=args.model)

    if args.strategy == "area_by_area":
        print("\nExecuting area-by-area isolated extraction passes...")
        structured, latency_s = extractor.extract_area_by_area(area_blocks)
    else:
        print("\nExecuting unified full-document extraction pass...")
        structured, latency_s = extractor.extract(markdown_doc)

    print(f"\n-> Extraction completed in {latency_s:.2f}s total latency.")

    # Save output JSON
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"nuextract_{args.strategy}_result.json"

    final_payload = {
        "url": args.url,
        "title": scraped_data["title"],
        "metadata": scraped_data["metadata"],
        "extraction_method": "nuextract_sandbox",
        "model_name": args.model,
        "latency_seconds": round(latency_s, 2),
        "structured": structured,
        "raw_specs_count": len(scraped_data["raw_specs"]),
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print(f"SUCCESS! Output written to {out_file}")
    print("=" * 70)
    print(json.dumps(structured, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

