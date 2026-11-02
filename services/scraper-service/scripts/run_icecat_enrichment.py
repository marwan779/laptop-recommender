"""Run Stage 3 (Icecat OpenIcecat JSON Enrichment) and Stage 4 (Targeted LLM Fallback)
directly on `unified_catalog_latest.json` using the already-matched IDs from
`icecat_match_report.json` and raw store tables from `compumarts.json`, `elbadr.json`,
and `sigma.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.common.logger import get_logger
from app.matching.models import UnifiedCatalog
from app.pipeline.icecat.enricher import IcecatCatalogEnricher

logger = get_logger("scripts.icecat_enrichment")

RESULTS_DIR = SERVICE_ROOT / "scraping results"
DEFAULT_UNIFIED_PATH = RESULTS_DIR / "unified_catalog_latest.json"
DEFAULT_MATCH_REPORT = RESULTS_DIR / "icecat_match_report.json"
DEFAULT_CACHE_PATH = RESULTS_DIR / "icecat_specs_cache.json"
STORE_FILES = [
    RESULTS_DIR / "compumarts.json",
    RESULTS_DIR / "elbadr.json",
    RESULTS_DIR / "sigma.json",
]


def hydrate_raw_store_context(catalog: UnifiedCatalog, store_files: list[Path]) -> int:
    """Attach `source_table` and `raw_description` from store JSONs to each CanonicalLaptop by URL."""
    url_to_context: dict[str, dict[str, Any]] = {}
    for sf in store_files:
        if not sf.is_file():
            continue
        try:
            with open(sf, encoding="utf-8") as f:
                data = json.load(f)
            for prod in data.get("structured_products", []) or []:
                url = (prod.get("url") or "").strip()
                if url:
                    url_to_context[url] = {
                        "source_table": prod.get("source_table") or {},
                        "raw_description": prod.get("raw_description") or "",
                    }
        except Exception as e:
            logger.warning("Could not read store file %s: %s", sf.name, e)

    hydrated = 0
    for lap in catalog.laptops:
        if lap.raw_store_context and lap.raw_store_context.get("source_table"):
            hydrated += 1
            continue

        merged_table: dict[str, Any] = {}
        descriptions: list[str] = []
        primary_url = ""

        for offer in lap.offers:
            u = (offer.product_url or "").strip()
            if not primary_url and u:
                primary_url = u
            ctx = url_to_context.get(u)
            if ctx:
                for k, v in (ctx.get("source_table") or {}).items():
                    if k not in merged_table and v:
                        merged_table[k] = v
                desc = (ctx.get("raw_description") or "").strip()
                if desc and desc not in descriptions:
                    descriptions.append(desc)

        if merged_table or descriptions:
            lap.raw_store_context = {
                "source_table": merged_table,
                "raw_description": "\n\n".join(descriptions),
                "primary_url": primary_url,
            }
            hydrated += 1

    return hydrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich unified_catalog_latest.json with OpenIcecat Live JSON specs and targeted LLM fallback."
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_UNIFIED_PATH,
        help="Path to unified_catalog_latest.json",
    )
    parser.add_argument(
        "--match-report",
        type=Path,
        default=DEFAULT_MATCH_REPORT,
        help="Path to icecat_match_report.json",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Path to icecat_specs_cache.json",
    )
    parser.add_argument(
        "--live-search",
        action="store_true",
        default=False,
        help="Allow live Icecat search for laptops not in icecat_match_report.json (default: False)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        default=False,
        help="Skip Stage 4 Cloud LLM step for VARIANT_MATCH and NOT_FOUND laptops",
    )
    args = parser.parse_args()

    t0 = time.perf_counter()
    if not args.catalog.is_file():
        raise FileNotFoundError(f"Unified catalog not found: {args.catalog}")

    logger.info("Loading unified catalog from: %s", args.catalog)
    with open(args.catalog, encoding="utf-8") as f:
        raw_catalog = json.load(f)

    catalog = UnifiedCatalog.model_validate(raw_catalog)
    hydrated_count = hydrate_raw_store_context(catalog, STORE_FILES)
    logger.info(
        "Loaded %d canonical laptops (%d hydrated with raw store tables for Stage 4 LLM).",
        len(catalog.laptops),
        hydrated_count,
    )

    enricher = IcecatCatalogEnricher(
        cache_path=args.cache,
        match_report_path=args.match_report,
        run_llm_fallback=not args.no_llm,
    )

    enriched_catalog = enricher.enrich_catalog(
        catalog=catalog,
        allow_live_search=args.live_search,
    )

    enriched_catalog.save_json(args.catalog)
    elapsed = round(time.perf_counter() - t0, 2)

    exact_cnt = sum(1 for l in enriched_catalog.laptops if l.verification_status == "VERIFIED_ICECAT")
    var_cnt = sum(1 for l in enriched_catalog.laptops if l.verification_status == "VERIFIED_ICECAT_VARIANT")
    llm_cnt = sum(1 for l in enriched_catalog.laptops if l.verification_status == "LLM_EXTRACTED")
    nf_cnt = sum(1 for l in enriched_catalog.laptops if l.verification_status == "NOT_FOUND")

    summary = {
        "total_laptops": len(enriched_catalog.laptops),
        "verified_icecat_exact": exact_cnt,
        "verified_icecat_variant": var_cnt,
        "llm_extracted": llm_cnt,
        "not_found_unverified": nf_cnt,
        "total_ready_for_metrics": exact_cnt + var_cnt + llm_cnt,
        "elapsed_seconds": elapsed,
        "output_file": str(args.catalog),
    }

    print("\n" + "=" * 80)
    print("Icecat & Targeted LLM Enrichment Summary:")
    print(json.dumps(summary, indent=2))
    print("=" * 80)


if __name__ == "__main__":
    main()
