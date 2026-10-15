"""GLiNER Extraction Tester for CompuMarts scraped datasets.

Benchmarks and tests GLiNER entity extraction and Hybrid KeyMatcher architectures.

Usage:
    # Test single laptop in hybrid mode (default)
    python gliner_extractor/test_compumarts.py --index 0

    # Test single laptop in raw GLiNER mode (for comparison)
    python gliner_extractor/test_compumarts.py --index 0 --mode raw_gliner

    # Benchmark first 10 laptops in hybrid mode
    python gliner_extractor/test_compumarts.py --limit 10

    # Benchmark all laptops in my_raw_specs.json and save structured database output
    python gliner_extractor/test_compumarts.py --source local_extractor/my_raw_specs.json --output gliner_extractor/hybrid_results.json
"""

import argparse
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gliner_extractor.schema_mapper import DEFAULT_LABELS, LaptopSchemaMapper
from gliner_extractor.wrapper import GLiNERExtractor
from gliner_extractor.hybrid_extractor import HybridLaptopExtractor
from gliner_extractor.compumarts_extractor import CompumartsExtractor


def fetch_live_pdp(url: str) -> tuple[str, dict[str, str]]:
    """Fetch live CompuMarts PDP and extract title and specs table."""
    try:
        from curl_cffi import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("[ERROR] curl_cffi or beautifulsoup4 not installed. Run: pip install curl_cffi beautifulsoup4")
        sys.exit(1)

    print(f"[*] Fetching live PDP: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch URL, HTTP status: {resp.status_code}")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "html.parser")
    title_el = soup.find("h1") or soup.find("title")
    title = title_el.get_text(strip=True) if title_el else ""

    specs = {}
    table = soup.find("table")
    if table:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) >= 2:
                k = cells[0].get_text(strip=True)
                v = cells[1].get_text(strip=True)
                if k and v:
                    specs[k] = v

    return title, specs


