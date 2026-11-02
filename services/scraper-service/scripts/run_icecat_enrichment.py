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
from app.matching.combiner import CatalogCombiner, merge_specifications
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
    """Attach `source_table`, `raw_description`, `store_specs`, and `store_slot_count` from store JSONs to each CanonicalLaptop."""
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
                    store_sc = ((prod.get("specs") or {}).get("storage") or {}).get("slot_count")
                    url_to_context[url] = {
                        "source_table": prod.get("source_table") or {},
                        "raw_description": prod.get("raw_description") or "",
                        "store_specs": prod.get("specs") or {},
                        "store_slot_count": store_sc if isinstance(store_sc, int) else None,
                    }
        except Exception as e:
            logger.warning("Could not read store file %s: %s", sf.name, e)

    hydrated = 0
    for lap in catalog.laptops:
        store_slot_counts: list[int] = []
        fused_store_specs: dict[str, Any] = {}
        for offer in lap.offers:
            u = (offer.product_url or "").strip()
            ctx = url_to_context.get(u)
            if ctx:
                if isinstance(ctx.get("store_slot_count"), int):
                    store_slot_counts.append(ctx["store_slot_count"])
                if ctx.get("store_specs"):
                    fused_store_specs = merge_specifications(fused_store_specs, ctx["store_specs"])

        max_store_sc = max(store_slot_counts) if store_slot_counts else None
        if max_store_sc is not None:
            stor = lap.specs.setdefault("storage", {})
            if (stor.get("slot_count") or 0) < max_store_sc:
                stor["slot_count"] = max_store_sc

        if lap.raw_store_context and lap.raw_store_context.get("source_table"):
            if max_store_sc is not None:
                lap.raw_store_context["store_slot_count"] = max_store_sc
            if fused_store_specs:
                lap.raw_store_context["store_specs"] = fused_store_specs
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

        if merged_table or descriptions or max_store_sc is not None or fused_store_specs:
            lap.raw_store_context = {
                "source_table": merged_table,
                "raw_description": "\n\n".join(descriptions),
                "primary_url": primary_url,
                "store_slot_count": max_store_sc,
                "store_specs": fused_store_specs,
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
    catalog: UnifiedCatalog | None = None
    if args.catalog.is_file():
        logger.info("Loading unified catalog from: %s", args.catalog)
        with open(args.catalog, encoding="utf-8") as f:
            raw_catalog = json.load(f)
        catalog = UnifiedCatalog.model_validate(raw_catalog)

    if catalog is None or len(catalog.laptops) == 0:
        backup_path = SERVICE_ROOT.parent / "catalog-service" / "scraping input" / "unified_catalog_latest.json"
        if backup_path.is_file():
            logger.info("Restoring unified catalog from backup: %s", backup_path)
            with open(backup_path, encoding="utf-8") as f:
                catalog = UnifiedCatalog.model_validate(json.load(f))
            catalog.save_json(args.catalog)
        else:
            logger.info(
                "Unified catalog is empty or missing; recombining from store files (%s)...",
                [sf.name for sf in STORE_FILES if sf.is_file()],
            )
            combiner = CatalogCombiner()
            catalog = combiner.combine_files([sf for sf in STORE_FILES if sf.is_file()])
            catalog.save_json(args.catalog)
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
