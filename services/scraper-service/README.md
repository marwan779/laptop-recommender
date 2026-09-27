# Scraper Microservice

Autonomous web scraping and hardware configuration extraction service for Egyptian laptop retail and brand official manufacturer portals.

---

## 🎯 Architecture & Design Highlights

1. **Independent Microservice Decoupling**:
   * Scrapes official manufacturer portals (ASUS, Lenovo, HP, Dell, Acer, GigaByte) and stores normalized raw results in standalone JSON files.
   * Scrapes Egyptian computer retailers (Compumarts, Sigma Computer, 2B Egypt).
   * Produces clean JSON artifacts consumed by the downstream `catalog-service`.
2. **Two-Level Ingestion**:
   * **Level 1 (Catalog Overview)**: Fast listing scan capturing model name, series family, product overview URL, official price, and preliminary generation.
   * **Level 2 (Deep Spec Crawl)**: Visits official `/techspec/` sheets, parses full specifications using Markdown conversion, extracts full MPN/SKU codes (e.g. `S5452MA-QD045W`), distinct configurations, and physical color options.
3. **Watermark / High-Water Mark Incremental Polling (`--until-model`)**:
   * Official brand catalogs default to "Sort by: Newest".
   * The scraper stops immediately upon reaching a previously indexed laptop pointer (`until_model`).
   * Saves bandwidth, avoids Cloudflare rate-limits, and makes scheduled cron updates ultra-fast.
4. **Anti-Bot Resistance**:
   * Powered by `ScraplingEngine` utilizing `StealthyFetcher` (Patchright / Playwright Chromium engine) with Chrome TLS fingerprint impersonation to bypass Cloudflare without failing on dynamic Single Page Applications (SPAs).

---

## 📂 Service Structure

```
services/scraper-service/
├── app/
│   ├── cli.py                     # Command-line interface for running scrapers
│   ├── core/
│   │   └── constants.py           # Brand definitions, catalog URLs, and headers
│   ├── engine/
│   │   ├── base.py                # IScraperEngine & ScrapedDocument interfaces
│   │   └── scrapling_engine.py    # Concrete Scrapling headless browser engine
│   ├── matching/
│   │   ├── engine.py              # CommonMatchingEngine for multi-store validation
│   │   └── normalizer.py          # SKU, MPN, and hardware text normalization
│   ├── schemas/
│   │   └── laptop.py              # Pydantic v2 data models & JSON output schemas
│   ├── scrapers/
│   │   ├── base.py                # BaseBrandScraper abstract class
│   │   └── asus.py                # ASUS Egypt brand scraper (L1 & L2)
│   ├── services/
│   │   ├── asus_scraper_service.py# ASUS standalone scraping service
│   │   └── store_aggregator.py    # Multi-store aggregation orchestrator
│   └── stores/
│       ├── base.py                # BaseStoreScraper interface
│       ├── registry.py            # Retailer store registry
│       ├── compumarts.py          # Compumarts Egypt crawler
│       ├── sigma.py               # Sigma Computer Egypt crawler
│       └── twob.py                # 2B Egypt crawler
└── tests/
    └── test_matching.py           # 12 unit tests verifying matching logic
```

---

## 🚀 CLI Commands & Examples

### 1. Brand Scraping Mode (`--mode brand-only`)

#### Full Backfill (Level 1)
```powershell
python -m app.cli --brand asus --mode brand-only --level 1 --save-json asus_l1.json
```

#### Full Backfill (Level 2 - Deep Specifications)
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --save-json asus_full_catalog.json
```

#### Incremental Cron Run (Watermark Cursor)
Stops immediately upon encountering `S3407`:
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --until-model "S3407" --save-json asus_new_laptops.json
```

**Parameters for `brand-only`:**
* `--brand`: Brand identifier (`asus`, `lenovo`, `hp`, `dell`, `acer`, `gigabyte`). Default: `asus`.
* `--level`: `1` (Listing card summaries) or `2` (Deep spec sheets & configurations). Default: `1`.
* `--until-model`: Stops when matching this model code, full name, or URL slug.
* `--max-pages`: Safety cap on pages scanned (default: `5`).
* `--limit`: Optional cap on laptops processed (default: unlimited).
* `--save-json`: Destination path for JSON output.

---

### 2. Multi-Store Search & Aggregation Mode (`--mode stores`)

Aggregates brand catalog configurations and searches Egyptian retailers to find exact matching offers:

```powershell
# Search all stores for the first 3 laptops
python -m app.cli --brand asus --mode stores --limit 3 --save-json asus_market.json

# Search specific store (e.g., Compumarts only)
python -m app.cli --brand asus --mode stores --stores compumarts --limit 2
```

---

## 🧪 Running Tests

```powershell
python -m pytest tests/test_matching.py -v
```
All 12 unit tests verify strict matching confidence thresholds, MPN resolution, sub-model hierarchy, and false positive prevention.
