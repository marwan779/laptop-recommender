# Engineering Task: Implement Official Brand Scrapers for Acer, DELL, and GigaByte

## 📋 Task Overview

* **Task Title**: Build Brand Scrapers for DELL, Acer, and GigaByte (Egypt Official Portals)
* **Assigned To**: Full-Stack / Scraping Engineer
* **Target Services**: `services/scraper-service/app/scrapers/`, `services/scraper-service/app/services/`
* **Reference Implementations**:
  * [`app/scrapers/asus.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/scrapers/asus.py)
  * [`app/services/asus_scraper_service.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/services/asus_scraper_service.py)
  * [`app/services/orchestrator.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/services/orchestrator.py)

---

## 🎯 Objective

You must implement official brand catalog scrapers and services for **DELL**, **Acer**, and **GigaByte** for the Egypt region. 

You **MUST follow the exact same architectural pattern, data structures, and lifecycle** established in the ASUS reference implementation:
1. **Inherit from `BaseBrandScraper`** ([`app/scrapers/base.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/scrapers/base.py)).
2. Support **Level 1** (listing card summaries sorted by Newest) and **Level 2** (deep hardware specs crawled from official spec sheets).
3. Support the **Watermark Cursor (`until_model`)** and **Pagination Cap (`max_pages: int | None = None`)** pattern for fast incremental cron runs or unconstrained initial population.
4. Convert HTML spec sheets to Markdown via `doc.markdown()` for robust section and table parsing.
5. Create a dedicated standalone service orchestrator (`<Brand>ScraperService`) that outputs the unified `BrandCatalogResult` and records `latest_pointers` (top 3 newest laptops) for subsequent watermark runs.
6. Register the new brand services in `BRAND_SERVICE_REGISTRY` in [`app/services/orchestrator.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/services/orchestrator.py).

---

## 📂 Files You Need to Create and Edit

### 1. New Scraper Files to Create:
* `services/scraper-service/app/scrapers/dell.py`
* `services/scraper-service/app/scrapers/acer.py`
* `services/scraper-service/app/scrapers/gigabyte.py`

### 2. New Service Files to Create:
* `services/scraper-service/app/services/dell_scraper_service.py`
* `services/scraper-service/app/services/acer_scraper_service.py`
* `services/scraper-service/app/services/gigabyte_scraper_service.py`

### 3. Existing Files to Update:
* `services/scraper-service/app/schemas/laptop.py`: Alias `DellBrandCatalogResult`, `AcerBrandCatalogResult`, and `GigabyteBrandCatalogResult` to the unified `BrandCatalogResult`.
* `services/scraper-service/app/core/constants.py`: Verify and adjust `BRAND_CATALOGS` URLs.
* `services/scraper-service/app/services/orchestrator.py`: Register in `BRAND_SERVICE_REGISTRY`.
* `services/scraper-service/app/services/__init__.py`: Export the new brand services.

---

## 🌐 Official Egypt Brand Portals

| Brand | Official Egypt Catalog URL | Notable Laptop Families | Example Model Codes |
| :--- | :--- | :--- | :--- |
| **DELL** | `https://www.dell.com/en-eg/shop/dell-laptops/sc/laptops` | XPS, Inspiron, Alienware, G Series, Latitude, Precision | `9340` (XPS 13), `3520` (Inspiron 15), `5530` (G15), `m18 R2` |
| **Acer** | `https://www.acer.com/eg-en/laptops` | Predator, Nitro, Swift, Aspire, TravelMate, Spin | `PH16-72` (Helios), `ANV15-51` (Nitro V), `SFG14-73` (Swift Go), `A515-58` |
| **GigaByte** | `https://www.gigabyte.com/eg/Laptop` | AORUS, AERO, G5, G6, G7 | `AORUS 16X`, `AERO 14 OLED`, `G5 KF`, `G6X (2024)` |

---

## 📐 Implementation Pattern (Step-by-Step)

### Step 1: Implement the Scraper Class (`BaseBrandScraper`)

Create `app/scrapers/<brand>.py` inheriting from `BaseBrandScraper`:

```python
import itertools
import json
import re
from urllib.parse import urljoin, urlparse
from app.engine.base import IScraperEngine
from app.schemas.laptop import ConfigurationItem, LaptopDetail, LaptopSummary
from app.scrapers.base import BaseBrandScraper

class DellBrandScraper(BaseBrandScraper):
    @property
    def brand_name(self) -> str:
        return "Dell"

    @property
    def catalog_url(self) -> str:
        return "https://www.dell.com/en-eg/shop/dell-laptops/sc/laptops"

    def _determine_family(self, text: str, url: str) -> str | None:
        combined = f"{text} {url}".lower()
        if "xps" in combined:
            return "XPS"
        elif "alienware" in combined:
            return "Alienware"
        elif "g-series" in combined or "g15" in combined or "g16" in combined:
            return "G Series"
        elif "inspiron" in combined:
            return "Inspiron"
        elif "latitude" in combined:
            return "Latitude"
        elif "precision" in combined:
            return "Precision"
        return "Dell Laptop"

    def _extract_model_code(self, name: str, url: str) -> str | None:
        # Extract model chassis code (e.g. '9340', '3520', '5530')
        match = re.search(r"\b([A-Za-z]?\d{4}[A-Za-z]?)\b", name)
        return match.group(1).upper() if match else None
```

#### Level 1: `get_laptop_summaries()` Requirements
1. **Unconstrained & Safe Pagination (`max_pages: int | None = None`)**:
   * Loop through pages using `itertools.count(1)`:
     ```python
     for page_idx in itertools.count(1):
         if max_pages is not None and page_idx > max_pages:
             break
         if reached_watermark:
             break
         if limit and len(summaries) >= limit:
             break
     ```
   * *Critical note for Single-Page Applications (SPAs)*: If the site renders client-side via JavaScript (like ASUS Vue.js) and ignores `?page={N}` query strings, discover and call the backend catalog API directly (e.g., ASUS Odin API, Lenovo DLP API).
   * Terminate naturally when a page returns 0 new products.

2. **Watermark Pointer Matching (`matches_pointer`)**:
   * Accepts `until_model: str | list[str] | None = None`.
   * Matches against:
     * Model Code (e.g. `9340` or `PH16-72`)
     * Full Name (e.g. `Dell XPS 13 (9340)`)
     * Product URL Slug (e.g. `xps-13-9340-laptop`)
   * **Halts immediately** on the first matching card:
     ```python
     if pointers and matches_pointer(name, model, full_url):
         print(f"  [+] Reached Watermark pointer matching '{name}'! Halting Level 1 scan.")
         reached_watermark = True
         break
     ```

#### Level 2: `get_laptop_detail()` Requirements
1. **Crawl Tech Specs Page**:
   * Visit `summary.specs_url` or `summary.product_url`.
   * Convert page to Markdown using `doc.markdown()`.
2. **Placeholder Filter**:
   * Check for empty catalog indicators (e.g., missing hardware specifications or zero configuration text). Return `None` if placeholder.
3. **Parse Markdown Sections**:
   * Extract key-value pairs between known headers (`Processor`, `Operating System`, `Graphics`, `Display`, `Memory`, `Storage`, `I/O Ports`, `Battery`, `Weight`, `Dimensions`, `Color`).
4. **Structured Specs Normalization**:
   * Map raw headers to standard keys: `processor`, `graphics`, `display`, `memory`, `storage`, `io_ports`, `battery`, `weight`, `color`.
5. **Extract SKU Variants & Configurations**:
   * Search for exact MPNs / part numbers using regex.
   * Return a fully populated `LaptopDetail` object with `configurations: list[ConfigurationItem]`.

---

### Step 2: Implement the Brand Service Orchestrator

Create `app/services/<brand>_scraper_service.py` returning the unified `BrandCatalogResult`:

```python
import json
from pathlib import Path
from typing import Any
from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.schemas.laptop import BrandCatalogResult, LaptopDetail, LaptopSummary
from app.scrapers.dell import DellBrandScraper

class DellScraperService:
    def __init__(self, engine: IScraperEngine | None = None):
        self.engine = engine or ScraplingEngine()
        self.scraper = DellBrandScraper(engine=self.engine)

    def scrape(
        self,
        mode: str = "level2",
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
        output_file: str | Path | None = None,
    ) -> BrandCatalogResult:
        # 1. Level 1: Fetch listing cards with watermark stopping
        summaries = self.scraper.get_laptop_summaries(
            limit=None if mode == "level2" else limit,
            until_model=until_model,
            max_pages=max_pages,
        )
        latest_pointers = [s.name for s in summaries[:3]]

        if mode == "level1":
            catalog_result = BrandCatalogResult(
                brand=self.scraper.brand_name,
                official_catalog_url=self.scraper.catalog_url,
                scrape_mode="level1",
                until_model=until_model,
                latest_pointers=latest_pointers,
                total_laptops=len(summaries),
                total_configurations=len(summaries),
                laptops=summaries,
            )
            self._save_if_requested(catalog_result, output_file)
            return catalog_result

        # 2. Level 2: Deep spec crawl
        detailed_laptops: list[LaptopDetail] = []
        for idx, summary in enumerate(summaries, 1):
            detail = self.scraper.get_laptop_detail(summary=summary)
            if detail is not None:
                detailed_laptops.append(detail)
            if limit and len(detailed_laptops) >= limit:
                break

        if detailed_laptops:
            latest_pointers = [d.name for d in detailed_laptops[:3]]

        total_configs = sum(len(d.configurations) for d in detailed_laptops)
        catalog_result = BrandCatalogResult(
            brand=self.scraper.brand_name,
            official_catalog_url=self.scraper.catalog_url,
            scrape_mode="level2",
            until_model=until_model,
            latest_pointers=latest_pointers,
            total_laptops=len(detailed_laptops),
            total_configurations=total_configs,
            laptops=detailed_laptops,
        )
        self._save_if_requested(catalog_result, output_file)
        return catalog_result

    def _save_if_requested(self, catalog: BrandCatalogResult, output_file: str | Path | None) -> None:
        if not output_file:
            return
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(catalog.model_dump(), f, indent=2, ensure_ascii=False)
```

---

### Step 3: Register in Centralized Registry

1. In [`app/schemas/laptop.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/schemas/laptop.py):
   Alias the brand results to `BrandCatalogResult`:
   ```python
   DellBrandCatalogResult = BrandCatalogResult
   AcerBrandCatalogResult = BrandCatalogResult
   GigabyteBrandCatalogResult = BrandCatalogResult
   ```

2. In [`app/services/orchestrator.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/services/orchestrator.py):
   Register the new services in `BRAND_SERVICE_REGISTRY`:
   ```python
   from app.services.dell_scraper_service import DellScraperService
   from app.services.acer_scraper_service import AcerScraperService
   from app.services.gigabyte_scraper_service import GigabyteScraperService

   BRAND_SERVICE_REGISTRY: dict[str, Type] = {
       "asus": AsusScraperService,
       "hp": HpScraperService,
       "lenovo": LenovoScraperService,
       "dell": DellScraperService,
       "acer": AcerScraperService,
       "gigabyte": GigabyteScraperService,
   }
   ```

3. In [`app/services/__init__.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/services/__init__.py):
   Export `DellScraperService`, `AcerScraperService`, and `GigabyteScraperService`.

---

## ✅ Acceptance Criteria & Verification

Your implementation will be accepted when all of the following commands execute successfully:

1. **Level 1 Overview Test**:
   ```powershell
   python -m app.cli --brand dell --mode brand-only --level 1 --limit 5
   python -m app.cli --brand acer --mode brand-only --level 1 --limit 5
   python -m app.cli --brand gigabyte --mode brand-only --level 1 --limit 5
   ```
   * Must render a Rich table with title, family, model code, and URL.

2. **Level 2 Deep Crawl Test**:
   ```powershell
   python -m app.cli --brand dell --mode brand-only --level 2 --limit 2 --save-json dell_test.json
   ```
   * Must produce a valid JSON file containing structured hardware specs (processor, RAM, storage, display, ports) and populated `latest_pointers`.

3. **Incremental Watermark Test**:
   ```powershell
   # First run captures top laptops: e.g. "Dell XPS 13 (9340)" as latest_pointers[0]
   # Second run stops at that laptop:
   python -m app.cli --brand dell --mode brand-only --level 2 --until-model "9340" --save-json dell_incremental.json
   ```
   * Must halt immediately upon encountering the watermark model without downloading older laptops.

4. **Unconstrained Full Catalog Crawl**:
   ```powershell
   python -m app.cli --brand dell --mode brand-only --level 1
   ```
   * Must scan across all pages until completion when `--limit` and `--max-pages` are omitted.

5. **Code Quality**:
   * Windows cp1252-safe: Use ASCII console indicators (`[+]`, `[-]`, `[!]`).
   * Clean imports and valid CLI execution (`python -m app.cli --help`).
