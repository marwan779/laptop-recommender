"""Audit generator: Compares live CompuMarts PDPs vs scraped raw specs vs GLiNER hybrid results."""

import json
import os
import sys
import httpx
from bs4 import BeautifulSoup

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from local_extractor.table_extractor import extract_raw_spec_table

from curl_cffi import requests as cffi_requests

RAW_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "local_extractor", "compumarts_scraper_results.json")
HYBRID_PATH = os.path.join(os.path.dirname(__file__), "hybrid_results.json")


def fetch_live_pdp_specs(url: str) -> dict[str, str]:
    try:
        res = cffi_requests.get(url, impersonate="chrome", timeout=15)
        if res.status_code != 200:
            return {"_error": f"HTTP {res.status_code}"}
        return extract_raw_spec_table(res.text)
    except Exception as e:
        return {"_error": str(e)}
    except Exception as e:
        return {"_error": str(e)}


def main():
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        raw_laptops = json.load(f)

    with open(HYBRID_PATH, "r", encoding="utf-8") as f:
        hybrid_laptops = json.load(f)

    audit_records = []

    for idx, (raw_item, hyb_item) in enumerate(zip(raw_laptops, hybrid_laptops)):
        url = raw_item.get("product_url")
        print(f"[*] Fetching live PDP for Laptop #{idx}: {url}...")
        live_specs = fetch_live_pdp_specs(url)

        audit_records.append({
            "index": idx,
            "title": raw_item.get("title"),
            "url": url,
            "live_specs_count": len(live_specs),
            "scraped_specs_count": len(raw_item.get("specs", {})),
            "raw_specs": raw_item.get("specs", {}),
            "structured": hyb_item.get("structured", {}),
            "live_sample": {k: v for k, v in list(live_specs.items())[:15]},
        })

    with open(os.path.join(os.path.dirname(__file__), "audit_data.json"), "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Audit data collected for {len(audit_records)} laptops.")


if __name__ == "__main__":
    main()
