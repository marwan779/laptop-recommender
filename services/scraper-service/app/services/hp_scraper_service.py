import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.laptop import (
    HpBrandCatalogResult,
    LaptopDetail,
    LaptopSummary,
    utcnow_str,
)
from app.scrapers.hp import HpBrandScraper, parse_date_param


class HpScraperService:
    """HP Brand Scraping Microservice.

    Provides independent Level 1 and Level 2 scraping modes for the official
    HP Middle East catalog, supporting incremental watermark stopping via `until_model`,
    deep Level 2 hardware specifications extraction, and recency sorting.
    """

    def __init__(self, engine: IScraperEngine | None = None):
        self.engine = engine or ScraplingEngine()
        self.scraper = HpBrandScraper(engine=self.engine)

    def scrape(
        self,
        mode: str = "level2",
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
        output_file: str | Path | None = None,
    ) -> HpBrandCatalogResult:
        """Execute HP brand scraping pipeline.

        Args:
            mode: "level1" (fast catalog summaries) or "level2" (deep hardware specs).
            until_model: Watermark pointer: stop scraping when reaching this laptop model,
                         name, or URL slug (or list of previous pointers).
            max_pages: Optional maximum catalog pages to scan as a safety ceiling (default: None - all pages).
            limit: Optional cap on laptops processed.
            output_file: Optional path to save the standalone JSON output.

        Returns:
            HpBrandCatalogResult containing all scraped laptop data and metadata.
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
        print(f"[HP Service] Starting HP Brand Scraping")
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
            limit=limit if (limit and not until_model) else None,
            until_model=until_model,
            max_pages=max_pages,
        )

        latest_pointers = [s.name for s in summaries[:3]]

        if mode_clean == "level1":
            catalog_result = HpBrandCatalogResult(
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
            print(f"\n[HP Service] [{idx}/{len(summaries)}] Deep Crawl: '{summary.name}'")
            try:
                detail = self.scraper.get_laptop_detail(summary)
                if detail:
                    detailed_laptops.append(detail)
                    print(
                        f"  -> Extracted {len(detail.all_specs)} specs, "
                        f"{len(detail.structured_specs)} structured attributes, "
                        f"Release Date: {detail.release_date or 'N/A'}"
                    )
                else:
                    print(f"  -> Skipping (no specifications found for '{summary.name}')")
                    if not any(s.name == summary.name for s in self.scraper.skipped_laptops):
                        self.scraper.record_skipped(
                            name=summary.name,
                            url=summary.specs_url or summary.product_url,
                            reason="No specifications found for laptop",
                            stage="level2_specs",
                        )
            except Exception as e:
                print(f"  -> Error crawling details for '{summary.name}': {e}")
                self.scraper.record_skipped(
                    name=summary.name,
                    url=summary.specs_url or summary.product_url,
                    reason=f"Exception during detail crawl: {e}",
                    error=str(e),
                    stage="level2_specs",
                )

            if limit and len(detailed_laptops) >= limit:
                print(f"\n[HP Service] Reached requested limit of {limit} laptops.")
                break

        # ---------------------------------------------------------------------
        # Recency Sorting: Sort by release_date descending so newest appear first
        # ---------------------------------------------------------------------
        def _date_sort_key(item: LaptopDetail) -> str:
            return item.release_date or "0000-00-00"

        detailed_laptops.sort(key=_date_sort_key, reverse=True)

        # Calculate time span of scraped batch
        valid_dates = [
            parse_date_param(item.release_date)
            for item in detailed_laptops
            if parse_date_param(item.release_date) is not None
        ]
        start_date_str = min(valid_dates).date().isoformat() if valid_dates else None
        if detailed_laptops:
            latest_pointers = [d.name for d in detailed_laptops[:3]]

        total_configs = sum(len(d.configurations) for d in detailed_laptops)

        catalog_result = HpBrandCatalogResult(
            brand=self.scraper.brand_name,
            official_catalog_url=self.scraper.catalog_url,
            scrape_mode="level2",
            until_model=watermark_display if watermark_display != "None (Full Catalog)" else None,
            latest_pointers=latest_pointers,
            start_date=start_date_str,
            # end_date=end_date_str,
            total_laptops=len(detailed_laptops),
            total_configurations=total_configs,
            total_skipped=len(self.scraper.skipped_laptops),
            laptops=detailed_laptops,
            skipped_laptops=list(self.scraper.skipped_laptops),
        )

        self._save_if_requested(catalog_result, output_file)

        print("\n" + "=" * 80)
        print(f"[HP Service] Scraping Complete!")
        print(f"  - Total Laptops: {catalog_result.total_laptops}")
        print(f"  - Total Configurations: {catalog_result.total_configurations}")
        print(f"  - Date Range: {catalog_result.start_date} to {catalog_result.end_date}")
        if output_file:
            print(f"  - Saved to: {output_file}")
        print("=" * 80)

        return catalog_result

    def _save_if_requested(
        self,
        result: HpBrandCatalogResult,
        output_file: str | Path | None,
    ) -> None:
        if not output_file:
            return
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"[HP Service] Results written to {out_path.resolve()}")
