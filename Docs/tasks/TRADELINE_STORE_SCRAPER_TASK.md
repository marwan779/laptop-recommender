# Engineering Task: Implement Tradeline Egypt Store Scraper

## 📋 Task Overview

* **Task Title**: Build Store Scraper for Tradeline Egypt (Apple Authorized Reseller)
* **Assigned To**: Scraping / Backend Engineer
* **Target Directory**: `services/scraper-service/app/stores/`
* **Target Store**: **Tradeline Egypt** (`https://tradelinestores.com`)
* **Reference Implementations**:
  * [`app/stores/base.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/base.py) (Base class & interfaces)
  * [`app/stores/compumarts.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/compumarts.py) (Standard catalog crawling & search)
  * [`app/stores/sigma.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/sigma.py) (Server-side chronological sort)
  * [`app/stores/twob.py`](file:///d:/Development/Side%20Projects/laptop-recommender/services/scraper-service/app/stores/twob.py) (Entity ID sort, Level 1 & 2 crawling)

---

## 🎯 Objective

You must build a store scraper for **Tradeline Egypt** (`https://tradelinestores.com`), the primary Apple Authorized Reseller in Egypt. The scraper must ingest all Apple MacBooks (MacBook Air, MacBook Pro, MacBook Neo) while rejecting standalone accessories (cases, sleeves, adapters, chargers).

You **MUST follow the exact engineering flow below**:
1. **Identify the Store "All Laptops" URLs** for Apple MacBooks.
2. **Explore the site to discover and verify "Newest" chronological sorting**.
3. **Create the scraper service** in `app/stores/tradeline.py` inheriting from `BaseStoreScraper`.
4. **Ensure all scraper parameters are defined and optional** (`level`, `until_model`, `max_pages`, `limit`).
5. **Implement Level 1 (Catalog Cards) and Level 2 (Deep PDP Specs)** extraction.
6. **Implement candidate search** via `search_candidates(query, limit)`.
7. **Filter out accessories** using `_is_standalone_accessory`.
8. **Register the store** in `STORE_REGISTRY`.
9. **Verify and explain execution using the CLI** (`python -m app.cli`).
10. **Add comprehensive unit tests** in `tests/test_tradeline_scraper.py`.
11. **Commit and push all changes** to the repository.

---

## 📂 Files to Create & Edit

### 1. New Files to Create:
* `services/scraper-service/app/stores/tradeline.py`: The `TradelineStoreScraper` implementation.
* `services/scraper-service/tests/test_tradeline_scraper.py`: Pytest unit test suite with mock HTML fixtures.

### 2. Existing Files to Update:
* `services/scraper-service/app/stores/registry.py`: Register `tradeline` in `STORE_REGISTRY`.
* `services/scraper-service/app/stores/__init__.py`: Export `TradelineStoreScraper`.
* `services/scraper-service/app/cli.py`: Ensure `tradeline` is included in `--stores` choices and execution.

---

## 🧭 Developer Step-by-Step Flow

### Step 1: Discover Store "All Laptops" URL & Catalog Scope

Tradeline is an Apple Authorized Reseller. Their laptop catalog consists exclusively of Apple MacBooks.

1. **Category Structure**:
   * Tradeline organizes MacBooks under dedicated collections:
     * MacBook Air: `https://tradelinestores.com/collections/macbook-air`
     * MacBook Pro: `https://tradelinestores.com/collections/macbook-pro`
     * All Mac landing page: `https://tradelinestores.com/pages/view-all-mac`
   * Tradeline also runs on **Shopify**, which exposes:
     * Standard HTML collection pages: `/collections/{collection}?page={page}`
     * JSON collection feeds: `/collections/{collection}/products.json?limit=250&page={page}`
     * Predictive Search API: `/search/suggest.json?q={query}&resources[type]=product`
     * Standard Search: `/search?q={query}&type=product`

2. **Catalog Scope**:
   * Scrape across both primary MacBook collections (`macbook-air` and `macbook-pro`) or aggregate through the canonical Mac product catalog.
   * Exclude desktop Macs (iMac, Mac mini, Mac Studio) unless specifically requested, and ignore standalone accessories (adapters, sleeves, chargers).

---

### Step 2: Explore & Verify the "Newest" Sorting

Before implementing the catalog crawl, inspect how products are ordered:

1. **Shopify Collection Sorting**:
   * In Shopify, collections accept the query parameter:
     ```
     ?sort_by=created-descending
     ```
   * Other common Shopify sort keys: `created-ascending`, `best-selling`, `price-ascending`, `price-descending`, `title-ascending`.

2. **Proof & Verification**:
   * Fetch a collection page with `?sort_by=created-descending` and compare with the default sort:
     ```python
     # Verification script example:
     import urllib.request, json

     headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
     url = "https://tradelinestores.com/collections/macbook-pro/products.json?limit=50"
     req = urllib.request.Request(url, headers=headers)
     with urllib.request.urlopen(req) as resp:
         data = json.loads(resp.read().decode("utf-8"))
         products = data.get("products", [])
         for p in products:
             print(f"ID: {p['id']} | Created: {p['created_at']} | Title: {p['title']}")
     ```
   * If using Shopify's `products.json` feed, the `created_at` or `published_at` timestamp is directly available in the JSON payload, allowing you to guarantee strict chronological sorting:
     ```python
     products.sort(key=lambda p: p.get("created_at") or "", reverse=True)
     ```
   * If parsing HTML collection cards, ensure the URL incorporates `?sort_by=created-descending` or sort by product ID descending if IDs are sequential.

---

### Step 3: Implement the Scraper Service (`app/stores/tradeline.py`)

Create `services/scraper-service/app/stores/tradeline.py` inheriting from `BaseStoreScraper`:

```python
import html
import itertools
import re
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class TradelineStoreScraper(BaseStoreScraper):
    """Store scraper for Tradeline Egypt (https://tradelinestores.com)."""

    BASE_URL = "https://tradelinestores.com"
    COLLECTIONS = ["macbook-air", "macbook-pro"]

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
        return "Tradeline"

    @property
    def store_key(self) -> str:
        return "tradeline"

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    @property
    def base_domain(self) -> str:
        return "tradelinestores.com"
```

---

### Step 4: Ensure All Parameters are Defined and Optional

The `scrape_catalog` method signature **must match the unified signature** established across all store scrapers:

```python
def scrape_catalog(
    self,
    level: int = 1,
    until_model: str | list[str] | None = None,
    max_pages: int | None = None,
    limit: int | None = None,
) -> list[RetailerProduct]:
    """Scrape Tradeline MacBooks catalog with Level 1/2 extraction and watermark stopping.

    Args:
        level: 1 for fast catalog card summaries, 2 for deep PDP spec crawling. Default: 1.
        until_model: Optional watermark pointer (name, MPN, SKU, or slug). Stops crawling
                     immediately upon matching. Default: None.
        max_pages: Optional pagination safety ceiling. If None, crawls all pages until
                   exhaustion. Default: None.
        limit: Optional maximum number of laptops to return. Default: None (unlimited).
    """
```

#### Behavior Requirements:
1. **`max_pages is None`**:
   * Scrape the entire catalog without artificial pagination cutoffs.
   * Use `itertools.count(1)` or loop across collection pages until receiving an empty page or 0 new products.
2. **`until_model` Watermark**:
   * Check each product against `self._matches_watermark(identifier, until_model)`.
   * Compare against: product title, retailer SKU / MPN (e.g. `MDHE4AE/A`, `MGEA4AE/A`), and URL handle.
   * When matched, log `[Tradeline] Watermark reached ('{name}'). Stopping crawl.` and immediately return the collected products.
3. **`limit`**:
   * If `limit` is provided, stop collecting once `len(products) >= limit`.
4. **Accessory Exclusion**:
   * Check `self._is_standalone_accessory(title)`.
   * Skip standalone items such as sleeves, cases, USB-C adapters, power bricks, and mouse accessories.

---

### Step 5: Implement Level 1 & Level 2 Scraping

#### Level 1: Fast Catalog Card Summaries
* Extract from collection cards (or collection JSON):
  * `title`: Clean product name (e.g., `15-inch MacBook Air: Apple M5 chip with 10-core CPU and 10-core GPU, 512GB SSD - Silver`).
  * `price_egp` / `price_str`: Numeric EGP price (e.g., `98800.0`).
  * `in_stock`: Boolean availability (`True` if purchasable, `False` if "Out of Stock" or "Notify Me").
  * `product_url`: Absolute URL to product detail page.
  * `retailer_sku` / `mpn`: Apple part code (e.g. `MDV94AE/A`).
  * `image_url`: Primary product image URL.

#### Level 2: Deep PDP Specifications Crawling
* For each product, fetch its Product Detail Page (`product_url`).
* Extract detailed technical hardware specifications into the `specs: dict[str, Any]` dictionary:
  * **Processor / Chip**: Apple M-series chip (e.g. `M2`, `M3`, `M4`, `M4 Pro`, `M4 Max`, `M5`), CPU core count, GPU core count, Neural Engine.
  * **Memory / Unified RAM**: e.g., `16GB`, `24GB`, `36GB`, `48GB`, `64GB Unified Memory`.
  * **Storage**: SSD capacity (e.g., `256GB SSD`, `512GB SSD`, `1TB SSD`, `2TB SSD`).
  * **Display**: Screen size (e.g., `13.6-inch`, `14.2-inch`, `15.3-inch`, `16.2-inch`), Liquid Retina display, resolution, ProMotion.
  * **Color / Finish**: Space Black, Silver, Space Gray, Midnight, Starlight.
  * **Part Number / MPN**: Apple part number (e.g., `MXCT3AB/A`, `MDHE4AE/A`).
  * **Keyboard Layout**: English / Arabic keyboard layout details.

---

### Step 6: Implement Search Candidates Endpoint

Implement `search_candidates(query: str, limit: int = 5) -> list[RetailerProduct]`:
* Use Tradeline's search interface:
  * Shopify Predictive Search: `/search/suggest.json?q={quote_plus(query)}&resources[type]=product&resources[limit]={limit}`
  * Fallback to HTML search: `/search?q={quote_plus(query)}&type=product`
* Parse and return candidates as `list[RetailerProduct]`.
* Filter accessories via `_is_standalone_accessory`.

---

### Step 7: Register in Store Registry

1. In `services/scraper-service/app/stores/registry.py`:
   ```python
   from app.stores.tradeline import TradelineStoreScraper

   STORE_REGISTRY: dict[str, Type[BaseStoreScraper]] = {
       "compumarts": CompumartsStoreScraper,
       "elbadr": ElBadrStoreScraper,
       "sigma": SigmaComputerStoreScraper,
       "twob": TwoBStoreScraper,
       "tradeline": TradelineStoreScraper,
   }
   ```
2. In `services/scraper-service/app/stores/__init__.py`:
   ```python
   from app.stores.tradeline import TradelineStoreScraper

   __all__ = [
       ...,
       "TradelineStoreScraper",
   ]
   ```

---

### Step 8: CLI Verification & Documentation

Explain and test all CLI commands for Tradeline:

```powershell
# 1. Level 1 Fast Summary (limit 5)
python -m app.cli --mode store --stores tradeline --level 1 --limit 5

# 2. Level 2 Deep Specs Crawl with JSON Export
python -m app.cli --mode store --stores tradeline --level 2 --limit 3 --save-json tradeline_sample.json

# 3. Watermark Incremental Stop Test
python -m app.cli --mode store --stores tradeline --level 1 --until-model "MDHE4AE/A"

# 4. Full Catalog Ingestion (No limit, all pages)
python -m app.cli --mode store --stores tradeline --level 1
```

#### CLI Parameters Explained:
* `--mode store`: Instructs the CLI to run retailer store scrapers rather than official brand portal scrapers.
* `--stores tradeline`: Target store slug matching `STORE_REGISTRY["tradeline"]`.
* `--level 1`: Quick catalog card extraction without requesting individual product pages.
* `--level 2`: Deep crawl fetching each product page to extract full hardware specs into `specs`.
* `--until-model "<watermark>"`: Stops the scrape the moment a matching laptop is encountered.
* `--max-pages <N>`: Optional safety limit; omit to scrape the complete catalog.
* `--limit <N>`: Maximum items to collect.
* `--save-json <path>`: Exports output to a structured JSON file conforming to `StoreCatalogResult`.

---

### Step 9: Add Automated Unit Tests

Create `services/scraper-service/tests/test_tradeline_scraper.py`:
* Must use mock HTML/JSON responses (do NOT depend on live external network calls in automated tests).
* Test cases to include:
  1. `test_tradeline_initialization`: Verify store properties (`store_name`, `store_key`, `base_url`, `base_domain`).
  2. `test_tradeline_level1_parse`: Parse sample catalog cards/JSON, verifying titles, EGP prices, in-stock status, and SKUs.
  3. `test_tradeline_level2_specs`: Verify deep spec extraction (Apple M-series chip, RAM, SSD, display).
  4. `test_tradeline_watermark_stopping`: Ensure crawl halts when `until_model` is encountered.
  5. `test_tradeline_accessory_filtering`: Ensure non-laptop accessories (sleeves, cables, cases) are rejected.
  6. `test_tradeline_search_candidates`: Test candidate search parsing.

Run test suite:
```powershell
pytest tests/test_tradeline_scraper.py -v
```

---

### Step 10: Commit and Push to Repository

After tests pass and verification is complete:
1. Check git status:
   ```powershell
   git status
   ```
2. Add files:
   ```powershell
   git add app/stores/tradeline.py app/stores/registry.py app/stores/__init__.py tests/test_tradeline_scraper.py
   ```
3. Commit with a clean semantic commit message:
   ```powershell
   git commit -m "feat(scraper): implement Tradeline Egypt store scraper with Level 1 and 2 specs"
   ```
4. Push to remote:
   ```powershell
   git push origin main
   ```

---

## ✅ Acceptance Checklist

- [ ] `TradelineStoreScraper` created in `app/stores/tradeline.py`.
- [ ] Catalog URLs identified for MacBooks (`macbook-air`, `macbook-pro`).
- [ ] Newest sorting verified and enforced (`created_at` / `created-descending`).
- [ ] All parameters (`level`, `until_model`, `max_pages`, `limit`) defined and optional.
- [ ] Full catalog ingestion works when `max_pages` and `limit` are `None`.
- [ ] Accessory filtering excludes standalone sleeves, chargers, and cases.
- [ ] Registered in `app/stores/registry.py` and `app/stores/__init__.py`.
- [ ] CLI runs smoothly on Windows without encoding crashes.
- [ ] 100% of unit tests pass in `tests/test_tradeline_scraper.py`.
- [ ] Clean git commit pushed to `origin/main`.
