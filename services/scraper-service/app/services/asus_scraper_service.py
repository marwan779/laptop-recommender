import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.laptop import (
    AsusBrandCatalogResult,
    LaptopDetail,
    LaptopSummary,
    utcnow_str,
)
from app.scrapers.asus import AsusBrandScraper, parse_date_param


class AsusScraperService:
    """ASUS Brand Scraping Microservice.

    Provides independent Level 1 and Level 2 scraping modes for the official
    ASUS Egypt catalog, supporting nullable start_date and end_date parameters
    for incremental cron updates and initial database population.
    """

    def __init__(self, engine: IScraperEngine | None = None):
        self.engine = engine or ScraplingEngine()
        self.scraper = AsusBrandScraper(engine=self.engine)

    def scrape(
        self,
        mode: str = "level2",
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
        output_file: str | Path | None = None,
    ) -> AsusBrandCatalogResult:
        """Execute ASUS brand scraping pipeline.

        Args:
            mode: "level1" (fast catalog summaries) or "level2" (deep hardware specs).
            until_model: Watermark pointer: stop scraping when reaching this laptop model,
                         name, or URL slug (or list of previous pointers).
            max_pages: Optional maximum catalog pages to scan as a safety ceiling (default: None - all pages).
            limit: Optional cap on laptops processed.
            output_file: Optional path to save the standalone JSON output.

        Returns:
            AsusBrandCatalogResult containing all scraped laptop data and metadata.
        """
        mode_clean = mode.lower().strip()
        if mode_clean not in ("level1", "level2"):
            raise ValueError(f"Invalid mode '{mode}'. Choose 'level1' or 'level2'.")

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )

        print("\n" + "=" * 80)
        print(f"[ASUS Service] Starting ASUS Brand Scraping")
        print(f"  - Mode: {mode_clean.upper()}")
        print(f"  - Until Model (Watermark): {watermark_display}")
        print(f"  - Max Pages: {max_pages}")
        print(f"  - Laptop Limit: {limit or 'Unlimited'}")
        print(f"  - Output Target: {output_file or 'In-Memory only'}")
        print("=" * 80)

        # ---------------------------------------------------------------------
        # Level 1: Discover Canonical Catalog Summaries (with Watermark Stopping)
        # ---------------------------------------------------------------------
        summaries = self.scraper.get_laptop_summaries(
            limit=None if mode_clean == "level2" else limit,
            until_model=until_model,
            max_pages=max_pages,
        )
        latest_pointers = [s.name for s in summaries[:3]]

        if mode_clean == "level1":
            catalog_result = AsusBrandCatalogResult(
                brand=self.scraper.brand_name,
                official_catalog_url=self.scraper.catalog_url,
                scrape_mode="level1",
                until_model=watermark_display if watermark_display != "None (Full Catalog)" else None,
                latest_pointers=latest_pointers,
                total_laptops=len(summaries),
                total_configurations=len(summaries),
                laptops=summaries,
            )
            self._save_if_requested(catalog_result, output_file)
            return catalog_result

        # ---------------------------------------------------------------------
        # Level 2: Deep Specifications, Full SKUs, Configurations & Hardware
        # ---------------------------------------------------------------------
        detailed_laptops: list[LaptopDetail] = []

        for idx, summary in enumerate(summaries, 1):
            print(f"\n[ASUS Service] [{idx}/{len(summaries)}] Deep Crawl: '{summary.name}'")
            detail = self.scraper.get_laptop_detail(summary=summary)
            if detail is None:
                continue

            detailed_laptops.append(detail)
            if limit and len(detailed_laptops) >= limit:
                print(f"[ASUS Service] Reached requested limit of {limit} laptop(s).")
                break

        total_configs = sum(len(d.configurations) for d in detailed_laptops)
        if detailed_laptops:
            latest_pointers = [d.name for d in detailed_laptops[:3]]

        catalog_result = AsusBrandCatalogResult(
            brand=self.scraper.brand_name,
            official_catalog_url=self.scraper.catalog_url,
            scrape_mode="level2",
            until_model=watermark_display if watermark_display != "None (Full Catalog)" else None,
            latest_pointers=latest_pointers,
            total_laptops=len(detailed_laptops),
            total_configurations=total_configs,
            laptops=detailed_laptops,
        )

        self._save_if_requested(catalog_result, output_file)
        return catalog_result

    def _save_if_requested(self, catalog: AsusBrandCatalogResult, output_file: str | Path | None) -> None:
        """Write JSON output file if destination path is specified."""
        if not output_file:
            return
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(catalog.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"\n[ASUS Service] [+] Successfully saved {catalog.total_laptops} laptop(s) to '{path}'")