def main():
    parser = argparse.ArgumentParser(description="Test CompuMarts extraction against scraped laptop specs or live URLs.")
    parser.add_argument(
        "--source",
        type=str,
        default="gliner_extractor/audit_119_full.json",
        help="Path to scraped results JSON file.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Live CompuMarts PDP URL to test directly.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["compumarts", "hybrid", "raw_gliner"],
        default="compumarts",
        help="Extraction mode: 'compumarts' (Ultra-fast Dedicated Tier 1 ~0.4ms), 'hybrid' (Tier 1 + Tier 2 GLiNER), or 'raw_gliner'.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="urchade/gliner_base",
        help="GLiNER model name on Hugging Face.",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="Specific laptop index to test (0-based).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of laptops to benchmark.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.35,
        help="Confidence score threshold for entity extraction.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to save full structured JSON results.",
    )
    args = parser.parse_args()

    # 1. Live URL Mode
    if args.url:
        title, specs = fetch_live_pdp(args.url)
        print(f"\n[*] Testing Live PDP: {title}")
        print(f"    Raw spec table fields: {len(specs)}")
        print("-" * 80)

        t0 = time.perf_counter()
        if args.mode == "compumarts":
            ext = CompumartsExtractor()
            structured, envelopes = ext.extract(specs, title)
            dur_ms = (time.perf_counter() - t0) * 1000
            print(f"[OK] CompuMarts Dedicated Extraction completed in {dur_ms:.2f}ms")
            print(f"     Envelopes generated for GLiNER fallback: {len(envelopes)}")
        elif args.mode == "hybrid":
            ext = HybridLaptopExtractor(model_name=args.model)
            structured, meta = ext.extract(title=title, specs=specs)
            print(f"[OK] Hybrid Extraction completed in {meta['total_time_ms']:.1f}ms")
            print(f"     - Layer 1 (Store Extractor): {meta['layer1_time_ms']:.3f}ms")
            print(f"     - Layer 2 (Scoped GLiNER):    {meta['gliner_time_ms']:.1f}ms ({meta['gliner_calls_count']} scoped calls)")
        else:
            raw_extractor = GLiNERExtractor(model_name=args.model)
            entities = raw_extractor.extract_from_spec_blocks(title=title, specs=specs, labels=DEFAULT_LABELS, threshold=args.threshold)
            dur_ms = (time.perf_counter() - t0) * 1000
            structured = LaptopSchemaMapper.map_entities(entities=entities, title=title, raw_specs=specs)
            print(f"[OK] Raw GLiNER Extraction completed in {dur_ms:.1f}ms")

        print("\n--- EXTRACTED DATABASE SCHEMA (catalog-service format) ---")
        display_dict = {k: v for k, v in structured.items() if k not in ("raw_entities",)}
        print(json.dumps(display_dict, indent=2, ensure_ascii=False))
        return

    # Locate source file
    source_path = args.source
    if not os.path.isabs(source_path):
        source_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), source_path)

    if not os.path.exists(source_path):
        # Fallback to local_extractor if default not present
        alt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "local_extractor/compumarts_scraper_results.json")
        if os.path.exists(alt_path):
            source_path = alt_path
        elif os.path.exists(args.source):
            source_path = os.path.abspath(args.source)
        else:
            print(f"[ERROR] Source file not found: {source_path}")
            sys.exit(1)

    print("=" * 80)
    print(f"[*] Loading data from: {source_path}")
    with open(source_path, "r", encoding="utf-8") as f:
        laptops = json.load(f)

    print(f"[*] Total laptops loaded: {len(laptops)}")
    print(f"[*] Mode: {args.mode.upper()}")
    if args.mode != "compumarts":
        print(f"[*] GLiNER model: {args.model}")
    print("=" * 80)

    # Initialize extractor based on mode
    if args.mode == "compumarts":
        compumarts_ext = CompumartsExtractor()
    elif args.mode == "hybrid":
        hybrid_extractor = HybridLaptopExtractor(model_name=args.model)
    else:
        raw_extractor = GLiNERExtractor(model_name=args.model)

    # Single laptop mode
    if args.index is not None:
        if args.index < 0 or args.index >= len(laptops):
            print(f"[ERROR] Index {args.index} out of range (0 to {len(laptops)-1})")
            sys.exit(1)

        target = laptops[args.index]
        title = target.get("title", "")
        specs = target.get("specs") or target.get("raw_specs") or {}

        print(f"\n[*] Testing Laptop #{args.index}: {title}")
        print(f"    Raw spec table fields: {len(specs)}")
        print("-" * 80)

        if args.mode == "compumarts":
            t0 = time.perf_counter()
            structured, envelopes = compumarts_ext.extract(raw_specs=specs, title=title, metadata=target)
            dur_ms = (time.perf_counter() - t0) * 1000
            print(f"[OK] Dedicated CompuMarts Extraction completed in {dur_ms:.3f}ms")
            print(f"     Envelopes generated for GLiNER fallback: {len(envelopes)}")
            if envelopes:
                for env in envelopes:
                    print(f"       - Target Area: {env.target_area} (reason: {env.reason})")
            print("\n--- EXTRACTED DATABASE SCHEMA (catalog-service format) ---")
            print(json.dumps(structured, indent=2, ensure_ascii=False))
        elif args.mode == "hybrid":
            structured, meta = hybrid_extractor.extract(title=title, specs=specs, metadata=target)
            print(f"[OK] Hybrid Extraction completed in {meta['total_time_ms']:.1f}ms")
            print(f"     - Layer 1 (Direct Key Match): {meta['layer1_time_ms']:.3f}ms")
            print(f"     - Layer 2 (Scoped GLiNER):    {meta['gliner_time_ms']:.1f}ms ({meta['gliner_calls_count']} scoped calls)")
            print("\n--- EXTRACTED DATABASE SCHEMA (catalog-service format) ---")
            print(json.dumps(structured, indent=2, ensure_ascii=False))
        else:
            t0 = time.perf_counter()
            entities = raw_extractor.extract_from_spec_blocks(
                title=title,
                specs=specs,
                labels=DEFAULT_LABELS,
                threshold=args.threshold,
            )
            dur_ms = (time.perf_counter() - t0) * 1000
            structured = LaptopSchemaMapper.map_entities(entities=entities, title=title, raw_specs=specs)
            print(f"[OK] Raw GLiNER Extraction completed in {dur_ms:.1f}ms")
            print(f"     Total entities extracted: {len(entities)}")
            print("\n--- EXTRACTED DATABASE SCHEMA (catalog-service format) ---")
            display_dict = {k: v for k, v in structured.items() if k not in ("raw_entities",)}
            print(json.dumps(display_dict, indent=2, ensure_ascii=False))

        return

    # Benchmark / Batch mode
    limit = args.limit or len(laptops)
    test_slice = laptops[:limit]

    print(f"\n[*] Running batch extraction on {len(test_slice)} laptops ({args.mode})...")
    latencies: list[float] = []
    results: list[dict] = []

    for idx, laptop in enumerate(test_slice):
        title = laptop.get("title", "")
        specs = laptop.get("specs") or laptop.get("raw_specs") or {}

        t0 = time.perf_counter()
        if args.mode == "compumarts":
            structured, envs = compumarts_ext.extract(raw_specs=specs, title=title, metadata=laptop)
            dur_ms = (time.perf_counter() - t0) * 1000
        elif args.mode == "hybrid":
            structured, meta = hybrid_extractor.extract(title=title, specs=specs, metadata=laptop)
            dur_ms = meta["total_time_ms"]
        else:
            entities = raw_extractor.extract_from_spec_blocks(
                title=title,
                specs=specs,
                labels=DEFAULT_LABELS,
                threshold=args.threshold,
            )
            dur_ms = (time.perf_counter() - t0) * 1000
            structured = LaptopSchemaMapper.map_entities(entities=entities, title=title, raw_specs=specs)

        product_url = laptop.get("product_url") or laptop.get("url") or ""
        latencies.append(dur_ms)
        results.append({
            "index": idx,
            "title": title,
            "product_url": product_url,
            "latency_ms": round(dur_ms, 2),
            "structured": structured,
        })

        # Compact progress indicator
        cpu_name = structured["cpu"].get("full_name") or f"{structured['cpu'].get('line') or ''} {structured['cpu'].get('model') or ''}".strip() or "N/A"
        gpu_name = structured["gpu"].get("model") or "N/A"
        ram_cap = structured["memory"].get("capacity_gb")
        res_str = structured["display"].get("resolution") or "N/A"
        brand = structured["identity"].get("brand") or "N/A"
        print(f"  [{idx+1:02d}/{len(test_slice):02d}] {dur_ms:6.2f}ms | Brand: {brand[:8]:<8} | CPU: {cpu_name[:24]:<24} | GPU: {gpu_name[:18]:<18} | RAM: {ram_cap}GB | Disp: {res_str[:11]}")

    # Summary Statistics
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    total_time = sum(latencies) / 1000

    print("\n" + "=" * 80)
    print("🎯 BENCHMARK SUMMARY:")
    print(f"  - Mode:                    {args.mode.upper()}")
    print(f"  - Total laptops processed: {len(test_slice)}")
    print(f"  - Total time elapsed:      {total_time:.3f}s")
    print(f"  - Average latency/laptop:  {avg_latency:.3f} ms")
    print(f"  - Min / Max latency:       {min(latencies):.2f} ms / {max(latencies):.2f} ms")
    print("=" * 80)

    if args.output:
        out_path = args.output
        if not os.path.isabs(out_path):
            out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), out_path)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Results saved to: {out_path}")


if __name__ == "__main__":
    main()
