"""Search online using DuckDuckGo Lite for missing (null) hardware specifications
of a specific laptop (default: laptop_asus_tuf_gaming_90nr0mc1m003t0).

Formulates specific, targeted queries for the model and its missing fields,
and displays the raw search results (titles, URLs, snippets) returned by DuckDuckGo Lite.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# Set stdout encoding for Windows console to handle UTF-8/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIFIED_PATH = SERVICE_ROOT / "scraping results" / "unified_catalog_latest.json"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"


def extract_null_fields(specs: dict[str, Any]) -> dict[str, list[str]]:
    """Identify all null fields across all categories in the laptop specs."""
    nulls: dict[str, list[str]] = {}
    for cat_name, cat_val in specs.items():
        if isinstance(cat_val, dict):
            cat_nulls = [k for k, v in cat_val.items() if v is None and not k.startswith("_")]
            if cat_nulls:
                nulls[cat_name] = cat_nulls
    return nulls


def build_targeted_queries(laptop: dict[str, Any], null_fields: dict[str, list[str]]) -> list[tuple[str, str]]:
    """
    Construct precision-engineered DuckDuckGo Lite queries.
    Returns list of (query_label, query_string).
    """
    title = laptop.get("title") or ""
    mpn = (laptop.get("mpn") or "").strip()

    # Extract clean model tokens (e.g. FA608PM, FA608)
    m_code = re.search(r"\b(FA\d{3}[A-Z]{2}(?:-[A-Z0-9]+)?)\b", title, re.I)
    model_code = m_code.group(1) if m_code else "FA608PM"
    base_chassis = model_code.split("-")[0]  # e.g. FA608PM

    # Format MPN with hyphen if applicable (e.g. 90NR0MC1-M003T0)
    formatted_mpn = ""
    if len(mpn) == 14 and "-" not in mpn:
        formatted_mpn = f"{mpn[:8]}-{mpn[8:]}"

    queries = []

    # 1. Official ASUS page for exact model
    queries.append((
        "Official ASUS Global / Regional Store",
        f'site:asus.com {base_chassis}'
    ))

    # 2. Comprehensive chassis-level specifications (FA608 family)
    queries.append((
        "ASUS TUF A16 FA608 Chassis Specifications",
        f'ASUS TUF Gaming A16 {base_chassis} specifications'
    ))

    # 3. Chassis Material & Ports (nulls: chassis_material, card_reader_type, thunderbolt)
    queries.append((
        "Chassis Material, Ports & Card Reader",
        f'ASUS TUF A16 {base_chassis} material ports card reader'
    ))

    # 4. Webcam Privacy Shutter (null: has_privacy_shutter)
    queries.append((
        "Webcam & Privacy Shutter Evidence",
        f'ASUS TUF {base_chassis} webcam privacy shutter'
    ))

    # 5. GPU Boost Clock & TGP (null: boost_clock_mhz)
    queries.append((
        "GPU Boost Clock & TGP",
        f'ASUS TUF {base_chassis} RTX 5060 boost clock TGP'
    ))

    return queries


def search_ddg_lite(query: str, session: Any = None, timeout: int = 15) -> list[dict[str, str]]:
    """Execute a POST request to DuckDuckGo Lite and parse raw result entries."""
    from bs4 import BeautifulSoup
    from curl_cffi import requests

    sess = session or requests.Session(impersonate="chrome120")
    if not getattr(sess, "_ddg_init", False):
        sess.get(DDG_LITE_URL, timeout=timeout)
        sess._ddg_init = True

    resp = sess.post(
        DDG_LITE_URL,
        data={"q": query},
        timeout=timeout,
    )

    if resp.status_code != 200:
        print(f"[!] DuckDuckGo Lite returned HTTP status: {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    links = soup.select("a.result-link")
    snippets = soup.select(".result-snippet")

    for idx, link_el in enumerate(links):
        raw_href = (link_el.get("href") or "").strip()
        # Clean DuckDuckGo redirect wrapper if present
        if "uddg=" in raw_href:
            m = re.search(r"uddg=([^&]+)", raw_href)
            if m:
                raw_href = unquote(m.group(1))

        title = link_el.get_text(strip=True)
        snippet = ""
        if idx < len(snippets):
            snippet = snippets[idx].get_text(strip=True)
            snippet = re.sub(r"\s+", " ", snippet).strip()

        results.append({
            "title": title,
            "url": raw_href,
            "snippet": snippet,
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search DuckDuckGo Lite for laptop null fields.")
    parser.add_argument(
        "--canonical-id",
        type=str,
        default="laptop_asus_tuf_gaming_90nr0mc1m003t0",
        help="Target canonical_id in unified_catalog_latest.json",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum raw search results to display per query",
    )
    args = parser.parse_args()

    # Load laptop from catalog
    if not DEFAULT_UNIFIED_PATH.is_file():
        print(f"Error: Catalog file not found at {DEFAULT_UNIFIED_PATH}")
        sys.exit(1)

    with open(DEFAULT_UNIFIED_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    target_lap = next((l for l in catalog.get("laptops", []) if l.get("canonical_id") == args.canonical_id), None)
    if not target_lap:
        print(f"Error: Laptop with canonical_id '{args.canonical_id}' not found in catalog.")
        sys.exit(1)

    print("=" * 80)
    print(f"TARGET LAPTOP: {target_lap.get('title')}")
    print(f"CANONICAL ID : {target_lap.get('canonical_id')}")
    print(f"MPN          : {target_lap.get('mpn')}")
    print("=" * 80)

    # 1. Inspect Null Fields
    null_fields = extract_null_fields(target_lap.get("specs", {}))
    print("\nCURRENT NULL SPECIFICATION FIELDS IN CATALOG:")
    for cat, fields in null_fields.items():
        print(f"  • {cat:16}: {', '.join(fields)}")
    print("-" * 80)

    # 2. Build Specific Targeted Queries
    queries = build_targeted_queries(target_lap, null_fields)
    print(f"\nCONSTRUCTED {len(queries)} TARGETED QUERIES FOR DUCKDUCKGO LITE:")
    for idx, (label, q) in enumerate(queries, 1):
        print(f"  [{idx}] {label}:\n      POST -> https://lite.duckduckgo.com/lite/\n      Body -> q={q}")
    print("=" * 80)

    # 3. Execute Searches & Output Raw Results
    from curl_cffi import requests
    session = requests.Session(impersonate="chrome120")

    for idx, (label, q) in enumerate(queries, 1):
        if idx > 1:
            time.sleep(1.5)  # Polite delay to prevent DDG Lite rate limits
        print(f"\n>>> EXECUTING QUERY [{idx}/{len(queries)}]: {label}")
        print(f"    Raw Query: {q}\n")

        results = search_ddg_lite(q, session=session)
        if not results:
            print("    [!] No results returned.")
            continue

        print(f"    Found {len(results)} raw results from DuckDuckGo Lite (showing top {min(args.max_results, len(results))}):")
        for r_idx, r in enumerate(results[:args.max_results], 1):
            print(f"\n    [{r_idx}] TITLE   : {r['title']}")
            print(f"        URL     : {r['url']}")
            print(f"        SNIPPET : {r['snippet']}")

    print("\n" + "=" * 80)
    print("SEARCH EXECUTION COMPLETE.")
    print("=" * 80)


if __name__ == "__main__":
    main()
