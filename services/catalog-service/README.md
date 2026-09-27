# Catalog Microservice

Central relational product catalog, specification evidence repository, entity resolution engine, and recommendation API for the Egyptian laptop market.

---

## 🎯 Architecture & Purpose

The `catalog-service` is the authoritative persistence and business logic core of the **Laptop Recommender System**. It is responsible for:
1. **Raw Payload Ingestion**: Consuming raw JSON outputs produced by `scraper-service` and storing them in immutable `RawLaptopRecord` audit logs.
2. **Canonical Product Hierarchy**: Enforcing a strict 4-tier normalized hierarchy (`Brand` $\rightarrow$ `LaptopFamily` $\rightarrow$ `LaptopModel` $\rightarrow$ `LaptopConfiguration`).
3. **Hardware Component Normalization**: Maintaining separate entities for processors (`CPU`), graphics cards (`GPU`), displays (`Display`), memory modules (`MemoryModule`), and storage devices (`StorageDevice`).
4. **Field-Level Specification Evidence**: Auditing the provenance of every hardware specification with confidence scores, source URLs, and timestamps via `SpecificationEvidence`.
5. **Entity Resolution & Store Alias Binding**: Resolving raw retailer offers against canonical hardware configurations using `LaptopConfigurationAlias`.
6. **Recommendation & Query API**: Exposing async FastAPI endpoints for laptop search, parametric filtering, and multi-store price comparisons.

---

## 📂 Service Structure

```
services/catalog-service/
├── alembic/                       # Alembic database migration scripts
│   ├── versions/                  # Versioned schema migrations
│   └── env.py                     # Async Alembic runtime environment
├── app/
│   ├── api/                       # REST API route handlers
│   │   └── routes/
│   │       └── health.py          # Health check & database ping
│   ├── core/                      # Core configuration and database session
│   │   ├── config.py              # Pydantic v2 BaseSettings (DB URL, pool sizes)
│   │   └── database.py            # SQLAlchemy 2.0 AsyncEngine and async sessionmaker
│   ├── models/                    # Declarative SQLAlchemy 2.0 ORM models
│   │   ├── base.py                # Base class and UTC timestamp helpers
│   │   ├── components.py          # CPU, GPU, Display, MemoryModule, StorageDevice, DataSource
│   │   ├── configuration.py       # Configuration details: Memory, Storage, Battery, Ports, Audio, Thermals
│   │   ├── laptop.py              # Brand, LaptopFamily, LaptopModel, LaptopConfiguration
│   │   └── pipeline.py            # RawLaptopRecord, SpecificationEvidence
│   ├── repositories/              # Database query repositories
│   ├── schemas/                   # Pydantic v2 API request/response schemas
│   ├── services/                  # Ingestion, matching, and recommendation business services
│   └── main.py                    # FastAPI application factory and lifespan events
├── tests/                         # Pytest test suite
├── .env.example                   # Example environment variables
├── alembic.ini                    # Alembic configuration
└── requirements.txt               # Service dependencies
```

---

## 🗄️ Relational Data Models

### 1. The 4-Tier Canonical Hierarchy
* **`Brand`**: Top-level manufacturer (e.g. `ASUS`, `Lenovo`, `HP`, `Dell`, `Acer`, `GigaByte`).
* **`LaptopFamily`**: Product marketing line (e.g. `Vivobook`, `ROG Strix`, `Legion Pro`, `ThinkPad X1`).
* **`LaptopModel`**: Base chassis model or series (e.g. `ASUS Vivobook S14 (S5452)`).
* **`LaptopConfiguration`**: Exact physical hardware SKU (e.g. `S5452MA-QD045W` with `Intel Core Ultra 7 258V`, `32GB LPDDR5X`, `1TB NVMe PCIe 4.0 SSD`, `14.0" 3K OLED 120Hz`). Identified by an immutable `identity_hash`.

### 2. Deep Hardware Component Entities
* **`CPU`**: Manufacturer, architecture, generation, core counts (P-cores / E-cores), TDP, base/boost clocks, benchmark scores.
* **`GPU`**: Integrated vs Discrete, architecture, VRAM size, memory type, TDP, benchmark scores.
* **`Display`**: Panel size (inches), resolution (width x height), panel type (OLED, IPS), refresh rate (Hz), color gamut (sRGB, DCI-P3 %), brightness (nits).
* **`LaptopMemory`** & **`LaptopStorage`**: Slot counts, soldered flags, capacity, expansion slots.
* **`Battery`**: Capacity (Wh), cell count, measured runtime hours.
* **`LaptopPort`**, **`LaptopConnectivity`**, **`LaptopWebcam`**, **`LaptopAudio`**, **`LaptopThermals`**, **`LaptopBuild`**, **`LaptopMeasurement`**.

### 3. Pipeline & Ingestion Audit Trail
* **`RawLaptopRecord`**: Stores raw scraped payloads (`raw_payload` as PostgreSQL `JSONB`), external IDs, ingestion timestamp, and processing status (`PENDING`, `PROCESSED`, `FAILED`).
* **`SpecificationEvidence`**: Records exact field-level extraction history (`field_name`, `field_value`, `source_url`, `confidence`, `collected_at`).
* **`LaptopConfigurationAlias`**: Maps retailer SKU strings and external IDs to the canonical `LaptopConfiguration`.

---

## 🚀 Getting Started

### 1. Prerequisites
* Python 3.11+ (64-bit)
* PostgreSQL 15+ (Local or Docker container)

### 2. Virtual Environment Setup
```powershell
# Navigate to catalog service
cd "services/catalog-service"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in `services/catalog-service/`:
```ini
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/laptop_recommender
DB_ECHO=false
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

### 4. Running Database Migrations
```powershell
# Apply all schema migrations to PostgreSQL
alembic upgrade head
```

### 5. Running the API Server
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Once started, visit:
* Interactive Swagger Docs: `http://localhost:8000/docs`
* Health Check: `http://localhost:8000/health`

