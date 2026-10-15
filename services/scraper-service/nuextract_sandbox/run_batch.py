import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuextract_sandbox.scraper import PDPScraper
from nuextract_sandbox.hybrid_nuextract import HybridNuExtractPipeline

# 8 diverse laptops across 5 major brands (Acer, Lenovo, HP, MSI, ASUS, Dell)
TEST_URLS = [
    {
        "brand": "Acer",
        "family": "Aspire Go 16",
        "url": "https://www.compumarts.com/collections/laptop/products/acer-aspire-go-16-ag16-71p-9142-intel-core-9-270h-16gb-512gb-egypt"
    },
    {
        "brand": "Acer",
        "family": "Nitro V 15",
        "url": "https://www.compumarts.com/collections/laptop/products/acer-nitro-v-15-anv15-a31-r8la-ryzen-7-170-rtx-5060-16gb-512gb-egypt"
    },
    {
        "brand": "Lenovo",
        "family": "LOQ 15",
        "url": "https://www.compumarts.com/collections/laptop/products/lenovo-loq-15irx9-core-i7-rtx-4050-gaming-laptop-egypt"
    },
    {
        "brand": "HP",
        "family": "HP 255 G10",
        "url": "https://www.compumarts.com/collections/laptop/products/hp-255-g10-b39stat-a2n-ryzen-5-7535u-16gb-512gb-egypt"
    },
    {
        "brand": "MSI",
        "family": "Cyborg 15",
        "url": "https://www.compumarts.com/collections/laptop/products/msi-cyborg-15-black-edition-a13ve-i7-13620h-rtx-4050-144hz-egypt"
    },
    {
        "brand": "ASUS",
        "family": "TUF Gaming F16",
        "url": "https://www.compumarts.com/collections/laptop/products/asus-tuf-f16-fx608jhi-tu657w-gaming-laptop-i7-14650hx-rtx-5050-egypt"
    },
    {
        "brand": "Dell",
        "family": "Pro 15 Essential",
        "url": "https://www.compumarts.com/collections/laptop/products/dell-pro-15-essential-pv15250-core-i7-1355u-laptop-egypt"
    },
    {
        "brand": "Lenovo",
        "family": "Yoga 7 2-in-1",
        "url": "https://www.compumarts.com/collections/laptop/products/lenovo-yoga-7-2-in-1-intel-core-ultra-7-14-inch-laptop-egypt"
    },
]

def main():
    parser = argparse.ArgumentParser(description="Test Hybrid Tier 1 + NuExtract pipeline on 8 live PDPs.")
    parser.add_argument("--limit", type=int, default=8, help="Number of laptops to run (default: 8).")
    parser.add_argument("--model", type=str, default="numind/NuExtract-v1.5", help="Model name.")
    args = parser.parse_args()

    print("=" * 80)
    print("HYBRID PIPELINE: LIVE MULTI-LAPTOP AUDIT (TIER 1 + NUEXTRACT FALLBACK + VALIDATORS)")
    print("=" * 80)
    print(f"Target count: {min(args.limit, len(TEST_URLS))} diverse live laptops across major brands\n")

    scraper = PDPScraper()
    pipeline = HybridNuExtractPipeline(model_name=args.model)

    results = []
    overall_t0 = time.time()

    for idx, item in enumerate(TEST_URLS[:args.limit], 1):
        brand_hint = item["brand"]
        family_hint = item["family"]
        url = item["url"]

        print("-" * 80)
        print(f"[{idx}/{args.limit}] Scraping & Extracting: {brand_hint} {family_hint}")
        print(f"URL: {url}")

        t0_lap = time.time()
        try:
            scraped = scraper.fetch_pdp(url)
            print(f"-> Live DOM scraped: '{scraped['title'][:65]}...' ({len(scraped['raw_specs'])} specs)")
        except Exception as e:
            print(f"-> Scraper failed for {url}: {e}")
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

        # Quick summary line
        c_cpu = f"{structured.get('cpu', {}).get('manufacturer')} {structured.get('cpu', {}).get('model')}"
        c_gpu = f"{structured.get('gpu', {}).get('model')} ({structured.get('gpu', {}).get('vram_gb')}GB)"
        c_ram = f"{structured.get('memory', {}).get('capacity_gb')}GB {structured.get('memory', {}).get('memory_type')}"
        c_stg = f"{structured.get('storage', {}).get('capacity_gb')}GB"
        c_dsp = f"{structured.get('display', {}).get('size_inches')}\" {structured.get('display', {}).get('resolution')}"
        print(f"-> Result: CPU=[{c_cpu}] | GPU=[{c_gpu}] | RAM=[{c_ram}] | Storage=[{c_stg}] | Display=[{c_dsp}]")
        print(f"-> Latency: {metrics['total_latency_seconds']}s (Tier 1: {metrics['tier1_latency_seconds']*1000:.1f}ms, NuExtract calls: {metrics['nuextract_calls_count']})\n")

    total_time = time.time() - overall_t0

    # Save final results
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "random_laptops_results.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("=" * 80)
    print(f"ALL DONE! Processed {len(results)} live laptops in {total_time:.2f}s (avg: {total_time/len(results):.2f}s/laptop)")
    print(f"Results saved to: {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()

