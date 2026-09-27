# Laptop Recommender System (Egypt Market)

An enterprise-grade, decoupled microservices system designed to autonomously discover official laptop configurations from brand manufacturer portals in Egypt (ASUS, Lenovo, HP, Dell, Acer, GigaByte), crawl live market inventories from leading Egyptian retailers (Compumarts, Sigma Computer, 2B Egypt), and provide structured data persistence, entity resolution, and intelligent consumer recommendations.

---

## 🌍 The Egyptian Laptop Market: Domain Context & Challenges

The consumer laptop market in Egypt presents a uniquely challenging landscape for buyers, retailers, and data systems:

1. **Extreme Currency & Price Volatility**: Macroeconomic shifts and currency fluctuations cause local computer prices (in EGP) to change rapidly—sometimes on a weekly basis. Consumers struggle to identify fair market pricing across stores.
2. **Disorganized Retail Listings**: Egyptian retailer listings frequently combine Arabic and English text, noisy promotional slogans (*"Special Offer"*, *"Best Seller"*, *"ضمان محلي"*), and Eastern Arabic numerals (`٠١٢٣٤٥٦٧٨٩`), with no unified naming standards.
3. **Vague Hardware Descriptions**: Many retail store listings advertise generic models (e.g. *"ASUS Vivobook 14"*) while omitting critical variant identifiers (e.g. OLED vs IPS display, soldered RAM vs upgradeable SODIMM slots, or exact TDP limits).
4. **Lack of a Canonical Ground Truth**: Independent comparison platforms often fail because they lack direct access to manufacturer-grade technical specification sheets.

### The Solution:
This project solves these challenges by establishing an **autonomous, decoupled microservices pipeline**:
* **Official Brand Ingestion**: Direct scraping of manufacturer portals (e.g. ASUS Egypt eStore) to capture the **uncompromising ground truth**: exact sub-model SKUs, manufacturer part numbers (MPNs), factory hardware configurations, and color variants.
* **Retailer Inventory Crawling**: Direct crawling of major Egyptian retail hubs to capture live prices, stock status, and retailer URLs.
* **Centralized Relational Persistence & Matching**: Consuming raw JSON outputs into a centralized PostgreSQL catalog with immutable audit trails, field-level data provenance, and entity resolution deferred to the catalog core.

---

## 🏗️ High-Level System Architecture

```mermaid
flowchart TD
    subgraph Manufacturer Portals ["Official Brand Portals (Egypt)"]
        ASUS["ASUS Egypt Store"]
        LENOVO["Lenovo Egypt"]
        HP["HP Egypt"]
        DELL["Dell Egypt"]
        ACER["Acer Egypt"]
        GIGA["GigaByte Egypt"]
    end

    subgraph Retailer Stores ["Egyptian Retailer Stores"]
        COMP["Compumarts Egypt"]
        SIGMA["Sigma Computer"]
        TWOB["2B Egypt"]
    end

    subgraph ScraperService ["scraper-service (Pure Ingestion Engine)"]
        ENG["ScraplingEngine (Stealth Chrome / Anti-Bot)"]
        L1["Level 1: Fast Catalog Discovery (Cards)"]
        L2["Level 2: Deep Spec & SKU Crawl (/techspec/)"]
        WM["Watermark Cursor Engine (until_model)"]
        STORE_ENG["Store Crawlers (Compumarts, Sigma, 2B)"]
    end

    subgraph StandaloneArtifacts ["Standalone Ingestion JSON Artifacts"]
        JSON_BRAND["brand_{brand}.json (Official Specs & SKUs)"]
        JSON_STORE["store_{store}.json (Raw Store Inventory & Prices)"]
    end

    subgraph CatalogService ["catalog-service (Business Layer & Database)"]
        RAW_INGEST["Raw Payload Ingestion Pipeline"]
        RAW_DB[("RawLaptopRecord (JSONB Audit Log)")]
        SPEC_EVID[("SpecificationEvidence (Field-Level Provenance)")]
        ENTITY_RES["Entity Resolution & Matching Engine"]
        CANONICAL_DB[("Canonical Models (Brand, Family, Model, Configuration)")]
        ALIAS_DB[("LaptopConfigurationAlias (Store SKU Bindings)")]
        REC_API["Recommendation & Filtering API (FastAPI)"]
    end

    ManufacturerPortals --> ENG
    ENG --> L1
    L1 --> WM
    WM --> L2
    L2 --> JSON_BRAND

    RetailerStores --> ENG
    ENG --> STORE_ENG
    STORE_ENG --> JSON_STORE

    JSON_BRAND --> RAW_INGEST
    JSON_STORE --> RAW_INGEST
    RAW_INGEST --> RAW_DB
    RAW_DB --> SPEC_EVID
    RAW_DB --> ENTITY_RES
    SPEC_EVID --> ENTITY_RES
    ENTITY_RES --> CANONICAL_DB
    ENTITY_RES --> ALIAS_DB
    CANONICAL_DB --> REC_API
    ALIAS_DB --> REC_API
```

