# Scraper Microservice

Autonomous, anti-bot-resistant web scraping and raw data ingestion engine for Egyptian laptop retail stores and official brand manufacturer portals.

---

## 🎯 Architecture & Design Highlights

1. **Decoupled Pure Ingestion Philosophy**:
   * **Single Responsibility**: The scraper service is strictly focused on raw web extraction, DOM rendering, anti-bot evasion, and schema-validated JSON serialization.
   * **No Direct DB Connections**: Outputs standalone JSON artifacts (`brand_{name}.json`, `store_{store}.json`).
   * **Separation of Concerns**: Entity resolution, fuzzy matching, and deduplication are deferred to the downstream `catalog-service`.
2. **Two-Level Brand Ingestion**:
   * **Level 1 (Catalog Overview)**: Fast listing scan capturing model name, series family, product overview URL, official price, and preliminary generation.
   * **Level 2 (Deep Spec Crawl)**: Visits official `/techspec/` sheets, parses full specifications using Markdown conversion, extracts full MPN/SKU codes (e.g. `S5452MA-QD045W`), distinct configurations, and physical color options.
3. **Reverse Watermark / High-Water Mark Polling (`--until-model`)**:
   * Brand catalogs default to "Sort by: Newest".
   * The scraper halts immediately upon encountering a previously indexed laptop pointer (`until_model`), preventing duplicate fetches.
   * Records the top 3 newest laptops (`latest_pointers`) to provide robust watermarks for future cron runs.
   * Guarded by a safety pagination ceiling (`--max-pages 5`).
4. **Direct Retailer Store Crawling (`--mode store`)**:
   * Discovers real-time market inventory, stock availability, and live EGP prices from leading Egyptian computer retailers (Compumarts, Sigma Computer, 2B Egypt).
   * Normalizes Arabic numerals and noise words before saving structured raw store catalogs.
5. **Anti-Bot Resistance**:
   * Powered by `ScraplingEngine` utilizing `StealthyFetcher` (Patchright / Playwright Chromium engine) with Chrome TLS fingerprint impersonation to bypass Cloudflare and render dynamic Single Page Applications (SPAs).

---

## 📂 Service Structure

```
services/scraper-service/
├── app/
│   ├── cli.py                     # Command-line interface for running scrapers
│   ├── core/
│   │   ├── constants.py           # Brand definitions, catalog URLs, and headers
│   │   └── normalizer.py          # Arabic text, numeral, and token normalizer
│   ├── engine/
│   │   ├── base.py                # IScraperEngine & ScrapedDocument interfaces
│   │   └── scrapling_engine.py    # Concrete Scrapling headless browser engine
│   ├── schemas/
│   │   └── laptop.py              # Pydantic v2 domain schemas & JSON contracts
│   ├── scrapers/
│   │   ├── base.py                # BaseBrandScraper abstract class
│   │   └── asus.py                # ASUS Egypt brand scraper (Level 1 & Level 2)
│   ├── services/
│   │   └── asus_scraper_service.py# ASUS brand service orchestrator
│   └── stores/
│       ├── base.py                # BaseStoreScraper interface
│       ├── registry.py            # Retailer store registry
│       ├── compumarts.py          # Compumarts Egypt crawler
│       ├── sigma.py               # Sigma Computer Egypt crawler
│       └── twob.py                # 2B Egypt crawler
└── requirements.txt               # Service dependencies
```

---

## 🚀 CLI Commands & Examples

### 1. Brand Scraping Mode (`--mode brand-only` or `--mode brand`)

#### Full Backfill (Level 1 - Fast Listing Overview)
```powershell
python -m app.cli --brand asus --mode brand-only --level 1 --save-json asus_l1.json
```

#### Full Backfill (Level 2 - Deep Specifications Crawl)
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --save-json asus_full_catalog.json
```

#### Incremental Cron Run (Watermark Cursor)
Stops immediately upon encountering `S3407`:
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --until-model "S3407" --save-json asus_new_laptops.json
```

**Parameters for `brand-only` mode:**
* `--brand`: Brand identifier (`asus`, `lenovo`, `hp`, `dell`, `acer`, `gigabyte`). Default: `asus`.
* `--level`: `1` (Listing card summaries) or `2` (Deep spec sheets & configurations). Default: `1`.
* `--until-model`: Stops when matching this model code, full name, or URL slug.
* `--max-pages`: Safety cap on pages scanned (default: `5`).
* `--limit`: Optional cap on laptops processed (default: unlimited).
* `--save-json`: Destination path for JSON output.

---

### 2. Retailer Store Scraping Mode (`--mode store` or `--mode stores`)

Crawls live inventory, stock status, and EGP prices directly from Egyptian retailers:

```powershell
# Scrape all supported stores (Compumarts, Sigma, 2B)
python -m app.cli --mode store --stores all --limit 20

# Scrape a specific store into a custom JSON file
python -m app.cli --mode store --stores compumarts --limit 30 --save-json store_compumarts.json

# Scrape multiple specific stores
python -m app.cli --mode store --stores compumarts,sigma --limit 15
```

**Parameters for `store` mode:**
* `--stores`: Comma-separated store keys (`compumarts`, `sigma`, `twob`) or `all`. Default: `all`.
* `--limit`: Number of laptop candidates to ingest per store. Default: `20`.
* `--save-json`: Destination path for JSON output (default: `store_{store_key}.json`).

---

## 🛡️ Anti-Bot & Stealth Configuration

The scraper uses Scrapling with Playwright / Patchright to bypass Cloudflare and WAF protections:
* **TLS Fingerprint Impersonation**: Uses real Chrome TLS fingerprints via `curl_cffi` in HTTP mode.
* **Stealthy Chromium**: Uses patched browser binaries with randomized viewport dimensions, masked navigator properties, and realistic user agent headers.
* **Auto-retry with Exponential Backoff**: Resilient to temporary network hiccups or rate limits.

