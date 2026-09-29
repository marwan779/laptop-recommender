# Engineering Task: Implement Store Scrapers for Amazon Egypt, Noon Egypt, and B.TECH Egypt

## 📋 Task Overview

* **Task Title**: Build Retail Store Scrapers for Amazon Egypt, Noon Egypt, and B.TECH Egypt
* **Assigned To**: Scraping / Backend Engineer
* **Target Services**: `services/scraper-service/app/stores/`
* **Target Stores**:
  1. **Amazon Egypt** (`https://www.amazon.eg`)
  2. **Noon Egypt** (`https://www.noon.com/egypt-en/`)
  3. **B.TECH Egypt** (`https://btech.com/en/`)
* **Reference Implementations**:
  * [`app/stores/base.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/base.py) (Base class, accessory filtering, and `record_skipped` contract)
  * [`app/stores/twob.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/twob.py) (Magento 2 architecture reference for B.TECH)
  * [`app/stores/tradeline.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/tradeline.py) (Shopify / JSON API & multi-variant extraction)
  * [`app/stores/compumarts.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/compumarts.py) (Predictive search & specs table parsing)
  * [`app/services/orchestrator.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/services/orchestrator.py) (Orchestration facade, dynamic registry dispatch, and email trigger)

---

## 🎯 Objective

You must implement retail store scrapers for Egypt's three largest e-commerce and electronics retailers: **Amazon Egypt**, **Noon Egypt**, and **B.TECH Egypt**. 

The scrapers are responsible for raw retail ingestion: extracting laptop product titles, current EGP pricing, availability/stock status, retailer SKUs / MPNs / ASINs, PDP URLs, images, and full technical specifications. They must feed downstream matching and entity resolution services in `catalog-service`.

You **MUST follow the exact engineering flow below**:
1. **Identify the Store "All Laptops" URLs** and catalog scope for each retailer.
2. **Explore and verify "Newest" chronological sorting** on live endpoints before building parsers.
3. **Create the scraper classes** in `app/stores/amazon.py`, `app/stores/noon.py`, and `app/stores/btech.py` inheriting from `BaseStoreScraper`.
4. **Ensure all parameters are defined and optional** (`level: int = 1`, `until_model: str | list[str] | None = None`, `max_pages: int | None = None`, `limit: int | None = None`) with zero-safe checking (`if max_pages and page > max_pages: break`).
5. **Implement Level 1 (Catalog Cards/JSON) and Level 2 (Deep PDP Specs)** extraction.
6. **Implement candidate search** via `search_candidates(query: str, limit: int = 5)`.
7. **Filter out non-laptop accessories** via `_is_standalone_accessory` AND record skipped items via `self.record_skipped()`.
8. **Support dual watermark checks**: pre-enrichment check (title, slug, card SKU/ASIN) AND post-enrichment check (for MPNs/part numbers discovered on PDP).
9. **Register all 3 stores** in `STORE_REGISTRY` in `app/stores/registry.py` and export in `app/stores/__init__.py`.
10. **Verify and explain execution using the CLI** (`python -m app.cli --mode store --stores amazon,noon,btech`).
11. **Add comprehensive unit tests** in `tests/test_amazon_scraper.py`, `tests/test_noon_scraper.py`, and `tests/test_btech_scraper.py`, plus tests in `tests/test_skipped_laptops.py`.
12. **Verify integration with `ScrapeOrchestrator`, background email reporting, and the FastAPI endpoint (`POST /api/v1/scrape`)**.
13. **Commit and push all changes** to the repository.

---

## 📂 Files to Create and Edit

### 1. New Scraper Files to Create:
* `services/scraper-service/app/stores/amazon.py`: The `AmazonStoreScraper` implementation.
* `services/scraper-service/app/stores/noon.py`: The `NoonStoreScraper` implementation.
* `services/scraper-service/app/stores/btech.py`: The `BTechStoreScraper` implementation.

### 2. New Test Files to Create:
* `services/scraper-service/tests/test_amazon_scraper.py`: Pytest suite with mock HTML/fixtures.
* `services/scraper-service/tests/test_noon_scraper.py`: Pytest suite with mock JSON/HTML fixtures.
* `services/scraper-service/tests/test_btech_scraper.py`: Pytest suite with mock HTML fixtures.

### 3. Existing Files to Update:
* `services/scraper-service/app/stores/registry.py`: Register `"amazon"`, `"noon"`, and `"btech"` in `STORE_REGISTRY`.
* `services/scraper-service/app/stores/__init__.py`: Export `AmazonStoreScraper`, `NoonStoreScraper`, and `BTechStoreScraper`.
* `services/scraper-service/tests/test_skipped_laptops.py`: Add unit tests ensuring skipped accessories and unparseable items are captured in `skipped_laptops`.

---

## 🌐 Target Retailers Architecture & Technical Discovery

### Store 1: Amazon Egypt (`amazon`)
* **Store Name**: `Amazon Egypt`
* **Store Key**: `amazon`
* **Base URL**: `https://www.amazon.eg`
* **Domain**: `amazon.eg`
* **Catalog Category Node / URLs**:
  * Laptops category browse node: `https://www.amazon.eg/s?i=computers&rh=n%3A21832907031` (Laptops & Traditional Laptops node)
  * English interface: `https://www.amazon.eg/s?i=computers&rh=n%3A21832907031&language=en_AE`
* **Chronological Sorting (Newest First)**:
  * Amazon query parameter: `&s=date-desc-rank` (Sort by Newest Arrivals)
  * Full sorted URL: `https://www.amazon.eg/s?i=computers&rh=n%3A21832907031&s=date-desc-rank&language=en_AE&page={page}`
* **Bot Protection & Headers**:
  * Amazon actively checks for browser headers and TLS signatures. You MUST use `self.engine.fetch(url, stealth=True)` or `curl_cffi` session with `impersonate="chrome120"` and standard English browser headers.
* **Key Selectors**:
  * Product cards: `div.s-result-item[data-asin]` (filter out items where `data-asin` is empty).
  * Title: `h2 a span` or `h2 span`.
  * URL: `h2 a.a-link-normal[href]`.
  * Price: `.a-price .a-offscreen` or `.a-price-whole` + `.a-price-fraction`.
  * Image: `img.s-image[src]`.
  * Level 2 Specs Table: `#productDetails_techSpec_section_1 tr`, `#poExpander tr`, or `#detailBullets_feature_div li`.

---

### Store 2: Noon Egypt (`noon`)
* **Store Name**: `Noon`
* **Store Key**: `noon`
* **Base URL**: `https://www.noon.com`
* **Domain**: `noon.com`
* **Catalog Scope & URLs**:
  * Category landing: `https://www.noon.com/egypt-en/electronics-and-mobiles/computers-and-accessories/laptops-and-notebooks/`
* **Architecture & Extraction Strategy**:
  * Noon is a Next.js Single Page Application (SPA).
  * Strategy A (Recommended - Fast JSON): Fetch the HTML page and parse the embedded `<script id="__NEXT_DATA__" type="application/json">` JSON script tag, or call Noon's catalog API endpoint with `x-platform: web` and `x-locale: en-eg`.
  * In `__NEXT_DATA__`, product hits are available under `props.pageProps.catalog.hits` or `props.pageProps.products`.
* **Chronological Sorting (Newest First)**:
  * Sort parameter on Noon: `?sort[by]=created_at&sort[dir]=desc` or `?sort[by]=recency` or `?sort=newest`.
* **Identifiers & Specs**:
  * Noon SKU: Available in `sku` (e.g. `N53381483A` or `Z64...`).
  * MPN / Model: Often found in `model_number` in product specifications or attributes.
  * Level 2 Specs: In PDP JSON (`props.pageProps.product.specifications`) or specs table `.specifications`.

---

### Store 3: B.TECH Egypt (`btech`)
* **Store Name**: `B.TECH`
* **Store Key**: `btech`
* **Base URL**: `https://btech.com`
* **Domain**: `btech.com`
* **Catalog Scope & URLs**:
  * English category URL: `https://btech.com/en/laptops-pcs/laptops.html`
* **Architecture & Extraction Strategy**:
  * B.TECH is built on **Magento 2 / Adobe Commerce** (the exact same architecture as 2B Egypt `twob.py`).
* **Chronological Sorting (Newest First)**:
  * Magento 2 chronological sorting: `?product_list_order=entity_id&product_list_dir=desc` or `?product_list_order=created_at&product_list_dir=desc` or `?product_list_order=news_from_date`.
  * Verified parameter: `https://btech.com/en/laptops-pcs/laptops.html?p={page}&product_list_order=entity_id&product_list_dir=desc`
* **Key Selectors**:
  * Product card: `li.product-item`, `.product-item-info`.
  * Title & Link: `a.product-item-link`.
  * Price: `.price-box .price-container [data-price-amount]` or `span.price`.
  * Stock: `.stock.unavailable` indicates out of stock.
  * Level 2 PDP Specs: `table#product-attribute-specs-table tr` or `table.data.table.additional-attributes tr`.

---

## 🧭 Developer Step-by-Step Flow

### Step 1: Identify Store "All Laptops" URLs & Catalog Scope

Before coding, verify the live URLs for each store:

1. **Amazon Egypt**:
   ```
   https://www.amazon.eg/s?i=computers&rh=n%3A21832907031&language=en_AE
   ```
2. **Noon Egypt**:
   ```
   https://www.noon.com/egypt-en/electronics-and-mobiles/computers-and-accessories/laptops-and-notebooks/
   ```
3. **B.TECH Egypt**:
   ```
   https://btech.com/en/laptops-pcs/laptops.html
   ```

Verify that each URL returns laptop computers and excludes desktops, tablets, and standalone components.

---

### Step 2: Explore & Verify "Newest" Sorting

Inspect live network requests in DevTools or via quick scratch scripts to confirm newest-first ordering:

1. **Amazon**:
   * Verify that adding `&s=date-desc-rank` orders newly listed laptops at the top.
2. **Noon**:
   * Inspect the sort dropdown on Noon Egypt. Note the query param (`sort[by]=recency` or `sort[by]=created_at&sort[dir]=desc`) and confirm that the latest models (e.g. M3/M4 MacBooks, Core Ultra, RTX 40-series) appear on page 1.
3. **B.TECH**:
   * Check Magento's sort options. `product_list_order=entity_id&product_list_dir=desc` orders by internal auto-incrementing ID (highest ID = newest added product).

---

### Step 3: Implement the Scraper Classes

Create each scraper file in `services/scraper-service/app/stores/`:
* `amazon.py` -> `class AmazonStoreScraper(BaseStoreScraper):`
* `noon.py` -> `class NoonStoreScraper(BaseStoreScraper):`
* `btech.py` -> `class BTechStoreScraper(BaseStoreScraper):`

#### Common Structure Template:
```python
import html
import itertools
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.engine.base import IScraperEngine
from app.matching.normalizer import ModelNormalizer
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class AmazonStoreScraper(BaseStoreScraper):
    """Store scraper for Amazon Egypt (https://www.amazon.eg)."""

    BASE_URL = "https://www.amazon.eg"
    CATALOG_URL = "https://www.amazon.eg/s?i=computers&rh=n%3A21832907031&s=date-desc-rank&language=en_AE&page={page}"

    def __init__(self, engine: IScraperEngine | None = None):
        super().__init__(engine=engine or None)
        self._session = cffi_requests.Session()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @property
    def store_name(self) -> str:
        return "Amazon Egypt"

    @property
    def store_key(self) -> str:
        return "amazon"

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    @property
    def base_domain(self) -> str:
        return "amazon.eg"
```

---

### Step 4: Ensure All Parameters are Defined and Optional

The `scrape_catalog` method on each scraper **must strictly match** this signature:

```python
def scrape_catalog(
    self,
    level: int = 1,
    until_model: str | list[str] | None = None,
    max_pages: int | None = None,
    limit: int | None = None,
) -> list[RetailerProduct]:
    """Scrape laptops catalog with Level 1/2 extraction and watermark stopping.

    Args:
        level: 1 for fast catalog card summaries, 2 for deep PDP spec crawling. Default: 1.
        until_model: Optional watermark pointer (name, MPN, SKU, or slug). Stops crawling
                     immediately upon matching. Default: None.
        max_pages: Optional pagination safety ceiling. If None or 0, crawls all pages until
                   exhaustion. Default: None.
        limit: Optional maximum number of laptops to return. Default: None (unlimited).
    """
```

#### Pagination Safety Rule:
> [!IMPORTANT]
> When evaluating `max_pages`, **never** use `if max_pages is not None and page > max_pages`. If a caller passes `max_pages=0`, that would immediately break on page 1 and scrape 0 items!
> Always check:
> ```python
> if max_pages and page > max_pages:
>     break
> ```

---

### Step 5: Implement Level 1 & Level 2 Extraction

#### Level 1: Fast Catalog Card Summaries
Extract basic attributes directly from catalog cards/JSON without extra network requests:
* `title`: Clean laptop product name.
* `price_egp` / `price_str`: Numeric EGP price parsed via `self.parse_egp_price()`.
* `in_stock`: Boolean availability (`True` if purchasable, `False` if out of stock).
* `product_url`: Absolute URL to product detail page.
* `retailer_sku`: Store unique identifier (`ASIN` for Amazon, `sku` for Noon, `sku`/`entity_id` for B.TECH).
* `thumbnail_url`: High-resolution product image URL.
* `specs`: Basic specs extractable from title or card tags (RAM, Storage, CPU family).

#### Level 2: Deep PDP Specifications Crawling
When `level == 2`, fetch the product's PDP URL and parse the full hardware specification table into `specs: dict[str, str]`:
* Processor (CPU name, generation, cores).
* RAM (capacity, DDR generation, speed).
* Storage (capacity, SSD/NVMe type).
* Graphics / GPU (dedicated GPU model, VRAM).
* Display (screen size, resolution, refresh rate, panel type).
* Operating System.
* Official Manufacturer Part Number (MPN).

---

### Step 6: Implement Search Candidates Endpoint

Implement `search_candidates(query: str, limit: int = 5) -> list[RetailerProduct]` on each scraper:
* **Amazon**: Use search query URL `https://www.amazon.eg/s?k={quote_plus(query)}&language=en_AE`.
* **Noon**: Use Noon search endpoint `https://www.noon.com/egypt-en/search/?q={quote_plus(query)}`.
* **B.TECH**: Use Magento search URL `https://btech.com/en/catalogsearch/result/?q={quote_plus(query)}`.
* Return parsed `RetailerProduct` candidate objects matching the query.

---

### Step 7: Filter Accessories & Record Skipped Items

1. In each scraper, define any store-specific accessory keywords to supplement `BaseStoreScraper.NON_LAPTOP_KEYWORDS`.
2. When an accessory is detected (backpacks, sleeves, chargers, cooling pads, mouse, keyboard covers), **do not silently discard it**.
3. Call `self.record_skipped()`:
   ```python
   if self._is_standalone_accessory(title):
       self.record_skipped(
           name=title,
           reason="Filtered out non-laptop accessory or peripheral",
           url=product_url,
           stage="level1_filter",
       )
       continue
   ```
4. If a card or variant cannot be parsed or has a zero/invalid price, record it:
   ```python
   self.record_skipped(
       name=title,
       reason="Product variant could not be parsed or zero/invalid price",
       url=product_url,
       stage="level1_parse",
   )
   ```

---

### Step 8: Dual Watermark Stopping Logic

Support fast incremental scraping using the `until_model` pointer:
1. **Pre-enrichment Check**:
   Before making a network call for PDP specs, check if `until_model` matches the listing title, SKU, or URL slug:
   ```python
   if until_model and self._matches_watermark(title, until_model):
       print(f"[{self.store_name}] Watermark matched '{until_model}'. Halting crawl.")
       watermark_hit = True
       break
   ```
2. **Post-enrichment Check**:
   After Level 2 extraction, check if `until_model` matches the newly extracted MPN or model code:
   ```python
   if level == 2 and until_model and any(
       self._matches_watermark(ident, until_model) for ident in [product.mpn, product.model_code]
   ):
       print(f"[{self.store_name}] Post-enrichment watermark matched '{until_model}'. Halting crawl.")
       watermark_hit = True
       break
   ```

---

### Step 9: Register in Store Registry

Update `services/scraper-service/app/stores/registry.py`:

```python
from app.stores.amazon import AmazonStoreScraper
from app.stores.btech import BTechStoreScraper
from app.stores.compumarts import CompumartsStoreScraper
from app.stores.elbadr import ElBadrStoreScraper
from app.stores.noon import NoonStoreScraper
from app.stores.sigma import SigmaComputerStoreScraper
from app.stores.tradeline import TradelineStoreScraper
from app.stores.twob import TwoBStoreScraper

STORE_REGISTRY: dict[str, Type[BaseStoreScraper]] = {
    "compumarts": CompumartsStoreScraper,
    "elbadr": ElBadrStoreScraper,
    "sigma": SigmaComputerStoreScraper,
    "twob": TwoBStoreScraper,
    "tradeline": TradelineStoreScraper,
    "amazon": AmazonStoreScraper,
    "noon": NoonStoreScraper,
    "btech": BTechStoreScraper,
}
```

And export the new scrapers in `services/scraper-service/app/stores/__init__.py`.

---

### Step 10: CLI Verification & Testing Commands

Verify that the CLI dynamically discovers and executes the new stores:

```powershell
# 1. Test Amazon Egypt (Level 1, limit 3)
python -m app.cli --mode store --stores amazon --level 1 --limit 3

# 2. Test Noon Egypt (Level 1, limit 3)
python -m app.cli --mode store --stores noon --level 1 --limit 3

# 3. Test B.TECH Egypt (Level 1, limit 3)
python -m app.cli --mode store --stores btech --level 1 --limit 3

# 4. Test Deep Specs (Level 2, limit 1) with JSON export
python -m app.cli --mode store --stores amazon --level 2 --limit 1 --save-json scraping-results\stores\store_amazon.json

# 5. Test Multi-Store Batch
python -m app.cli --mode store --stores amazon,noon,btech --level 1 --limit 2
```

---

### Step 11: Unit & Integration Tests

Create three separate test files:
1. `tests/test_amazon_scraper.py`
2. `tests/test_noon_scraper.py`
3. `tests/test_btech_scraper.py`

Each test suite must include mock HTML/JSON fixtures and test:
* Store properties (`store_name`, `store_key`, `base_url`, `base_domain`).
* Price parsing (`parse_egp_price` handles thousands commas, "EGP", decimals).
* Level 1 card/JSON parsing.
* Level 2 PDP specs extraction.
* Accessory filtering (`_is_standalone_accessory` returns True for bags, sleeves, adapters, chargers, etc.).
* Watermark stopping behavior (`until_model` halts scraping immediately).
* Candidate search (`search_candidates`).

Also update `tests/test_skipped_laptops.py` to add tests for `AmazonStoreScraper`, `NoonStoreScraper`, and `BTechStoreScraper`.

Run the entire test suite:
```powershell
.venv\Scripts\python.exe -m pytest -v
```

---

### Step 12: Orchestrator, Background Email, & API Verification

1. **Orchestrator Resolution**:
   Verify that `target_type="store", targets="all"` and `target_type="both", targets="all"` automatically resolve the new stores:
   ```powershell
   python -c "from app.services.orchestrator import ScrapeOrchestrator; from app.schemas.orchestrator import ScrapeRequest; orch = ScrapeOrchestrator(); print(orch._resolve_targets(ScrapeRequest(target_type='store', targets='all')))"
   ```
2. **FastAPI Background Endpoint**:
   Verify `POST /api/v1/scrape` returns `202 Accepted` immediately for the new stores:
   ```json
   {
     "target_type": "store",
     "targets": ["amazon", "noon", "btech"],
     "level": 1,
     "limit": 2,
     "send_email": false
   }
   ```
3. **Background Email Dispatch**:
   Verify that if `send_email: true` is passed, the orchestrator dispatches a non-blocking background email report after each store scraper finishes.

---

### Step 13: Git Commit & Push

1. Stage all changes:
   ```powershell
   git status
   git add app/stores/amazon.py app/stores/noon.py app/stores/btech.py app/stores/registry.py app/stores/__init__.py tests/
   ```
2. Commit with semantic commit message:
   ```powershell
   git commit -m "feat(scrapers): implement Amazon, Noon, and B.TECH Egypt store scrapers"
   ```
3. Push to remote repository:
   ```powershell
   git push origin main
   ```

---

## 🏆 Success Criteria & Acceptance Checklist

To consider this task complete, all items in this checklist must be met:

### 1. Functional & Data Accuracy
- [ ] **All 3 Stores Implemented**: `AmazonStoreScraper`, `NoonStoreScraper`, and `BTechStoreScraper` are implemented and inherit from `BaseStoreScraper`.
- [ ] **Accurate Store Metadata**: Proper `store_name`, `store_key`, `base_url`, and `base_domain` are configured for Egypt.
- [ ] **Chronological Sorting**: "Newest" sort order is verified and applied for each store.
- [ ] **Dual Extraction Levels**:
  - Level 1 extracts listing card summaries (Title, Price in EGP, Stock, URL, SKU, Image).
  - Level 2 crawls the PDP to populate technical specs (CPU, RAM, Storage, GPU, Display).
- [ ] **Watermark Cursor (`until_model`)**: Dual watermark checks (pre-enrichment on card & post-enrichment on PDP specs) halt crawling upon matching.
- [ ] **Unconstrained Pagination**: Full catalog crawls run seamlessly when `max_pages=None` and `limit=None`.
- [ ] **Zero-Safe Pagination**: Passing `max_pages=0` is treated as unlimited, never stopping prematurely on page 1.
- [ ] **Search Candidates**: `search_candidates(query, limit)` works across all 3 stores.

### 2. Observability & Quality Assurance
- [ ] **Accessory Filtering**: Standalone accessories (backpacks, sleeves, chargers, cables, mice) are filtered out.
- [ ] **Skipped Items Tracking**: Every filtered accessory or unparseable item is recorded via `self.record_skipped()` and included in `StoreCatalogResult.skipped_laptops`.
- [ ] **Latest Pointers**: The top 3 newest scraped laptops are recorded in `StoreCatalogResult.latest_pointers`.

### 3. Orchestration & API Compatibility
- [ ] **Registry Integration**: Stores registered in `STORE_REGISTRY` under keys `"amazon"`, `"noon"`, and `"btech"`.
- [ ] **CLI Support**: Works via `python -m app.cli --mode store --stores amazon,noon,btech`.
- [ ] **FastAPI Endpoint**: `POST /api/v1/scrape` queues jobs and returns `202 Accepted` immediately.
- [ ] **Email Reports**: Background email reports are dispatched cleanly without blocking when `send_email=True`.

### 4. Testing & Code Hygiene
- [ ] **No Live Network in Tests**: Unit tests use mock HTML/JSON fixtures.
- [ ] **100% Test Passing**: All new unit test files (`test_amazon_scraper.py`, `test_noon_scraper.py`, `test_btech_scraper.py`) and existing tests in `test_skipped_laptops.py` and `test_api_scrape.py` pass without errors.
- [ ] **Clean Git Commit**: Changes committed with clean message and pushed to origin.