---

## 🎯 Decoupled Ingestion vs. Matching Philosophy

A foundational architectural decision in this system is that **`scraper-service` is strictly an ingestion service**:
* **Pure Ingestion**: The scraper's only responsibility is to visit websites, bypass anti-bot defenses, parse DOM content, and serialize structured raw data into standalone JSON files.
* **No Database Dependencies**: The scraper service does not require access to PostgreSQL, database credentials, or Alembic migrations. It can be run independently on remote worker nodes, scheduled via cron, or executed in isolated Docker containers.
* **Why Matching Logic Was Removed from Scraping**:
  1. *Fragility & Latency*: Web scraping is network-bound, slow, and prone to rate limits. Coupling complex entity resolution or database lookups during a scraping session introduces severe failure cascades.
  2. *Re-runnability & Idempotence*: By persisting the raw scraped payloads (`brand_{brand}.json` and `store_{store}.json`) into `RawLaptopRecord` (PostgreSQL `JSONB`), data engineers can adjust, test, and re-run entity resolution algorithms offline without re-crawling the web.
  3. *Auditability & Provenance*: Matching requires historical context and multi-source heuristics. The `catalog-service` manages this via `SpecificationEvidence` (field-level confidence and source tracking) and `LaptopConfigurationAlias`.

---

## 📂 Repository Layout

```
laptop-recommender/
├── Docs/                                  # Master technical documentation
│   ├── ARCHITECTURE.md                    # System architecture, schemas, and data models
│   ├── GETTING_STARTED.md                 # Complete developer setup & environment guide
│   ├── BRAND_SCRAPING_GUIDE.md            # Building brand scrapers (L1/L2, markdown parsing)
│   ├── STORE_SCRAPING_GUIDE.md            # Retailer store crawlers and schemas
│   └── tasks/
│       └── NEW_BRAND_SCRAPERS_TASK.md     # Engineering task for Acer, Dell, and GigaByte
├── services/
│   ├── scraper-service/                   # Standalone Web Ingestion Engine
│   │   ├── app/
│   │   │   ├── cli.py                     # Scraper CLI (Brand & Store modes)
│   │   │   ├── core/                      # Constants, URLs, and token normalizer
│   │   │   ├── engine/                    # Scrapling headless browser & HTTP abstraction
│   │   │   ├── schemas/                   # Pydantic v2 data models & JSON output schemas
│   │   │   ├── scrapers/                  # Brand scrapers (ASUS, BaseBrandScraper)
│   │   │   ├── services/                  # Brand orchestrators (AsusScraperService)
│   │   │   └── stores/                    # Store scrapers (Compumarts, Sigma, 2B)
│   │   ├── requirements.txt               # Scraper dependencies
│   │   └── README.md                      # Scraper service documentation
│   └── catalog-service/                   # Relational Catalog, Matching & API Engine
│       ├── alembic/                       # Alembic schema migrations
│       ├── app/
│       │   ├── api/                       # FastAPI routes (Health, Catalog, Recommendations)
│       │   ├── core/                      # Settings, async database session engine
│       │   ├── models/                    # SQLAlchemy 2.0 ORM models (4-Tier + Components)
│       │   ├── repositories/              # Database query repositories
│       │   ├── schemas/                   # Pydantic v2 API schemas
│       │   ├── services/                  # Ingestion, matching, and recommendation logic
│       │   └── main.py                    # FastAPI application entrypoint
│       ├── requirements.txt               # Catalog service dependencies
│       └── README.md                      # Catalog service documentation
└── .vscode/                               # Workspace settings for multi-virtual environments
```

---

## 🔍 Deep Dive: `scraper-service`

### 1. Brand Scraping (Two-Level Ingestion Model)
* **Level 1 (Listing Overview)**:
  * Crawls the official brand eStore catalog sorted by **Newest** (e.g. `https://www.asus.com/eg-en/store/laptops/`).
  * Extracts product card metadata: laptop full name, series family, base model code, product overview URL, official price in EGP, and thumbnail image.
  * Evaluates the **Watermark Cursor (`until_model`)**: If the card matches the watermark, Level 1 halts immediately.
* **Level 2 (Deep Specifications Crawl)**:
  * Navigates to the official `/techspec/` page for each Level 1 laptop.
  * Uses `markdownify` to convert complex nested HTML spec tables into clean Markdown.
  * Extracts exact SKU codes (e.g. `S5452MA-QD045W`), manufacturer part numbers (MPNs), distinct physical configurations, and available colors.
  * Maps specifications into structured fields: Processor, Graphics, Display, Memory, Storage, I/O Ports, Battery, Weight, and Dimensions.

