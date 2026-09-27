# Laptop Recommender System (Egypt Market)

A specialized microservices architecture designed to autonomously discover laptop configurations from official brand manufacturer catalogs in Egypt (ASUS, Lenovo, HP, Dell, Acer, GigaByte), crawl leading Egyptian retailer stores (Compumarts, Sigma Computer, 2B Egypt), and perform entity resolution and price aggregation.

---

## 🏗️ Architecture Overview

The system is split into decoupled microservices:

```
laptop-recommender/
├── Docs/                              # Comprehensive architecture & developer documentation
│   ├── ARCHITECTURE.md                # System design, models, and product hierarchy
│   ├── GETTING_STARTED.md             # Developer setup, dependencies & environment
│   ├── BRAND_SCRAPING_GUIDE.md        # How to build and maintain brand scrapers
│   ├── STORE_SCRAPING_AND_MATCHING.md # Retailer crawling and fuzzy SKU matching
│   └── tasks/
│       └── NEW_BRAND_SCRAPERS_TASK.md # Handover task for Acer, Dell, and GigaByte
├── services/
│   ├── scraper-service/               # Autonomous ingestion engine (Brands & Retailers)
│   │   ├── app/
│   │   │   ├── cli.py                 # Multi-store & brand scraper CLI
│   │   │   ├── core/                  # Constants and catalog URLs
│   │   │   ├── engine/                # Scrapling headless browser & HTTP abstraction
│   │   │   ├── matching/              # Deterministic MPN & SKU matching engine
│   │   │   ├── schemas/               # Pydantic v2 domain schemas and JSON contracts
│   │   │   ├── scrapers/              # Brand scrapers (ASUS, BaseBrandScraper)
│   │   │   ├── services/              # Orchestration services (AsusService, StoreAggregator)
│   │   │   └── stores/                # Retailer scrapers (Compumarts, Sigma, 2B)
│   │   └── tests/                     # Unit & integration tests
│   └── catalog-service/               # Centralized product catalog, DB, & recommendation API
└── .vscode/                           # Multi-virtual environment IDE settings
```

---

## ⚡ Quick Start

### 1. Prerequisites
* **Python 3.11+** (Windows 64-bit recommended)
* **PowerShell** / Terminal
* **Git**

### 2. Setting Up `scraper-service`
```powershell
# Navigate to scraper service
cd "services/scraper-service"

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install Playwright/Patchright browser engines (required by Scrapling stealth fetcher)
playwright install chromium
```

### 3. Running the Scraper CLI

#### Mode 1: Brand Scraping (Official Catalogs)
```powershell
# Level 1: Quick catalog overview sorted by Newest
python -m app.cli --brand asus --mode brand-only --level 1

# Level 2: Deep crawl with full hardware specs, colors, and SKU variants
python -m app.cli --brand asus --mode brand-only --level 2 --save-json asus_catalog.json

# Incremental run (Stop when reaching a known laptop watermark)
python -m app.cli --brand asus --mode brand-only --level 2 --until-model "S3407" --save-json asus_new.json
```

#### Mode 2: Multi-Store Aggregation (Brand Catalog -> Retail Stores)
```powershell
# Discover official configurations and deep-search Compumarts, Sigma, and 2B
python -m app.cli --brand asus --mode stores --limit 3 --save-json asus_market.json
```

### 4. Running Unit Tests
```powershell
python -m pytest tests/test_matching.py
```

---

## 📚 Documentation Index

All in-depth technical documentation is located in the [`Docs/`](file:///d:/Development/Side%20Projects/laptop-recommender/Docs) directory:

1. [**System Architecture & Domain Models (`Docs/ARCHITECTURE.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/ARCHITECTURE.md)
   * Decoupled microservice pattern.
   * Product Hierarchy: Brand $\rightarrow$ Model Family $\rightarrow$ Exact Configuration $\rightarrow$ Retail Offer.
   * Watermark Cursor pattern (`until_model`, `latest_pointers`, `max_pages`).
2. [**Getting Started & Setup Guide (`Docs/GETTING_STARTED.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/GETTING_STARTED.md)
   * Step-by-step developer environment setup.
   * Scrapling engine requirements and Windows cp1252 considerations.
3. [**Brand Scraping Guide (`Docs/BRAND_SCRAPING_GUIDE.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/BRAND_SCRAPING_GUIDE.md)
   * Implementing `BaseBrandScraper`.
   * Markdown spec parsing and hardware normalization.
4. [**Store Scraping & Matching (`Docs/STORE_SCRAPING_AND_MATCHING.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/STORE_SCRAPING_AND_MATCHING.md)
   * Multi-store candidate search.
   * `CommonMatchingEngine` and MPN verification.
5. [**New Brand Scrapers Task (`Docs/tasks/NEW_BRAND_SCRAPERS_TASK.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/tasks/NEW_BRAND_SCRAPERS_TASK.md)
   * Complete implementation task for building **Acer**, **Dell**, and **GigaByte** scrapers.
