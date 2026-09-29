import json
from pathlib import Path
from typing import Any

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.laptop import (
    BrandCatalogResult,
    GigabyteBrandCatalogResult,
    LaptopDetail,
    LaptopSummary,
    utcnow_str,
)
from app.scrapers.gigabyte import GigabyteBrandScraper


class GigabyteScraperService:
    """GigaByte Brand Scraping Microservice.

    Provides independent Level 1 and Level 2 scraping modes for the official
    GigaByte laptop catalog, supporting watermark stopping via `until_model`
    and deep Level 2 hardware specifications extraction.
    """

    def __init__(self, engine: IScraperEngine | None = None):
        self.engine = engine or ScraplingEngine()
        self.scraper = GigabyteBrandScraper(engine=self.engine)

    def scrape(
        self,
        mode: str = "level2",
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
        output_file: str | Path | None = None,
    ) -> BrandCatalogResult:
        """Execute GigaByte brand scraping pipeline.

        Args:
            mode: "level1" (fast catalog summaries) or "level2" (deep hardware specs).
            until_model: Watermark pointer: stop scraping when reaching this laptop model,
                         name, or URL slug (or list of previous pointers).
            max_pages: Optional maximum catalog pages to scan as a safety ceiling (default: None - all pages).
            limit: Optional cap on laptops processed.
            output_file: Optional path to save the standalone JSON output.

        Returns:
            BrandCatalogResult containing all scraped laptop data and metadata.
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
        print(f"[GigaByte Service] Starting GigaByte Brand Scraping")
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
            catalog_result = BrandCatalogResult(
                brand=self.scraper.brand_name,
                official_catalog_url=self.scraper.catalog_url,
                scrape_mode="level1",
                until_model=watermark_display if watermark_display != "None (Full Catalog)" else None,
                latest_pointers=latest_pointers,
                total_laptops=len(summaries),
                total_configurations=len(summaries),
                total_skipped=len(self.scraper.skipped_laptops),
                laptops=summaries,
                skipped_laptops=list(self.scraper.skipped_laptops),
            )
            self._save_if_requested(catalog_result, output_file)
            return catalog_result

        # ---------------------------------------------------------------------
        # Level 2: Deep Specifications, Full SKUs, Configurations & Hardware
        # ---------------------------------------------------------------------
        detailed_laptops: list[LaptopDetail] = []

        for idx, summary in enumerate(summaries, 1):
            print(f"\n[GigaByte Service] [{idx}/{len(summaries)}] Deep Crawl: '{summary.name}'")
            try:
                detail = self.scraper.get_laptop_detail(summary=summary)
                if detail is None:
                    continue
                detailed_laptops.append(detail)
            except Exception as e:
                print(f"[GigaByte Service] Error crawling details for '{summary.name}': {e}")
                self.scraper.record_skipped(
                    name=summary.name,
                    url=summary.specs_url or summary.product_url,
                    reason=f"Exception during detail crawl: {e}",
                    error=str(e),
                    stage="level2_specs",
                )
                continue

            if limit and len(detailed_laptops) >= limit:
                print(f"[GigaByte Service] Reached requested limit of {limit} laptop(s).")
                break

        total_configs = sum(len(d.configurations) for d in detailed_laptops)
        if detailed_laptops:
            latest_pointers = [d.name for d in detailed_laptops[:3]]

        catalog_result = BrandCatalogResult(
            brand=self.scraper.brand_name,
            official_catalog_url=self.scraper.catalog_url,
            scrape_mode="level2",
            until_model=watermark_display if watermark_display != "None (Full Catalog)" else None,
            latest_pointers=latest_pointers,
            total_laptops=len(detailed_laptops),
            total_configurations=total_configs,
            total_skipped=len(self.scraper.skipped_laptops),
            laptops=detailed_laptops,
            skipped_laptops=list(self.scraper.skipped_laptops),
        )

        self._save_if_requested(catalog_result, output_file)
        return catalog_result

    def _save_if_requested(self, catalog: BrandCatalogResult, output_file: str | Path | None) -> None:
        """Write JSON output file if destination path is specified."""
        if not output_file:
            return
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(catalog.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"\n[GigaByte Service] [+] Successfully saved {catalog.total_laptops} laptop(s) to '{path}'")