### 2. Reverse Watermark / Incremental Polling Pattern (`--until-model`)
Instead of guessing publication dates via brittle meta tags or heuristic CPU generation tables, the scraper uses a **Reverse Watermark Cursor Pattern**:
* The official catalog is sorted by **Newest**.
* During each run, the scraper records the **top 3 newest laptop names** in `latest_pointers` (e.g. `["ASUS Vivobook S14 (S5452)", "ASUS Vivobook S14 (S3407)", "ProArt P16 (H7607)"]`).
* On the subsequent cron run, `catalog-service` passes `--until-model "S5452"`.
* The scraper loops through new cards and **halts immediately** upon encountering the watermark card without crawling older laptops.
* **Delisted Model Safeguard**: The `--max-pages` parameter (default: 5) ensures the scraper never enters an infinite loop if the watermark model was renamed or unlisted.

### 3. Retailer Store Crawling (`--mode store`)
Crawls live inventory, stock availability, and current EGP prices from leading Egyptian computer stores:
* **Compumarts Egypt** (`compumarts.com`): Search query and HTML card parsing.
* **Sigma Computer** (`sigma-computer.com`): Structured product grid parsing.
* **2B Egypt** (`2b.com.eg`): Bilingual Arabic/English title parsing and Arabic numeral conversion.
* Outputs standardized standalone JSON catalogs (`store_{store_key}.json`).

### 4. Anti-Bot Evasion via `ScraplingEngine`
* Powered by `ScraplingEngine` utilizing `StealthyFetcher` (Patchright / Playwright Chromium engine).
* **TLS Fingerprint Impersonation**: Uses real Chrome TLS fingerprints via `curl_cffi` for fast HTTP requests.
* **Stealth Headless Browser**: Masks `navigator.webdriver`, randomizes viewport sizes, injects realistic headers, and solves JavaScript-rendered SPAs protected by Cloudflare.

---

## 🗄️ Deep Dive: `catalog-service`

### 1. Technology Stack
* **Framework**: FastAPI (Async Python 3.11+)
* **ORM**: SQLAlchemy 2.0 (Fully typed `Mapped` columns, AsyncSession)
* **Database**: PostgreSQL 15+ (with native `JSONB` support)
* **Migrations**: Alembic (Async migration runner)
* **Validation**: Pydantic v2

### 2. The 4-Tier Product Hierarchy
To prevent configuration collisions, the data model strictly separates marketing families from physical configurations:

```
Brand (e.g., ASUS)
  ↓
LaptopFamily (e.g., Vivobook)
  ↓
LaptopModel (e.g., ASUS Vivobook S14 (S5452))
  ↓
LaptopConfiguration (e.g., S5452MA-QD045W)
  ├── Canonical Components (CPU, GPU, Display, RAM, Storage, Battery, Ports)
  └── Retail Offers via LaptopConfigurationAlias (Compumarts, Sigma, 2B)
```

### 3. Deep Hardware Component Entities
* **`CPU`**: Manufacturer, architecture, generation, core counts (P-cores / E-cores), TDP, base/boost clocks, benchmark scores.
* **`GPU`**: Integrated vs Discrete, architecture, VRAM size, memory type, TDP, benchmark scores.
* **`Display`**: Screen size (inches), resolution (width x height), panel type (OLED, IPS), refresh rate (Hz), color gamut (sRGB, DCI-P3 %), brightness (nits).
* **`LaptopMemory`** & **`LaptopStorage`**: Slot counts, soldered flags, capacity, expansion slots.
* **`Battery`**: Capacity (Wh), cell count, measured runtime hours.
* **`LaptopPort`**, **`LaptopConnectivity`**, **`LaptopWebcam`**, **`LaptopAudio`**, **`LaptopThermals`**, **`LaptopBuild`**, **`LaptopMeasurement`**.

### 4. Ingestion Pipeline & Audit Trail
* **`RawLaptopRecord`**: Stores raw scraped payloads (`raw_payload` as PostgreSQL `JSONB`), external IDs, ingestion timestamp, and processing status (`PENDING`, `PROCESSED`, `FAILED`).
* **`SpecificationEvidence`**: Records exact field-level extraction history (`field_name`, `field_value`, `source_url`, `confidence`, `collected_at`).
* **`LaptopConfigurationAlias`**: Maps retailer SKU strings and external IDs to the canonical `LaptopConfiguration`.
* **Matching / Entity Resolution**: Handled inside `catalog-service` during pipeline processing of `RawLaptopRecord`.

---

