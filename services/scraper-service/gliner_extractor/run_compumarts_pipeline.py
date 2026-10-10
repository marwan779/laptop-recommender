"""Full End-to-End CompuMarts Scraping and Hybrid Extraction Pipeline.

Flow:
1. Scrapes raw specification tables for all in-stock PDPs from CompuMarts Egypt.
2. Extracts specifications through dedicated CompumartsExtractor (Tier 1).
3. Hands off complex / unmapped fields with ContextEnvelopes to GLiNER (Tier 2).
4. Outputs the structured results to gliner_extractor/hybrid_results.json as usual.

Usage:
    # Run full flow on all live PDPs (uses fresh cached PDPs or live scrape)
    python gliner_extractor/run_compumarts_pipeline.py

    # Run full flow with live network re-scrape of every PDP
    python gliner_extractor/run_compumarts_pipeline.py --live

    # Limit to first 10 laptops for quick test
    python gliner_extractor/run_compumarts_pipeline.py --limit 10

    # Custom output file
    python gliner_extractor/run_compumarts_pipeline.py --output gliner_extractor/hybrid_results.json
"""

import argparse
import itertools
import json
import os
import re
import sys
import time
from urllib.parse import urljoin

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from gliner_extractor.hybrid_extractor import HybridLaptopExtractor

DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hybrid_results.json")
CACHE_FILE = os.path.join(
    r"C:\Users\COMPUMARTS\.gemini\antigravity\brain\6c47eca0-37e4-4ea1-98d4-14195fc0dba0\scratch",
    "compumarts_fresh_live_pdp_cache.json"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def scrape_live_compumarts_pdps(limit: int | None = None) -> list[dict]:
    """Crawl collection pages and fetch all raw tables from live PDPs."""
    try:
        from curl_cffi import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("[ERROR] curl_cffi or beautifulsoup4 not installed. Run: pip install curl_cffi beautifulsoup4")
        sys.exit(1)

    base_domain = "https://www.compumarts.com"
    collection_tpl = "https://www.compumarts.com/collections/laptop?filter.v.availability=1&sort_by=created-descending&page={page}"

    discovered_pdps: list[dict] = []
    seen_urls: set[str] = set()

    print("[*] Stage 1: Discovering all in-stock laptops from CompuMarts collection...")
    for page in itertools.count(1):
        url = collection_tpl.format(page=page)
        r = None
        for attempt in range(5):
            try:
                r = requests.get(url, headers=HEADERS, impersonate="chrome120", timeout=20)
                if r.status_code == 200 and len(r.text) > 500:
                    break
                elif r.status_code == 429:
                    time.sleep(3.0 * (attempt + 1))
            except Exception:
                time.sleep(1.0)

        if not r or r.status_code != 200 or len(r.text) < 500:
            print(f"Failed (status {r.status_code if r else 'error'}). Finished collection discovery.")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.find_all("product-card") or soup.find_all(attrs={"class": re.compile(r"card--product|grid__item", re.I)})
        if not cards:
            print("0 cards found. Finished collection discovery.")
            break

        page_new = 0
        for card in cards:
            link = card.find("a", class_=re.compile(r"card-link|js-prod-link", re.I)) or card.find("a", href=re.compile(r"/products/"))
            if not link:
                continue
            href = link.get("href", "").split("?")[0]
            full_url = urljoin(base_domain, href)
            if full_url in seen_urls:
                continue

            title = ""
            title_el = card.find(class_=re.compile(r"card__title|title", re.I))
            if title_el:
                title = title_el.get_text(strip=True)
            if not title:
                title = link.get("aria-label", "").strip() or link.get_text(strip=True)

            seen_urls.add(full_url)
            discovered_pdps.append({"url": full_url, "title": title})
            page_new += 1

            if limit and len(discovered_pdps) >= limit:
                break

        print(f"found {page_new} laptops. Total so far: {len(discovered_pdps)}")
        if page_new == 0 or (limit and len(discovered_pdps) >= limit):
            break

    print(f"[OK] Total in-stock PDPs discovered: {len(discovered_pdps)}")

    # Fetch live PDP tables
    print("\n[*] Stage 2: Crawling raw specification tables for each PDP...")
    from app.core.patterns import PatternEngine

    laptops: list[dict] = []
    for i, item in enumerate(discovered_pdps):
        pdp_url = item["url"]
        card_title = item["title"]

        specs = {}
        page_title = card_title
        metadata = {}
        soup_pdp = None
        for attempt in range(5):
            try:
                rp = requests.get(pdp_url, headers=HEADERS, impersonate="chrome120", timeout=25)
                if rp.status_code == 200 and len(rp.text) > 500:
                    soup_pdp = BeautifulSoup(rp.text, "html.parser")
                    break
                elif rp.status_code == 429:
                    time.sleep(2.0 * (attempt + 1))
            except Exception:
                time.sleep(1.0)
        time.sleep(0.15)

        if soup_pdp:
            t_el = soup_pdp.find("h1")
            if t_el and len(t_el.get_text(strip=True)) > 5:
                page_title = t_el.get_text(strip=True)

            spec_res = PatternEngine.extract_specs(
                soup=soup_pdp,
                title=page_title,
                store_key="compumarts",
                base_url="https://www.compumarts.com",
            )
            specs = spec_res.specs
            if spec_res.mpn:
                metadata["mpn"] = spec_res.mpn

        laptops.append({
            "product_url": pdp_url,
            "title": page_title,
            "specs": specs,
            "metadata": metadata,
        })
        print(f"    [{i+1:03d}/{len(discovered_pdps):03d}] {page_title[:55]} | Specs: {len(specs)} rows")

    return laptops


def load_cached_compumarts_pdps(limit: int | None = None) -> list[dict]:
    """Load from freshly crawled raw specs or store results."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        laptops = []
        for url, data in cache_data.items():
            laptops.append({
                "product_url": url,
                "title": data.get("title", ""),
                "specs": data.get("specs", {}),
            })
            if limit and len(laptops) >= limit:
                break
        if laptops:
            return laptops

    # Check freshest crawled specs first (sorted by created-descending as requested)
    raw_specs_file = os.path.join(PROJECT_ROOT, "local_extractor", "my_raw_specs.json")
    if os.path.exists(raw_specs_file):
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
                        "brand": p.get("brand"),
                    },
                })
                if limit and len(laptops) >= limit:
                    break
            if laptops:
                return laptops

    store_file = os.path.join(PROJECT_ROOT, "scraping-results", "stores", "store_compumarts.json")
    if os.path.exists(store_file):
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
                    "brand": p.get("brand"),
                },
            })
            if limit and len(laptops) >= limit:
                break
        if laptops:
            return laptops

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        laptops = []
        for url, data in cache_data.items():
            laptops.append({
                "product_url": url,
                "title": data.get("title", ""),
                "specs": data.get("specs", {}),
            })
            if limit and len(laptops) >= limit:
                break
        return laptops

    return []


def main():
    parser = argparse.ArgumentParser(description="Run full end-to-end CompuMarts scraping and hybrid extraction pipeline.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform a fresh live crawl over CompuMarts website instead of using cache.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Output path for structured JSON results (default: {DEFAULT_OUTPUT}).",
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

    print("=" * 80)
    print("🚀 COMPUMARTS FULL PIPELINE: SCRAPE RAW TABLES -> STORE EXTRACTOR -> GLINER -> JSON")
    print(f"[*] Target Output: {args.output}")
    print("=" * 80)

    # 1. Scrape raw tables
    laptops: list[dict] = []
    if args.live:
        laptops = scrape_live_compumarts_pdps(limit=args.limit)
    else:
        print("[*] Loading discovered live PDP tables (cached)...")
        laptops = load_cached_compumarts_pdps(limit=args.limit)
        if not laptops:
            print("[*] Cache not found. Running live crawl...")
            laptops = scrape_live_compumarts_pdps(limit=args.limit)

    if not laptops:
        print("[ERROR] No laptops found to process.")
        sys.exit(1)

    print(f"\n[OK] Ready to process {len(laptops)} laptops.")
    print("=" * 80)

    # 2. Initialize 2-Tier Hybrid Extractor
    print("[*] Initializing Hybrid Laptop Extractor (CompumartsExtractor + GLiNER)...")
    extractor = HybridLaptopExtractor(model_name=args.model)

    # 3. Extraction Loop
    results: list[dict] = []
    latencies: list[float] = []
    total_envelopes = 0
    total_gliner_calls = 0

    print(f"\n[*] Processing laptops through 2-Tier Pipeline...")
    t_start = time.perf_counter()

    for idx, laptop in enumerate(laptops):
        title = laptop.get("title", "")
        specs = laptop.get("specs", {})
        url = laptop.get("product_url", "")

        t0 = time.perf_counter()
        structured, meta = extractor.extract(
            title=title,
            specs=specs,
            metadata=laptop,
            store="compumarts",
        )
        dur_ms = meta["total_time_ms"]
        latencies.append(dur_ms)
        total_envelopes += meta.get("envelopes_count", 0)
        total_gliner_calls += meta.get("gliner_calls_count", 0)

        results.append({
            "index": idx,
            "title": title,
            "product_url": url,
            "latency_ms": round(dur_ms, 2),
            "structured": structured,
        })

        # Compact progress output
        brand = structured["identity"].get("brand") or "N/A"
        cpu_name = structured["cpu"].get("full_name") or f"{structured['cpu'].get('line') or ''} {structured['cpu'].get('model') or ''}".strip() or "N/A"
        gpu_name = structured["gpu"].get("model") or "N/A"
        ram_cap = structured["memory"].get("capacity_gb")
        st_cap = structured["storage"].get("capacity_gb")
        res_str = structured["display"].get("resolution") or f"{structured['display'].get('size_inches')}\"" if structured['display'].get('size_inches') else "N/A"

        print(
            f"  [{idx+1:03d}/{len(laptops):03d}] {dur_ms:6.1f}ms | "
            f"Brand: {brand[:8]:<8} | "
            f"CPU: {cpu_name[:24]:<24} | "
            f"GPU: {gpu_name[:18]:<18} | "
            f"RAM: {ram_cap}GB | "
            f"SSD: {st_cap}GB | "
            f"Disp: {res_str[:11]}"
        )

    total_time_s = time.perf_counter() - t_start
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    # 4. Save Output JSON as usual
    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("🎯 FULL PIPELINE EXECUTION SUMMARY:")
    print(f"  - Total laptops scraped & extracted: {len(results)}")
    print(f"  - Total pipeline time:                {total_time_s:.2f}s")
    print(f"  - Average latency per laptop:         {avg_latency:.2f} ms")
    print(f"  - ContextEnvelopes created:           {total_envelopes}")
    print(f"  - GLiNER fallback calls:              {total_gliner_calls}")
    print(f"  - Output JSON saved to:               {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()

