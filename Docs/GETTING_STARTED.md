# Developer Getting Started & Environment Setup

This guide provides step-by-step instructions for setting up the development environment, installing browser dependencies, running database migrations, executing scrapers, and troubleshooting common issues across both `scraper-service` and `catalog-service`.

---

## 1. System Prerequisites

* **Operating System**: Windows 10 / 11 (or Linux/macOS)
* **Python**: 3.11+ (64-bit recommended)
* **PostgreSQL**: 15+ (Local instance or Docker container)
* **Shell**: PowerShell (Windows) or Bash (Linux/macOS)
* **Git**: Installed and configured

---

## 2. Workspace & Virtual Environment Setup

The repository contains two independent microservices with their own isolated Python virtual environments:

```
laptop-recommender/
├── services/
│   ├── scraper-service/    # Standalone web ingestion engine
│   └── catalog-service/    # Relational catalog, matching, and recommendation API
```

---

### Setting Up `scraper-service`

```powershell
# 1. Navigate to scraper service
cd "services/scraper-service"

# 2. Create the virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# (If PowerShell blocks script execution, run once as administrator:)
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# On Linux / macOS:
# source .venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Install Playwright / Patchright browser binaries
playwright install chromium
```

---

### Setting Up `catalog-service`

```powershell
# 1. Open a new terminal and navigate to catalog service
cd "services/catalog-service"

# 2. Create the virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# On Linux / macOS:
# source .venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Configure environment variables (.env)
cp .env.example .env
# Edit .env to set your PostgreSQL connection string:
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/laptop_recommender

# 6. Apply database migrations
alembic upgrade head

# 7. Start the development server
uvicorn app.main:app --reload --port 8000
```

---

## 3. IDE Configuration (VS Code)

To ensure Pylance / Python language server resolves all local packages and submodules across services, the repository includes a preconfigured [`.vscode/settings.json`](file:///d:/Development/Side%20Projects/laptop-recommender/.vscode/settings.json):

```json
{
  "python.analysis.extraPaths": [
    "${workspaceFolder}/services/scraper-service",
    "${workspaceFolder}/services/scraper-service/.venv/Lib/site-packages",
    "${workspaceFolder}/services/catalog-service",
    "${workspaceFolder}/services/catalog-service/.venv/Lib/site-packages"
  ],
  "python.defaultInterpreterPath": "${workspaceFolder}/services/scraper-service/.venv/Scripts/python.exe"
}
```

---

## 4. Running the Scraper CLI

Always run commands as modules from within `services/scraper-service` with its virtual environment activated:

```powershell
cd "services/scraper-service"
.\.venv\Scripts\Activate.ps1
```

### CLI Help
```powershell
python -m app.cli --help
```

### Common Commands:

#### 1. Quick Brand Catalog Verification (Level 1)
Fetches catalog summary cards sorted by Newest:
```powershell
python -m app.cli --brand asus --mode brand-only --level 1
```

#### 2. Deep Specification Crawl (Level 2)
Visits full `/techspec/` sheets, extracts CPU, GPU, RAM, storage, colors, and SKU variants:
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --save-json asus_full.json
```

#### 3. Incremental Update (Watermark Cursor)
Stops immediately upon reaching the watermark laptop pointer:
```powershell
python -m app.cli --brand asus --mode brand-only --level 2 --until-model "S3407" --save-json asus_incremental.json
```

#### 4. Direct Retailer Store Crawling
Crawls live inventory, stock availability, and current EGP prices from Egyptian retailers:
```powershell
# Scrape all supported stores (Compumarts, Sigma, 2B)
python -m app.cli --mode store --stores all --limit 20

# Scrape a specific store
python -m app.cli --mode store --stores compumarts --limit 15 --save-json store_compumarts.json
```

---

## 5. Troubleshooting & Gotchas

### 1. Windows Character Encoding (`UnicodeEncodeError: 'charmap' codec can't encode...`)
* **Cause**: The default console codepage on Windows PowerShell is `cp1252` (ANSI), which crashes when Python prints Unicode symbols (like `✓`, `⚙️`, or Arabic text).
* **Fix**:
  * All production CLI code uses ASCII-safe formatting (e.g. `[+]`, `[-]`, `[!]`).
  * If needed, set your terminal codepage to UTF-8 in PowerShell:
    ```powershell
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001
    ```

### 2. `playwright._impl._errors.Error: Executable doesn't exist`
* **Cause**: Headless Chromium browser binaries have not been downloaded.
* **Fix**:
  ```powershell
  playwright install chromium
  ```

### 3. `ModuleNotFoundError: No module named 'scrapling'`
* **Cause**: Running Python outside the activated virtual environment.
* **Fix**: Ensure `.\.venv\Scripts\Activate.ps1` has been executed before running `python -m app.cli`.

