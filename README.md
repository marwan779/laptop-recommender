# 💻 Laptop Recommender System (Egyptian Market & Beyond)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=flat&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-AMQP-FF6600?style=flat&logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![Redis](https://img.shields.io/badge/Redis-Caching-DC382D?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![Clean Architecture](https://img.shields.io/badge/Architecture-Clean%20%26%20SOLID-00599C?style=flat)](#-clean-architecture--solid-principles)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An enterprise-grade, distributed recommendation platform designed to conquer the chaotic laptop retail ecosystem in Egypt. By fusing **stealth web crawling**, **global hardware specification enrichment (Icecat & OCR)**, **event-driven microservices (RabbitMQ & Transactional Outbox)**, **mathematical multi-criteria decision-making (TOPSIS)**, **aspect-based sentiment analysis of social multimedia reviews (YouTube & Reddit)**, and **ultra-fast distributed caching (Redis)**, this system turns messy, bilingual, and volatile retail data into trustworthy, personalized hardware recommendations.

---

## 📑 Table of Contents

1. [Executive Summary & Problem Statement](#-executive-summary--problem-statement)
2. [High-Level End-to-End System Architecture](#-high-level-end-to-end-system-architecture)
3. [Core Engineering Philosophies](#-core-engineering-philosophies)
   - [Clean Architecture & Layered Separation](#clean-architecture--layered-separation)
   - [SOLID Principles Compliance](#solid-principles-compliance)
   - [Transactional Outbox Pattern & Event-Driven Reliability](#transactional-outbox-pattern--event-driven-reliability)
   - [Idempotent Seeding & Reverse Watermark Polling](#idempotent-seeding--reverse-watermark-polling)
4. [Implemented Subsystems (Phase 1 & Phase 2)](#-implemented-subsystems-phase-1--phase-2)
   - [1. Data Acquisition Engine (`scraper-service`)](#1-data-acquisition-engine-scraper-service)
   - [2. Global Specification & OCR Pipeline (Icecat & Tesseract)](#2-global-specification--ocr-pipeline-icecat--tesseract)
   - [3. Relational Catalog Core (`catalog-service`)](#3-relational-catalog-core-catalog-service)
   - [4. Hardware Metrics Engine (11 TOPSIS Criteria)](#4-hardware-metrics-engine-11-topsis-criteria)
   - [5. Domain Pricing Engine & Corrupted Price Defense](#5-domain-pricing-engine--corrupted-price-defense)
   - [6. Asynchronous Event-Driven Price Synchronization](#6-asynchronous-event-driven-price-synchronization)
   - [7. Review Intelligence Pipeline & Multi-Platform Mining](#7-review-intelligence-pipeline--multi-platform-mining)
5. [Upcoming & In-Flight Subsystems (Phase 3)](#-upcoming--in-flight-subsystems-phase-3)
   - [8. Dynamic TOPSIS Recommendation Engine](#8-dynamic-topsis-recommendation-engine)
   - [9. Aspect-Based Sentiment Analysis (ABSA) & Downstream NLP](#9-aspect-based-sentiment-analysis-absa--downstream-nlp)
   - [10. High-Performance Redis Caching Layer](#10-high-performance-redis-caching-layer)
   - [11. Interactive Client API & Persona Quiz](#11-interactive-client-api--persona-quiz)
6. [Data Model & Relational Schema (35+ Dimensions)](#-data-model--relational-schema-35-dimensions)
7. [Repository Layout](#-repository-layout)
8. [Local Developer Setup & Verification](#-local-developer-setup--verification)
9. [Automated Testing Strategy & Zero-DB-Pollution Guarantee](#-automated-testing-strategy--zero-db-pollution-guarantee)
10. [Roadmap & Milestones](#-roadmap--milestones)

---

## 🌍 Executive Summary & Problem Statement

Buying a laptop in Egypt is historically frustrating due to three structural market anomalies:

1. **Extreme Currency Volatility & Price Fluctuations**: Due to shifting foreign exchange rates, local prices in Egyptian Pounds (EGP) swing violently across weeks. A deal today can be obsolete tomorrow.
2. **Chaotic, Bilingual, & Inconsistent Retail Listings**: Local retail listings (Compumarts, Sigma, 2B, El Badr, Technology Valley) blend Arabic and English, mix Western and Eastern Arabic numerals (`١٢٣`), bury critical details in marketing fluff (*"Special Gaming Offer"*, *"Best Seller"*), or misuse placeholder prices (e.g., listing laptops for `1.00 EGP` or `0.00 EGP` for out-of-stock / "call for price" items).
3. **Spec Sheet Ambiguity & The "Paper Spec" Trap**: Retail listings frequently advertise generic model families (e.g., *"Lenovo LOQ 15"*) while completely omitting critical performance differentiators: GPU TDP/TGP limits, soldered vs expandable RAM slots, 45% NTSC vs 100% sRGB screen gamuts, or battery capacities. Worse, pure spec sheets do not capture **real-world thermals, fan noise, hinge fragility, or chassis flex**.

### The Solution
This platform automates the end-to-end intelligence cycle:
- **Harvests** live catalog data from official brand stores and major Egyptian tech retailers.
- **Enriches & Standardizes** raw listings using Icecat product datasheets and fallback OCR on promotional spec card graphics.
- **Normalizes** hardware into 35+ relational dimensions and 11 mathematical criteria scores.
- **Syncs** price adjustments asynchronously via RabbitMQ with a rock-solid Transactional Outbox pattern.
- **Evaluates** options through a dynamic, persona-weighted TOPSIS multi-criteria decision engine.
- **Augments** technical scores with Aspect-Based Sentiment Analysis (ABSA) extracted from YouTube video reviews, editorial verdicts (LaptopMag), and enthusiast technical communities (Level1Techs, Arabhardware, Reddit).
- **Delivers** sub-50ms query responses through a distributed Redis caching layer.

---

## 🏗️ High-Level End-to-End System Architecture

```mermaid
flowchart TD
    subgraph S1 ["1. Data Acquisition & Enrichment (scraper-service)"]
        direction TB
        BP["Brand Portals<br/>(ASUS, Lenovo, HP, Dell)"] --> SE["Scrapling Stealth Engine<br/>(Playwright / Chromium / TLS)"]
        ER["Egyptian Retailers<br/>(Compumarts, Sigma, 2B, El Badr)"] --> SE
        SE --> L1["Level 1 Discovery<br/>(Reverse Watermark Cursor)"]
        L1 --> L2["Level 2 Deep Spec Scraping<br/>(HTML to Markdown Tables)"]
        L2 --> IC["Icecat Specification Ingestion<br/>(Global MPN / EAN API)"]
        IC --> OCR["Tesseract OCR Fallback<br/>(Spec Cards & Poster Images)"]
        OCR --> JSON_OUT["Clean Unified Catalog Artifact<br/>(unified_catalog_latest.json)"]
    end

    subgraph S2 ["2. Event Bus & Messaging Broker (RabbitMQ)"]
        direction TB
        EX_SYNC["catalog.exchange.sync<br/>(Direct Price Exchange)"]
        Q_PRICE["catalog.queue.price_updates"]
        EX_REV["catalog.exchange.reviews<br/>(Direct Reviews Exchange)"]
        Q_SCRAPE["catalog.queue.scrape_reviews"]
        Q_READY["catalog.queue.reviews_ready"]
        EX_DLX["catalog.exchange.dlx<br/>(Dead Letter Exchange)"]
        Q_DLQ["catalog.queue.dead_letter"]
        
        EX_SYNC --> Q_PRICE
        EX_REV --> Q_SCRAPE
        EX_REV --> Q_READY
        Q_PRICE -.->|Max Retries Exceeded| EX_DLX
        Q_SCRAPE -.->|Max Retries Exceeded| EX_DLX
        EX_DLX --> Q_DLQ
    end

    subgraph S3 ["3. Catalog Core & Persistence (catalog-service)"]
        direction TB
        ING_SRV["Catalog Ingestion Service<br/>(S3 / File Seeder)"]
        HW_ENG["Hardware Metrics Engine<br/>(11 Criteria Normalization)"]
        CHASSIS_RES["Chassis Target Resolver<br/>(Modal Screen Size & Identity)"]
        
        subgraph DB ["PostgreSQL 16 Relational Engine"]
            CONF[("laptop_configuration<br/>(35+ Dimensions)")]
            OFFER[("laptop_offer<br/>(Multi-Store Pricing)")]
            METRICS[("laptop_metrics<br/>(TOPSIS Input Scores)")]
            OUTBOX[("outbox_message<br/>(Transactional Outbox)")]
            BATCH[("scraping_batch_log")]
        end
        
        PRICE_SYNC["PriceSyncService<br/>(Pure Domain Transitions)"]
        OUTBOX_WORKER["Transactional Outbox Publisher<br/>(At-Least-Once Delivery)"]
    end

    subgraph S4 ["4. Review Intelligence Pipeline (scraper-service)"]
        direction TB
        COLL_SRV["CommunitiesReviewsCollector<br/>(Multi-Platform Orchestration)"]
        YT_CRAWL["YouTube Scraper<br/>(yt-dlp Transcripts & Comments)"]
        MAG_CRAWL["LaptopMag Scraper<br/>(Editorial Pros/Cons/Verdict)"]
        L1_CRAWL["Level1Techs Scraper<br/>(Discourse 3-Layer Gated REST API)"]
        AH_CRAWL["Arabhardware Scraper<br/>(Egyptian Regional Market Data)"]
        RED_CRAWL["Reddit Scraper<br/>(Injectable Fallback Strategy)"]
        S3_STORAGE[("S3 / Local Claim Check<br/>raw_chassis_reviews_{job_id}.json")]
        
        COLL_SRV --> YT_CRAWL
        COLL_SRV --> MAG_CRAWL
        COLL_SRV --> L1_CRAWL
        COLL_SRV --> AH_CRAWL
        COLL_SRV --> RED_CRAWL
        COLL_SRV --> S3_STORAGE
    end

    subgraph S5 ["5. Recommender & NLP Engine (catalog-service / NLP)"]
        direction TB
        ABSA_MODEL["Aspect-Based Sentiment (ABSA)<br/>(Thermals, Fan Noise, Hinges, Battery)"]
        SENT_SCORES[("laptop_sentiment_scores<br/>(Dimension Penalties & Boosts)")]
        REDIS[("Redis In-Memory Cache<br/>(TOPSIS Matrix, Laptops, Sessions)")]
        TOPSIS["Dynamic TOPSIS Engine<br/>(In-Memory Persona Multi-Criteria MCDM)"]
        API["FastAPI Presentation Gateway<br/>(Interactive Quiz, Comparison Matrix)"]
        
        ABSA_MODEL --> SENT_SCORES
    end

    JSON_OUT --> ING_SRV
    ING_SRV --> HW_ENG
    ING_SRV --> CHASSIS_RES
    CHASSIS_RES --> DB
    HW_ENG --> DB
    
    PRICE_SYNC --> DB
    DB --> OUTBOX_WORKER
    OUTBOX_WORKER --> EX_SYNC
    OUTBOX_WORKER --> EX_REV
    Q_PRICE --> PRICE_SYNC
    Q_SCRAPE --> COLL_SRV
    COLL_SRV --> EX_REV
    Q_READY --> ABSA_MODEL
    
    METRICS --> TOPSIS
    SENT_SCORES --> TOPSIS
    TOPSIS <--> REDIS
    API <--> REDIS
    API --> TOPSIS
```

---

## 🏛️ Core Engineering Philosophies

### Clean Architecture & Layered Separation
Every backend service strictly enforces the **Three-Tier Onion Architecture**:

```
┌────────────────────────────────────────────────────────┐
│                   Presentation Layer                   │
│   FastAPI Endpoints, Pydantic V2 Schemas, CLI Runners  │
└──────────────────────────┬─────────────────────────────┘
                           │ Injects
┌──────────────────────────▼─────────────────────────────┐
│                 Application / Use Cases                │
│ CatalogIngestionService, PriceSyncService, Consumers  │
└──────────────────────────┬─────────────────────────────┘
                           │ Coordinates
┌──────────────────────────▼─────────────────────────────┐
│                   Domain Layer (Pure)                  │
│  PricingDomainService, Scoring Math, Transition Events │
│  * ZERO DB imports * ZERO async I/O * 100% Unit Tested │
└──────────────────────────┬─────────────────────────────┘
                           │ Inverted Dependency
┌──────────────────────────▼─────────────────────────────┐
│              Repository & Infrastructure               │
│  SQLAlchemy 2.0 ORM, Postgres Repositories, RabbitMQ   │
└────────────────────────────────────────────────────────┘
```

1. **Domain Layer (`app/domain/`)**: Pure business rules and mathematical formulas (e.g., offer state transitions, hardware tiering, TOPSIS vector normalization). Contains **zero** database imports (no SQLAlchemy, asyncpg), **zero** web framework imports (no FastAPI), and **zero** network clients. Testable in microseconds.
2. **Repository Layer (`app/repositories/`)**: Encapsulates SQL queries and data access logic (`LaptopRepository`, `OfferRepository`, `OutboxRepository`). Controllers and application services never execute inline SQL statements (`session.execute("SELECT...")` is forbidden outside repositories).
3. **Application Layer (`app/services/`, `app/jobs/`)**: Orchestrates workflows by combining domain policies with repository outputs, managing database transactions, and publishing outbox events.

### SOLID Principles Compliance
- **Single Responsibility (SRP)**: Data ingestion, price reconciliation, hardware scoring, and API serialization are decoupled into dedicated classes.
- **Open/Closed (OCP)**: New store scrapers, persona weighting profiles, or scoring criteria are added via interfaces without modifying existing core logic.
- **Liskov Substitution (LSP)**: All store scrapers and database repositories strictly honor base abstract contracts.
- **Interface Segregation (ISP)**: Clients depend solely on the granular repository methods they call.
- **Dependency Inversion (DIP)**: High-level business logic depends on abstract interfaces; concrete database sessions and network adapters are injected.

### Transactional Outbox Pattern & Event-Driven Reliability
In a microservices setup, updating a database and publishing a message to a broker in two separate operations introduces dual-write hazards. If the broker is unreachable, data desynchronizes.
We solve this with the **Transactional Outbox Pattern**:

```mermaid
sequenceDiagram
    participant S as PriceSyncService
    participant DB as PostgreSQL Transaction
    participant OB as Outbox Repository
    participant W as Outbox Worker Task
    participant RMQ as RabbitMQ Exchange

    S->>DB: 1. Begin Atomic Transaction
    S->>DB: 2. Update laptop_offer & laptop_configuration
    S->>OB: 3. Insert OutboxMessage (status=PENDING)
    S->>DB: 4. Commit Transaction (Atomic State + Event Persisted)
    
    W->>OB: 5. Fetch PENDING outbox messages (with row lock)
    W->>RMQ: 6. Publish message with publisher confirms
    RMQ-->>W: 7. Broker Ack
    W->>OB: 8. Mark OutboxMessage as PUBLISHED
```

- **Guarantees**: At-least-once message delivery, zero phantom updates, and zero lost price drop notifications.
- **Dead-Letter Handling**: If consumers fail processing repeatedly, messages route to `catalog.exchange.dlx` and wait in `catalog.queue.dead_letter` for operator inspection.

### Idempotent Seeding & Reverse Watermark Polling
- **Incremental Crawling**: Instead of brute-force scraping thousands of pages on every run, the scraper reads the `latest_pointers` watermark from `store_scraping_pointer`. The scraper crawls newest-first and halts immediately upon encountering the watermark.
- **Consolidation & Deduplication**: Multiple retail URLs for the same physical laptop configuration are unified under a single canonical identity via Manufacturer Part Number (MPN) and hardware fingerprint matching.

---

## 🛠️ Implemented Subsystems (Phase 1 & Phase 2)

### 1. Data Acquisition Engine (`scraper-service`)
- **Anti-Bot Defense**: Utilizes `ScraplingEngine` and `StealthyFetcher` (Patchright / Playwright Chromium engine) with randomized viewport geometry, user-agent rotation, and Chrome TLS fingerprint impersonation (`curl_cffi`) to bypass Cloudflare and perimeter firewalls.
- **Two-Level Brand Ingestion**:
  - *Level 1 (Discovery)*: Fast scan of catalog grids sorted by newest first, capturing base titles, family codes, and product URLs.
  - *Level 2 (Deep Spec Crawl)*: Traverses `/techspec/` endpoints, converts nested HTML tables into clean Markdown tables via `markdownify`, and parses exact hardware parameters into strongly-typed Pydantic v2 schemas.
- **Multi-Store Crawlers**:
  - **Compumarts Egypt**: Search query and HTML card parsing.
  - **Sigma Computer**: High-throughput product grid crawler.
  - **2B Egypt**: Bilingual Arabic/English catalog crawler with automatic Eastern Arabic numeral conversion.
  - **El Badr Group**: Multi-category gaming and business crawler with out-of-stock and placeholder price detection.

### 2. Global Specification & OCR Pipeline (Icecat & Tesseract)
Many retail stores in Egypt do not list structured specs in their HTML; instead, they embed spec sheets into **promotional images** or provide an ambiguous one-line description.
- **Icecat Open Catalog Integration**: Uses the official Icecat XML/JSON Open Catalog API to look up laptops by MPN (Manufacturer Part Number) and EAN/UPC barcodes, pulling laboratory-grade component specs directly from the manufacturer.
- **OCR Fallback Engine**: When Icecat lacks data and the store provides an image-only spec sheet, the scraper runs **Tesseract OCR with OpenCV pre-processing** (grayscale conversion, Otsu thresholding, noise reduction) to transcribe spec text directly from poster graphics into structured JSON.

### 3. Relational Catalog Core (`catalog-service`)
- **Technology Stack**: Python 3.11+, FastAPI, SQLAlchemy 2.0 (fully typed `Mapped` async annotations), PostgreSQL 16+, Alembic migrations, Pydantic v2.
- **Canonical Architecture**:
  - `laptop_configuration`: The single source of truth for physical hardware configurations.
  - `laptop_offer`: Many-to-one relationship tracking every store listing, URL, availability, stock, and live price in EGP.
  - `laptop_metrics`: 1:1 hardware performance criteria matrix serving as input to the recommendation engine.
  - `scraping_batch_log`: Audit trail recording execution times, items ingested, and failure logs.
  - `store_scraping_pointer`: Watermark cursors for incremental scraping.

### 4. Hardware Metrics Engine (11 TOPSIS Criteria)
Every canonical laptop configuration is ingested through our pure mathematical engine to produce normalized baseline scores across 11 key performance dimensions:

| Criterion | Code Key | Formula / Inputs | Goal |
| :--- | :--- | :--- | :--- |
| **CPU Performance** | `cpu_perf_score` | Weighted composite of Single-Thread & Multi-Thread benchmarks, Core count, Architecture generation | Maximize |
| **GPU Performance** | `gpu_perf_score` | 3DMark TimeSpy / FireStrike scores, VRAM capacity, TGP/TDP limits | Maximize |
| **RAM Capability** | `ram_score` | Capacity (GB), DDR generation speed (MHz), Dual-channel bandwidth, Upgradeable slot allowance | Maximize |
| **Storage Speed & Space** | `storage_score` | Capacity (GB), NVMe PCIe Gen (Gen 3 vs 4 vs 5), Secondary M.2 slot availability | Maximize |
| **Display Quality** | `display_score` | Resolution, Panel type (OLED > IPS > TN), Refresh rate (Hz), Brightness (Nits), Color gamut (% sRGB / DCI-P3) | Maximize |
| **Battery Life & Efficiency** | `battery_score` | Battery capacity (Wh), CPU TDP class (U-series vs H-series), Fast-charging, USB-C PD support | Maximize |
| **Portability** | `portability_score` | Inverse weight (kg), Chassis thickness (mm), Charger wattage size | Maximize |
| **Connectivity & I/O** | `connectivity_score` | Thunderbolt 4 / USB4, HDMI 2.1, Wi-Fi 6E/7, SD Card reader, Ethernet RJ-45 | Maximize |
| **Build & Security** | `build_score` | Chassis materials (Aluminum vs Plastic), MIL-STD-810H durability, Fingerprint, IR Windows Hello, Backlit keyboard | Maximize |
| **Composite Hardware** | `composite_hw_score` | Harmonic mean of CPU, GPU, Display, RAM, and Storage scores | Maximize |
| **Value for Money** | `value_score` | $\frac{\text{Composite Hardware Score}}{\text{Effective Price (EGP)}} \times 100,000$ | Maximize |

### 5. Domain Pricing Engine & Corrupted Price Defense
Retail scrapers frequently ingest bad data (promotional teasers, missing digits, or stores using `1.00 EGP` to represent "Call for Price"). The pure domain service (`PricingDomainService`) guards catalog integrity:
- **Corrupted Price Threshold**: Any price $< 5,000\text{ EGP}$ is classified as an invalid placeholder and flagged (`is_valid_price = False`).
- **Aggregated Rollup Calculation**:
  - `min_price_egp`: The lowest price among *valid, in-stock* offers.
  - `max_price_egp`: The highest price among valid offers.
  - `cheapest_store`: Automatically identifies which store currently holds the lowest price.
  - `price_spread_egp`: Quantifies market price divergence ($\text{max} - \text{min}$).
- **Transition Evaluator**: Classifies price changes into explicit domain events: `PRICE_DROP`, `PRICE_HIKE`, `OUT_OF_STOCK`, `RESTOCKED`, or `UNCHANGED`.

### 6. Asynchronous Event-Driven Price Synchronization
- **RabbitMQ Pipeline**: The ingestion service pushes price batches to `catalog.exchange.sync`.
- **`CatalogMessageConsumer`**: Listens asynchronously, executes batch price synchronization inside an atomic PostgreSQL transaction, updates the configuration rollup, and recalculates the laptop's `value_score` in real time.

### 7. Review Intelligence Pipeline & Multi-Platform Mining
Spec sheets only tell half the story. A laptop might boast an RTX 4070 and an i9 CPU on paper, but suffer from thermal throttling that drops performance by 40%, loud coil whine, or fragile plastic hinges that snap after six months.

To uncover real-world ground truth, the platform incorporates an autonomous **Multi-Platform Review Intelligence Pipeline** spanning video reviews, editorial verdicts, and enthusiast community forums:

```mermaid
flowchart LR
    subgraph CatalogService ["catalog-service (Trigger & Resolution)"]
        INGEST["Catalog Ingestion Service"]
        CHASSIS["ChassisTargetResolver<br/>(Modal Screen Size & Identity)"]
        OUTBOX["Transactional Outbox<br/>ScrapeReviewsCommand"]
    end

    subgraph MessagingBroker ["RabbitMQ Broker"]
        EX_REV["catalog.exchange.reviews<br/>(Direct Reviews Exchange)"]
        Q_CMD["catalog.queue.scrape_reviews"]
        Q_RDY["catalog.queue.reviews_ready"]
    end

    subgraph ScraperService ["scraper-service (Mining Engine)"]
        COLLECTOR["CommunitiesReviewsCollector<br/>(Multi-Platform Orchestration)"]
        YT["YouTube Scraper<br/>(yt-dlp Transcripts & Comments)"]
        MAG["LaptopMag Scraper<br/>(Editorial Pros/Cons/Verdict)"]
        L1["Level1Techs Scraper<br/>(Discourse 3-Layer Gated REST API)"]
        AH["Arabhardware Scraper<br/>(Egyptian Regional Coverage)"]
        RED["Reddit Scraper<br/>(Injectable Fallback Strategy)"]
    end

    subgraph ClaimCheck ["Object Storage (Claim-Check Pattern)"]
        S3_JSON[("S3 / Local JSON Artifact<br/>raw_chassis_reviews_{job_id}.json")]
    end

    subgraph DownstreamNLP ["Catalog Core / NLP Worker"]
        ABSA["DeBERTa-v3 ABSA Model<br/>(Aspect-Based Sentiment)"]
        SENT_MOD[("Sentiment Penalties & Multipliers<br/>in TOPSIS Decision Matrix")]
    end

    INGEST --> CHASSIS --> OUTBOX
    OUTBOX --> EX_REV --> Q_CMD
    Q_CMD --> COLLECTOR
    COLLECTOR --> YT
    COLLECTOR --> MAG
    COLLECTOR --> L1
    COLLECTOR --> AH
    COLLECTOR --> RED
    COLLECTOR --> S3_JSON
    COLLECTOR --> EX_REV --> Q_RDY
    Q_RDY --> ABSA
    ABSA --> SENT_MOD
```

#### Key Architecture & Capabilities
1. **Chassis Target Resolution (`ChassisTargetResolver`)**:
   - Hardware configurations are clustered by physical chassis family: `(brand, laptop_family, modal screen_size, cpu_line, gpu_model)`.
   - Different configurations of the same chassis (e.g. 16GB RAM vs 32GB RAM, 512GB vs 1TB SSD) share the identical cooling assembly, thermal dissipation limits, keyboard travel, screen chassis, and hinge rigidity. Clustered review targets avoid redundant network crawls.
   - **Modal Screen Size Resolution**: Deterministically resolves the modal display size across family members (e.g., resolving `15.6"` across configurations, tie-breaking deterministically to first-seen).
   - **Integer Floor Tokenization**: Floor truncation converts float display sizes into standard commercial chassis family tokens (`int(screen_size)` so `15.6"` -> `15`, `17.3"` -> `17`), matching real-world review titles (e.g., `"Lenovo LOQ 15 review"` instead of false-positive `"LOQ 16"` queries).
2. **Asynchronous Command & Event Orchestration (RabbitMQ & Transactional Outbox)**:
   - When new configurations are ingested, `catalog-service` publishes a `ScrapeReviewsCommand` payload via the Transactional Outbox pattern into `catalog.exchange.reviews` bound to `catalog.queue.scrape_reviews`.
   - Dedicated dead-letter routing (`catalog.exchange.dlx` / `catalog.queue.dead_letter`) ensures fault tolerance and dead-lettering if workers exceed retry limits.
   - Upon completing multi-platform scraping, `scraper-service` emits a `ReviewsReadyEvent` to `catalog.queue.reviews_ready` for downstream processing.
3. **S3 Claim-Check Storage Architecture (`RawChassisReviewsPayload`)**:
   - Long-form video transcripts and multi-threaded discussion posts easily exceed standard message broker payload limits (128 KB - 1 MB).
   - Review payloads are saved via the **Claim Check Pattern** to Amazon S3 (or local disk in development environments) under `reviews/{job_id}/raw_chassis_reviews_{job_id}.json`.
   - `reviews_s3.py` maintains **100% byte-for-byte schema lockstep** between `catalog-service` and `scraper-service` via Pydantic v2 validation.
4. **Multi-Platform Scraper Engine**:
   - **YouTube Review Scraper**: Crawls top video reviews using `yt-dlp` and `youtube-transcript-api` for English and Arabic transcripts with timestamps, plus top-ranked viewer comments.
   - **LaptopMag Platform Scraper**: Parses structured editorial reviews extracting rating scores, summary verdicts, `.reasons-to-buy` (pros), and `.reasons-to-avoid` (cons).
   - **Level1Techs Platform Scraper**: High-signal enthusiast discussions queried via Discourse REST JSON API with a strict 3-layer relevance gate (title match, brand/family verification, query hit).
   - **Arabhardware Platform Scraper**: Harvests local Egyptian tech community reviews, regional Arabic feedback, and local market context.
   - **Reddit Platform Scraper (Fallback Strategy)**: Preserves targeted querying for `r/SuggestALaptop` and `r/GamingLaptops` with a 4-layer keyword gate, fully preserved for future authenticated OAuth2 deployments.
   - **Fail-Open HTTP Architecture**: Injected `httpx.AsyncClient` context with resilient error handling ensures network anomalies or rate-limits on a single source never disrupt collection from remaining platforms.
   - **Deduplication & Hygiene**: Automatic URL normalization, `(platform, post_id)` deduplication, and deal/sales filtering.

---

## 🔮 Upcoming & In-Flight Subsystems (Phase 3)

### 8. Dynamic TOPSIS Recommendation Engine
Instead of arbitrary hardcoded rules, recommendations are powered by **TOPSIS** (*Technique for Order of Preference by Similarity to Ideal Solution*), a proven Multi-Criteria Decision-Making (MCDM) algorithm.

#### Mathematical Foundation
1. **Decision Matrix Construction**: An $m \times n$ matrix where $m$ is the number of laptops and $n$ is the 11 hardware/sentiment evaluation criteria:
   $$X = [x_{ij}]_{m \times n}$$

2. **Vector Normalization**:
   $$r_{ij} = \frac{x_{ij}}{\sqrt{\sum_{k=1}^{m} x_{kj}^2}}$$

3. **Weighted Normalized Decision Matrix**:
   $$v_{ij} = w_j \cdot r_{ij} \quad \text{where} \quad \sum_{j=1}^{n} w_j = 1$$
   *Weights ($w_j$) are dynamically assigned based on the user's selected persona.*

4. **Identify Positive Ideal ($A^+$) and Negative Ideal ($A^-$) Solutions**:
   $$A^+ = \{ \max_i(v_{ij}) \mid j \in J_{\text{benefit}} \}, \quad A^- = \{ \min_i(v_{ij}) \mid j \in J_{\text{benefit}} \}$$

5. **Calculate Euclidean Separation Distances**:
   $$S_i^+ = \sqrt{\sum_{j=1}^{n} (v_{ij} - v_j^+)^2}, \quad S_i^- = \sqrt{\sum_{j=1}^{n} (v_{ij} - v_j^-)^2}$$

6. **Relative Closeness to the Ideal Solution ($C_i^*$)**:
   $$C_i^* = \frac{S_i^-}{S_i^+ + S_i^-} \quad (0 \le C_i^* \le 1)$$
   *Laptops are ranked in descending order of $C_i^*$.*

#### Why TOPSIS Results Are Computed Dynamically In-Memory
A key architectural design decision was **not storing final TOPSIS ranking results in PostgreSQL tables**:
- **Zero Stale Locks**: User preferences, budgets, and criteria weights change continuously.
- **Personalized Weights**: A Gamer prioritizes GPU and Refresh Rate; a Software Engineer prioritizes CPU Multi-Thread and RAM; a College Student prioritizes Battery and Value.
- **Ultra-Fast Computation**: Because the 11 input criteria are pre-normalized in `laptop_metrics`, calculating $C_i^*$ across 500 laptops using NumPy takes **under 4 milliseconds in memory**.

#### Pre-Configured Personas

```
┌────────────────────────────────────────────────────────────────────────┐
│                        User Persona Profiles                           │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Competitive Gamer    │ GPU (30%), Display 144Hz+ (25%), CPU (20%),     │
│                      │ Thermals (15%), Portability (10%)               │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Software / AI Dev    │ CPU Multi-Thread (30%), RAM (25%),              │
│                      │ Storage (20%), Display (15%), Battery (10%)     │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Content Creator      │ Display DCI-P3/OLED (30%), GPU (25%),           │
│                      │ Storage Speed (20%), CPU (15%), I/O Ports (10%) │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Business / Travel    │ Battery Life (35%), Portability/Weight (30%),   │
│                      │ Build Quality (20%), Connectivity (15%)         │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Budget Student       │ Value for Money (40%), Battery (25%),           │
│                      │ CPU (20%), Portability (15%)                    │
└──────────────────────┴─────────────────────────────────────────────────┘
```

---

### 9. Aspect-Based Sentiment Analysis (ABSA) & Downstream NLP
Using the rich transcripts and editorial feedback harvested in Phase 2, the downstream NLP worker parses unstructured sentiment into quantitative penalties and multipliers:
- **Aspect Extraction**:
  - `Thermals & Throttling`: Quantifies complaints regarding surface temperature, cooling failure, and thermal throttling under gaming/compilation loads.
  - `Acoustics / Fan Whine`: Detects user dissatisfaction with aggressive fan curves and high-pitch coil whine.
  - `Chassis & Hinge Durability`: Flags notorious hinge cracking, deck flex, and plastic breakage.
  - `Real Battery vs Claimed`: Measures the delta between manufacturer-advertised battery life and real-world reviewer benchmarks.
- **Sentiment-Adjusted TOPSIS Modifiers**: Sentiment scores feed directly into the TOPSIS decision matrix as penalties or multipliers, ensuring laptops with notorious hardware flaws drop in ranking regardless of their paper specs.

---

### 10. High-Performance Redis Caching Layer
To support high-concurrency client requests and sub-second recommendation generation, **Redis** is introduced across two tiers:

```
                                  Client Request
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │   FastAPI Gateway Router    │
                         └──────────────┬──────────────┘
                                        │
                       Check Cache Key  │
                                        ▼
                         ┌─────────────────────────────┐
                 Yes ─── │      Redis Cache Hit?       │
                │        └──────────────┬──────────────┘
                │                       │ No
                ▼                       ▼
    ┌───────────────────────┐ ┌───────────────────────────────────┐
    │  Return Cached JSON   │ │ Run Dynamic TOPSIS in Memory      │
    │  (< 5ms Response)     │ │ Fetch from PostgreSQL via Repos   │
    └───────────────────────┘ └─────────────────┬─────────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ Cache Result in Redis     │
                                  │ (TTL: 15-60 min)          │
                                  └───────────────────────────┘
```

- **L1 Catalog Cache**: Caches serialized canonical laptop detail payloads (`GET /catalog/laptops/{canonical_id}`) and full catalog listings (`GET /catalog/laptops`).
- **L2 Recommendation Matrix Cache**: Caches the normalized $m \times n$ TOPSIS decision matrix in Redis memory. When a user requests recommendations with custom weights, the engine pulls the pre-normalized matrix directly from Redis, executes vector multiplication, and returns results in **$< 15\text{ms}$**.
- **Event-Driven Cache Invalidation**: When `PriceSyncService` processes a price change or an item goes out of stock, it publishes a domain event that automatically invalidates the affected Redis keys via a lightweight cache-invalidation consumer.
- **Distributed Session State**: Stores user quiz progress, comparison trays (up to 4 laptops compared side-by-side), and user filter preferences.

---

### 11. Interactive Client API & Persona Quiz
The upcoming presentation layer exposed via FastAPI will feature:
- **Interactive Quiz Endpoint (`POST /api/v1/recommendations/quiz`)**: A simple 5-question questionnaire (budget range in EGP, primary use-case, portability importance, preferred brands, required battery life) that dynamically translates answers into TOPSIS weights.
- **Side-by-Side Comparison Matrix (`GET /api/v1/catalog/compare?ids=...`)**: Detailed hardware diffing across 35+ dimensions, highlighting advantages, price spread between stores, and review pros/cons.
- **Price History & Deal Tracker (`GET /api/v1/catalog/laptops/{id}/price-history`)**: Historical pricing trends tracking inflation, discounts, and best times to buy.

---

## 📊 Data Model & Relational Schema (35+ Dimensions)

The relational catalog in PostgreSQL is built on fully typed SQLAlchemy 2.0 ORM models:

```mermaid
erDiagram
    laptop_configuration ||--o{ laptop_offer : "has many store offers"
    laptop_configuration ||--|| laptop_metrics : "has 1:1 criteria scores"
    scraping_batch_log ||--o{ outbox_message : "emits"

    laptop_configuration {
        uuid id PK
        string canonical_id UK "Unique hardware fingerprint"
        string mpn "Manufacturer Part Number"
        string brand "ASUS, Lenovo, Dell, HP, Acer, etc."
        string laptop_family "ROG, Vivobook, Legion, etc."
        string laptop_model "Specific sub-model name"
        string title "Normalized presentation title"
        
        string cpu_manufacturer "Intel, AMD, Apple, Qualcomm"
        string cpu_line "Core i7, Core Ultra 7, Ryzen 7"
        string cpu_model "14700HX, 155H, 7840HS"
        int cpu_cores "Physical cores"
        int cpu_threads "Logical threads"
        float cpu_base_clock_ghz
        float cpu_boost_clock_ghz
        float cpu_npu_tops "AI computing performance"
        
        string gpu_manufacturer "NVIDIA, AMD, Intel"
        string gpu_model "RTX 4060, Radeon 780M, etc."
        int gpu_vram_gb
        int gpu_tdp_w "TGP power allowance in watts"
        boolean gpu_integrated
        
        int ram_capacity_gb
        string ram_type "DDR4, DDR5, LPDDR5X"
        int ram_speed_mhz
        int ram_slot_count "Total slots"
        int ram_max_supported_gb
        boolean ram_is_soldered
        
        int storage_capacity_gb
        string storage_type "SSD, NVMe, HDD"
        string storage_interface "PCIe 4.0 x4, PCIe 5.0"
        int storage_slot_count
        
        float display_size_inches
        string display_resolution "1920x1080, 2560x1600"
        int display_refresh_rate_hz
        string display_panel_type "IPS, OLED, Mini-LED"
        int display_brightness_nits
        string display_color_gamut "100% sRGB, 100% DCI-P3"
        boolean display_touchscreen
        
        float battery_capacity_wh
        float power_adapter_w
        float weight_kg
        float thickness_mm
        
        boolean has_backlit_keyboard
        boolean has_fingerprint
        string webcam_resolution
        string operating_system
        jsonb ports "Full I/O port breakdown"
        
        decimal min_price_egp "Lowest live market price"
        decimal max_price_egp "Highest live market price"
        string cheapest_store "Store offering lowest price"
        boolean in_stock
    }

    laptop_offer {
        uuid id PK
        uuid laptop_configuration_id FK
        string store_key "compumarts, sigma, twob, elbadr"
        string store_name
        string product_url
        decimal price_egp
        decimal previous_price_egp
        boolean in_stock
        boolean is_valid_price
        timestamp price_updated_at
        timestamp last_checked_at
    }

    laptop_metrics {
        uuid id PK
        uuid laptop_id FK "1:1 unique relation to configuration"
        float cpu_perf_score "0-100 normalized"
        float gpu_perf_score "0-100 normalized"
        float ram_score "0-100 normalized"
        float storage_score "0-100 normalized"
        float display_score "0-100 normalized"
        float battery_score "0-100 normalized"
        float portability_score "0-100 normalized"
        float connectivity_score "0-100 normalized"
        float build_score "0-100 normalized"
        float composite_hw_score "Composite overall score"
        float value_score "Hardware / EGP ratio"
        float effective_price_egp
    }

    scraping_batch_log {
        uuid id PK
        string batch_id UK
        string status "COMPLETED, FAILED"
        int total_items
        timestamp created_at
    }

    outbox_message {
        uuid id PK
        string event_type "PRICE_UPDATE, SCRAPE_REVIEWS"
        string routing_key
        jsonb payload
        string status "PENDING, PUBLISHED, FAILED"
        int retry_count
        timestamp created_at
        timestamp published_at
    }
```

---

## 📁 Repository Layout

```
laptop-recommender/
├── Docs/                                  # Technical specifications & architecture guides
│   ├── ARCHITECTURE.md                    # Detailed microservice design & schemas
│   ├── GETTING_STARTED.md                 # Local environment & toolchain setup
│   ├── BRAND_SCRAPING_GUIDE.md            # Brand scraping guide (Markdown extraction)
│   ├── STORE_SCRAPING_GUIDE.md            # Retailer store crawler schemas
│   └── CATALOG_SPECIFICATIONS_REPORT.md   # Field audit across all 35+ dimensions
├── services/
│   ├── scraper-service/                   # Autonomous Ingestion & Review Mining Engine
│   │   ├── app/
│   │   │   ├── cli.py                     # CLI for Brand & Store scraping
│   │   │   ├── core/                      # Constants, URLs, and token normalizers
│   │   │   ├── domain/                    # PURE DOMAIN LAYER (Zero DB / external dependencies)
│   │   │   │   └── reviews/               # CommunityQuerySet builder & integer floor screen tokens
│   │   │   ├── engine/                    # Scrapling headless browser & HTTP abstraction
│   │   │   ├── enrichment/                # Icecat API client & Tesseract OCR fallback
│   │   │   ├── schemas/                   # Pydantic v2 schemas (Catalog, Events, S3 Reviews)
│   │   │   │   ├── events.py              # Review & Price sync AMQP events
│   │   │   │   └── reviews_s3.py          # Byte-identical S3 Claim-Check schema
│   │   │   ├── scrapers/                  # Brand scrapers (ASUS, Lenovo, Dell, HP)
│   │   │   ├── services/                  # Review Mining & Extraction Services
│   │   │   │   └── reviews/
│   │   │   │       ├── youtube/           # YouTube scraper (yt-dlp, transcripts, comments)
│   │   │   │       └── community/         # CommunitiesReviewsCollector, LaptopMag, Level1Techs, Arabhardware, Reddit
│   │   │   └── stores/                    # Store scrapers (Compumarts, Sigma, 2B, El Badr)
│   │   ├── tests/                         # Scraper & Review Test Suite (604 tests)
│   │   ├── requirements.txt               # Scraper dependencies
│   │   └── README.md                      # Scraper-specific documentation
│   │
│   └── catalog-service/                   # Relational Core, Messaging & Recommender
│       ├── alembic/                       # Database schema migrations
│       ├── app/
│       │   ├── api/                       # FastAPI router endpoints (Health, Catalog, Recommendations)
│       │   ├── common/                    # Logging, caching (Redis / Memory), storage & resilience
│       │   ├── core/                      # Settings, PostgreSQL connection engine
│       │   ├── domain/                    # PURE DOMAIN LAYER (Zero external dependencies)
│       │   │   ├── pricing.py             # PricingDomainService, Rollups, Transitions
│       │   │   ├── recommender/           # Dynamic TOPSIS, 7 Personas & Decision Explainer
│       │   │   └── reviews/               # ChassisTargetResolver & modal screen size logic
│       │   ├── messaging/                 # Event-Driven Messaging Layer (RabbitMQ)
│       │   │   ├── config.py              # Exchange, Queue, and Routing Key setup
│       │   │   ├── consumer.py            # Async CatalogMessageConsumer (RabbitMQ)
│       │   │   └── publisher.py           # Transactional Outbox Publisher worker
│       │   ├── models/                    # SQLAlchemy 2.0 ORM Data Models
│       │   │   ├── laptop.py              # LaptopConfiguration (35+ dimensions)
│       │   │   ├── offer.py               # LaptopOffer (Store pricing & availability)
│       │   │   ├── metrics.py             # LaptopMetrics (11 TOPSIS criteria)
│       │   │   ├── outbox.py              # OutboxMessage (Transactional Outbox)
│       │   │   └── scraping.py            # ScrapingBatchLog & StoreScrapingPointer
│       │   ├── repositories/              # Repository Layer (Data Access Isolation)
│       │   │   ├── laptop_repository.py   # Catalog queries
│       │   │   ├── offer_repository.py    # Store offers queries
│       │   │   ├── outbox_repository.py   # Atomic outbox message persistence
│       │   │   ├── seeder.py              # Bulk upserting & entity resolution
│       │   │   └── pointer_repository.py  # Watermark pointers
│       │   ├── schemas/                   # Pydantic v2 schemas (Events, S3 Claim Check)
│       │   │   ├── events.py              # Review & Price sync AMQP events
│       │   │   └── reviews_s3.py          # Byte-identical S3 Claim-Check schema
│       │   ├── services/                  # Application Layer (Use Cases)
│       │   │   ├── catalog_ingestion_service.py # Ingestion & Chassis resolution orchestrator
│       │   │   ├── hardware_metrics_service.py  # 11 Criteria normalizer
│       │   │   ├── price_sync_service.py        # Price reconciliation & outbox
│       │   │   └── recommendation_service.py    # In-memory TOPSIS evaluation & Redis caching
│       │   └── main.py                    # FastAPI application initialization
│       ├── scripts/                       # CLI operational utilities
│       │   └── run_catalog_seeder.py      # Standalone catalog seeder CLI
│       ├── tests/                         # Test Suite (200 tests, Savepoint isolation)
│       ├── requirements.txt               # Catalog dependencies
│       └── README.md                      # Catalog-specific documentation
└── README.md                              # Master Project Documentation (This File)
```

---

## ⚡ Local Developer Setup & Verification

### 1. Prerequisites
- **Python 3.11+ (64-bit)**
- **PostgreSQL 16+** (Local service or Docker)
- **RabbitMQ 3.12+** (with management plugin enabled)
- **Redis 7+** (Optional for Phase 1, required for Phase 2 caching)
- **Tesseract-OCR** (Optional, required for OCR spec card extraction)

---

### 2. Setting Up `catalog-service`
In your terminal:

```powershell
cd "services/catalog-service"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env to set your PostgreSQL and RabbitMQ credentials:
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/laptop_recommender_catalog
# RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Apply database migrations
alembic upgrade head

# Ingest initial clean catalog seed (294 canonical laptops, 372 offers)
python scripts/run_catalog_seeder.py --file "scraping input/unified_catalog_latest.json"

# Launch the FastAPI development server
uvicorn app.main:app --reload --port 8000
```
Interactive Swagger API documentation is available at `http://localhost:8000/docs`.

---

### 3. Setting Up `scraper-service`
In a separate terminal:

```powershell
cd "services/scraper-service"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium

# Test running a brand scraper (Level 1 fast card scan)
python -m app.cli --brand asus --mode brand-only --level 1

# Test running a store scraper (e.g., Compumarts with a 10-item limit)
python -m app.cli --mode store --stores compumarts --limit 10
```

---

## 🧪 Automated Testing Strategy & Zero-DB-Pollution Guarantee

The monorepo contains **804 automated unit and integration tests** (200 in `catalog-service`, 604 in `scraper-service`) verifying Clean Architecture, pricing rollups, outbox publishing, chassis resolution, multi-platform review scrapers, and concurrent RabbitMQ consumers.

### Zero Database Pollution via Transactional Savepoints
To ensure automated test suites never leave test records in local or CI databases:
- `conftest.py` wraps every test in an isolated **PostgreSQL Savepoint** (`join_transaction_mode="create_savepoint"`).
- Tests can insert dummy laptops, offers, and outbox messages freely.
- Upon test completion, the savepoint **rolls back 100% of mutations**, guaranteeing a clean database state after every run.

```powershell
# Run catalog-service test suite (200 tests in ~7s)
cd "services/catalog-service"
pytest tests/ -v

# Run scraper-service test suite (604 tests in ~44s)
cd "services/scraper-service"
pytest tests/ -v
```

---

## 🗺️ Roadmap & Milestones

- [x] **Milestone 1**: Headless stealth scraper with anti-bot evasion (`ScraplingEngine`).
- [x] **Milestone 2**: Reverse Watermark incremental polling pattern (`--until-model`).
- [x] **Milestone 3**: Icecat API datasheet enrichment and OCR spec card fallback.
- [x] **Milestone 4**: PostgreSQL 16 relational catalog with 35+ dimensional specifications.
- [x] **Milestone 5**: Hardware Metrics Engine normalizing 11 TOPSIS criteria.
- [x] **Milestone 6**: Pure Domain Pricing Service with corrupted price defense (handling `1.00 EGP` placeholders).
- [x] **Milestone 7**: RabbitMQ Event-Driven Price Synchronization & Transactional Outbox pattern.
- [x] **Milestone 8**: In-Memory Dynamic TOPSIS Recommendation Engine with 7 Persona Weight Profiles & Decision Explainer.
- [x] **Milestone 9**: Multi-Platform Review Intelligence Pipeline (YouTube `yt-dlp` transcripts & comments, LaptopMag editorial reviews, Level1Techs Discourse REST API, Arabhardware regional data, Reddit fallback, and S3 Claim-Check Storage).
- [ ] **Milestone 10**: DeBERTa-v3 Aspect-Based Sentiment Analysis (ABSA) model for thermals, fan noise, and hinges.
- [x] **Milestone 11**: Distributed Redis Caching layer for TOPSIS matrix and catalog endpoints.
- [ ] **Milestone 12**: Interactive Consumer Frontend with Persona Quiz and Side-by-Side Comparison Matrix.

---

## 👨‍💻 Engineering & Authorship

Developed with extreme attention to **Clean Architecture**, **domain modeling**, and **system reliability**. Every component—from anti-bot DOM crawling to mathematical decision-making—is engineered to deliver genuine transparency and value to laptop buyers navigating complex markets.