## ⚡ Quick Start & Developer Setup

### 1. Prerequisites
* **Python 3.11+** (64-bit)
* **PostgreSQL 15+** (Local service or Docker container)
* **PowerShell** (Windows) or **Bash** (Linux/macOS)
* **Git**

---

### 2. Setting Up `scraper-service`
```powershell
# Navigate to scraper service
cd "services/scraper-service"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright Chromium binaries
playwright install chromium
```

---

### 3. Setting Up `catalog-service`
```powershell
# In a separate terminal, navigate to catalog service
cd "services/catalog-service"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Set your PostgreSQL connection string in .env:
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/laptop_recommender

# Run database migrations
alembic upgrade head

# Start the FastAPI server
uvicorn app.main:app --reload --port 8000
```
Interactive API documentation will be available at `http://localhost:8000/docs`.

---

## 🚀 Scraper CLI Usage & Examples

Always run commands as modules from within `services/scraper-service` with its virtual environment activated:

```powershell
cd "services/scraper-service"
.\.venv\Scripts\Activate.ps1
```

### Brand Scraping Mode (`--mode brand-only` or `--mode brand`)

#### 1. Level 1: Quick Brand Catalog Scan (Newest First)
```powershell
python -m app.cli --brand asus --mode brand-only --level 1
```

#### 2. Level 2: Full Deep Specification Crawl
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --save-json asus_catalog.json
```

#### 3. Incremental Update via Watermark Cursor
Halts immediately upon reaching the watermark laptop pointer:
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --until-model "S3407" --save-json asus_new.json
```

---

### Store Scraping Mode (`--mode store` or `--mode stores`)

Crawls live market inventory, stock status, and EGP prices directly from Egyptian computer retailers:

```powershell
# Scrape all supported stores (Compumarts, Sigma, 2B)
python -m app.cli --mode store --stores all --limit 20

# Scrape a specific store
python -m app.cli --mode store --stores compumarts --limit 30 --save-json store_compumarts.json

# Scrape specific multiple stores
python -m app.cli --mode store --stores compumarts,sigma --limit 15
```

---

## 📚 Documentation Index

All detailed architecture specifications, developer guides, and engineering tasks are maintained in the [`Docs/`](file:///d:/Development/Side%20Projects/laptop-recommender/Docs) folder:

| Document | Description |
| :--- | :--- |
| [**System Architecture (`Docs/ARCHITECTURE.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/ARCHITECTURE.md) | In-depth microservice design, data models, entity relationships, and watermark cursor mechanics. |
| [**Getting Started Guide (`Docs/GETTING_STARTED.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/GETTING_STARTED.md) | Step-by-step developer setup, database provisioning, IDE configuration, and troubleshooting. |
| [**Brand Scraping Guide (`Docs/BRAND_SCRAPING_GUIDE.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/BRAND_SCRAPING_GUIDE.md) | Guide to building and maintaining brand scrapers, Level 1/2 models, and Markdown spec extraction. |
| [**Store Scraping Guide (`Docs/STORE_SCRAPING_GUIDE.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/STORE_SCRAPING_GUIDE.md) | Guide to retailer store crawlers (Compumarts, Sigma, 2B), token normalization, and output schemas. |
| [**Catalog Specifications Report (`Docs/CATALOG_SPECIFICATIONS_REPORT.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/CATALOG_SPECIFICATIONS_REPORT.md) | Database entities checklist, fields obtained from brand portals, and external enrichment requirements. |
| [**New Brand Scrapers Task (`Docs/tasks/NEW_BRAND_SCRAPERS_TASK.md`)**](file:///d:/Development/Side%20Projects/laptop-recommender/Docs/tasks/NEW_BRAND_SCRAPERS_TASK.md) | Detailed handover task specification for implementing **Acer**, **Dell**, and **GigaByte** brand services. |

---

## 🗺️ Roadmap & Next Steps

1. **Lenovo & HP Brand Scrapers**: Implement official catalog ingestion for Lenovo Egypt and HP Egypt following the ASUS reference pattern.
2. **Acer, Dell & GigaByte Handover**: Implement brand scrapers as detailed in `Docs/tasks/NEW_BRAND_SCRAPERS_TASK.md`.
3. **Catalog Ingestion Pipeline**: Implement the async ingestion worker in `catalog-service` to process `brand_{brand}.json` and `store_{store}.json` into `RawLaptopRecord` and `SpecificationEvidence`.
4. **Entity Resolution Engine**: Implement fuzzy and MPN-based matching in `catalog-service` to link raw retailer offers to canonical `LaptopConfiguration` items.
5. **AI Recommendation Engine**: Build vector search and multi-criteria recommendation scoring (price-to-performance, battery life, display quality) via FastAPI endpoints.

