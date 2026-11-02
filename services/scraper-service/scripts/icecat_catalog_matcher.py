"""Icecat Catalog Matcher Script.

Searches Icecat for laptops from unified_catalog_latest.json using the
search endpoint with categoryId 151 (Laptops). Validates exact spec
matches across brand, chassis/model code, CPU, GPU, RAM, and Storage.
Outputs a comprehensive report of found vs not found laptops.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from curl_cffi import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("icecat_matcher")

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_CATALOG = SERVICE_ROOT / "scraping results" / "unified_catalog_latest.json"
DEFAULT_OUTPUT_REPORT = SERVICE_ROOT / "scraping results" / "icecat_match_report.json"
CHECKPOINT_PATH = SERVICE_ROOT / "scraping results" / ".icecat_matcher_checkpoint.json"

ICECAT_SEARCH_API = "https://icecat.biz/search/rest/get-products-list"
ICECAT_WARMUP_URL = "https://icecat.biz/en/search/computers-peripherals"
LAPTOPS_CATEGORY_ID = "151"


def sanitize_query_text(s: str | None) -> str:
    """Sanitize query string to ASCII-friendly tokens without symbols."""
    if not s:
        return ""
    # Replace unicode dashes with standard hyphen
    s = s.replace("—", "-").replace("–", "-").replace("―", "-")
    # Replace unicode quotes
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    # Remove registered trademark, copyright, etc.
    s = s.replace("®", "").replace("™", "").replace("©", "")
    # Remove excessive punctuation
    s = re.sub(r"[^\w\s\-\.\+]", " ", s)
    # Collapse whitespace
    return re.sub(r"\s+", " ", s).strip()


class IcecatClient:
    """Manages an impersonated Chrome session to query Icecat search endpoint."""

    def __init__(self, base_delay: float = 5.5) -> None:
        self.base_delay = base_delay
        self.session = requests.Session(impersonate="chrome120")
        self._warmed_up = False

    def warm_up(self) -> None:
        """Fetch search page to acquire browser session cookies (ULocation, SId)."""
        logger.info("Initializing Icecat session cookies from %s ...", ICECAT_WARMUP_URL)
        try:
            resp = self.session.get(
                ICECAT_WARMUP_URL,
                headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                timeout=20,
            )
            if resp.status_code == 200:
                self._warmed_up = True
                logger.info("Session warmed up successfully. Cookies: %s", list(self.session.cookies.keys()))
            else:
                logger.warning("Warmup returned status %s", resp.status_code)
        except Exception as e:
            logger.error("Session warmup failed: %s", e)

    def search_products(self, query: str, max_retries: int = 3) -> tuple[int, list[dict[str, Any]]]:
        """Query Icecat /search/rest/get-products-list with categoryId 151.

        Returns:
            tuple[total_count, list_of_product_dicts]
        """
        if not self._warmed_up:
            self.warm_up()

        clean_query = sanitize_query_text(query)
        encoded_query = quote(clean_query.encode("utf-8"))

        payload = {
            "searchString": clean_query,
            "sort": ["", ""],
            "tmp": None,
            "params": {"keyword": clean_query, "categoryId": LAPTOPS_CATEGORY_ID},
            "codes": {"ean": [], "mpn": []},
            "facetParams": [],
            "p": 0,
        }

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": f"https://icecat.biz/en/search/laptops?keyword={encoded_query}",
            "X-Requested-With": "XMLHttpRequest",
        }

        for attempt in range(1, max_retries + 1):
            try:
                # Add polite jitter delay (~5.5s - 6.0s pace keeps under the 10 req/min limit)
                jitter = random.uniform(0.1, 0.4)
                time.sleep(self.base_delay + jitter)

                resp = self.session.post(ICECAT_SEARCH_API, json=payload, headers=headers, timeout=20)

                # Track rate limit headers: only sleep if remaining is truly exhausted (0 or 1)
                remaining = resp.headers.get("x-ratelimit-remaining")
                if remaining is not None and int(remaining) <= 1:
                    reset_sec = int(resp.headers.get("x-ratelimit-reset", "10"))
                    if reset_sec > 0:
                        logger.info(
                            "Rate limit quota reached (remaining: %s). Waiting %ds for reset...",
                            remaining,
                            reset_sec,
                        )
                        time.sleep(reset_sec + 1)

                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("info", {}).get("count", 0)
                    products = data.get("products", [])
                    return count, products
                elif resp.status_code == 429:
                    wait_time = 15 * attempt
                    logger.warning("HTTP 429 Too Many Requests. Backing off for %ds...", wait_time)
                    time.sleep(wait_time)
                    self.warm_up()
                else:
                    logger.warning("Search failed with status %d: %s", resp.status_code, resp.text[:150])

            except Exception as e:
                logger.error("Exception querying '%s' (attempt %d/%d): %s", clean_query, attempt, max_retries, e)
                time.sleep(5 * attempt)

        return 0, []


def normalize_token(s: str | None) -> str:
    """Normalize string for token comparison (lowercase, alphanumeric only)."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


KNOWN_SERIES_KEYWORDS = [
    "tuf gaming",
    "rog strix",
    "rog zephyrus",
    "rog flow",
    "vivobook",
    "zenbook",
    "expertbook",
    "legion pro",
    "legion slim",
    "legion",
    "loq",
    "ideapad slim",
    "ideapad gaming",
    "ideapad",
    "thinkpad",
    "thinkbook",
    "yoga",
    "victus",
    "omen",
    "omnibook",
    "pavilion",
    "envy",
    "probook",
    "elitebook",
    "zbook",
    "alienware",
    "inspiron",
    "latitude",
    "vostro",
    "xps",
    "aurora",
    "nitro v",
    "nitro",
    "predator",
    "aspire",
    "swift",
    "travelmate",
    "katana",
    "cyborg",
    "stealth",
    "raider",
    "vector",
    "pulse",
    "sword",
    "crosshair",
    "prestige",
    "modern",
    "thin",
    "aorus",
    "aero",
    "g6x",
    "g6",
    "g5",
    "macbook air",
    "macbook pro",
]

CORE_FAMILY_ANCHORS = [
    "tuf",
    "rog",
    "vivobook",
    "zenbook",
    "expertbook",
    "legion",
    "loq",
    "ideapad",
    "thinkpad",
    "thinkbook",
    "yoga",
    "victus",
    "omen",
    "omnibook",
    "pavilion",
    "envy",
    "probook",
    "elitebook",
    "zbook",
    "alienware",
    "inspiron",
    "latitude",
    "vostro",
    "xps",
    "aurora",
    "nitro",
    "predator",
    "aspire",
    "swift",
    "travelmate",
    "katana",
    "cyborg",
    "stealth",
    "raider",
    "vector",
    "pulse",
    "sword",
    "crosshair",
    "prestige",
    "modern",
    "aorus",
    "aero",
    "macbook",
]


def extract_clean_family(laptop: dict[str, Any]) -> str:
    """Extract clean marketing family/series without regional MPNs or SKUs."""
    raw_family = (laptop.get("laptop_family") or "").strip()
    brand = (laptop.get("brand") or "").strip()

    # Clean embedded parenthetical MPNs like 'Travelmate P2 (Nx.Vpqem.008)'
    if raw_family:
        cleaned = re.sub(r"\([^)]*\)", "", raw_family).strip()
        if brand and cleaned.lower().startswith(brand.lower() + " "):
            cleaned = cleaned[len(brand) :].strip()
        if cleaned and cleaned.lower() not in ("unknown", "none", "laptop", "notebook"):
            return sanitize_query_text(cleaned)

    # Fallback: detect series from laptop_model or title
    combined = f"{laptop.get('laptop_model') or ''} {laptop.get('title') or ''}".lower()
    for kw in KNOWN_SERIES_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", combined):
            return kw.title()

    # Check Dell Pro / G15 style series
    m_dell = re.search(r"\b(g15|g16|pro\s+1[3456])\b", combined)
    if m_dell:
        return m_dell.group(1).upper()

    return ""


def extract_core_cpu_chip(cpu_model: str | None) -> str:
    """Extract primary chip number (e.g. '12700H', '13620H', '8940HX', '240H', '150U', '350')."""
    if not cpu_model:
        return ""
    s = cpu_model.strip()
    # 1. Standard 4-5 digit + suffix or 3 digit + suffix (e.g. 13650HX, 8940HX, 240H, 150U, 258V)
    m = re.search(r"\b(\d{4,5}[A-Z]{1,2}|\d{3}[A-Z]{1,2})\b", s, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 2. Snapdragon X models (e.g. X1-26-100, X1E-78-100)
    m_snap = re.search(r"\b(X1[A-Z]?-\d{2}-\d{3})\b", s, re.IGNORECASE)
    if m_snap:
        return m_snap.group(1).upper()
    # 3. AMD Ryzen AI 300 / 200 numeric models (e.g. AI 9 365, AI 7 350, AI 5 330, Ryzen 7 260)
    m_ai = re.search(r"\b(?:AI\s+\d+\s+(?:HX\s+)?|Ryzen\s+\d+\s+)(\d{3})\b", s, re.IGNORECASE)
    if m_ai:
        return m_ai.group(1)
    # 4. Apple M-series (e.g. M1, M2, M3, M4 Pro/Max)
    m_apple = re.search(r"\b(M[1-5](?:\s+(?:Pro|Max))?)\b", s, re.IGNORECASE)
    if m_apple:
        return m_apple.group(1).upper()
    # 5. Trailing 3-digit model number (e.g. "350", "260")
    m_num = re.search(r"\b(\d{3,5})\b", s)
    if m_num:
        return m_num.group(1)
    return s


def extract_core_gpu_chip(gpu_model: str | None) -> str:
    """Extract core GPU series/number (e.g. 'RTX 3060', 'RTX 4060', 'RTX 5060', 'MX350')."""
    if not gpu_model:
        return ""
    m = re.search(
        r"\b(RTX\s*\d{3,4}(?:\s*Ti)?|GTX\s*\d{3,4}(?:\s*Ti)?|RX\s*\d{3,4}[A-Z]{0,2}|MX\s*\d{3})\b",
        gpu_model,
        re.IGNORECASE,
    )
    if m:
        raw = re.sub(r"\s+", " ", m.group(1).upper()).strip()
        # Normalize RTX4050 -> RTX 4050 for search readability
        raw = re.sub(r"^(RTX|GTX|RX|MX)(\d)", r"\1 \2", raw)
        return raw
    # Check integrated names
    lower = gpu_model.lower()
    for igpu in ["arc 140v", "arc 130v", "radeon 890m", "radeon 880m", "radeon 860m", "radeon 780m"]:
        if igpu in lower:
            return igpu.upper()
    return ""


def evaluate_spec_match(
    catalog_laptop: dict[str, Any],
    candidate_product: dict[str, Any],
) -> tuple[str, dict[str, bool]]:
    """Determine if an Icecat product matches all shared specifications (Zero SKU/MPN, Zero Contradictions).

    Returns:
        tuple[status, field_matches]
        status: 'EXACT_MATCH' | 'VARIANT_MATCH' | 'NO_MATCH'
    """
    specs = catalog_laptop.get("specs", {}) or {}
    cpu_spec = specs.get("cpu", {}) or {}
    gpu_spec = specs.get("gpu", {}) or {}
    mem_spec = specs.get("memory", {}) or {}
    storage_spec = specs.get("storage", {}) or {}
    display_spec = specs.get("display", {}) or {}

    brand = (catalog_laptop.get("brand") or "").strip().lower()
    clean_family = extract_clean_family(catalog_laptop).lower()

    # Icecat text bundle to check against
    icecat_title = (candidate_product.get("title") or "").lower()
    icecat_long_desc = (candidate_product.get("long_summary_description") or "").lower()
    icecat_short_desc = (candidate_product.get("short_summary_description") or "").lower()
    icecat_name = (candidate_product.get("name") or "").lower()
    icecat_vendor = (candidate_product.get("manufacturer_name") or "").lower()
    all_text = f"{icecat_title} {icecat_long_desc} {icecat_short_desc} {icecat_name} {icecat_vendor}"
    norm_all_text = normalize_token(all_text)

    matches: dict[str, bool] = {}

    # 1. Brand Match
    matches["brand"] = bool(brand and (brand in icecat_vendor or brand in icecat_title or brand in all_text))

    # 2. Product Family / Line Consistency (No SKU/MPN required)
    # If our laptop belongs to a distinct sub-brand (e.g. LOQ, Legion, Vivobook, Victus), ensure Icecat matches it
    family_anchors = [a for a in CORE_FAMILY_ANCHORS if a in clean_family]
    if family_anchors:
        matches["family"] = any(a in all_text for a in family_anchors)
    else:
        matches["family"] = True

    # 3. CPU Chip Match
    cpu_chip = extract_core_cpu_chip(cpu_spec.get("model"))
    if cpu_chip:
        chip_low = cpu_chip.lower()
        # Handle known store typo 13645HX -> 13650HX
        if chip_low == "13645hx":
            matches["cpu"] = "13645hx" in all_text or "13650hx" in all_text
        else:
            matches["cpu"] = (
                bool(re.search(rf"\b{re.escape(chip_low)}\b", all_text)) or normalize_token(chip_low) in norm_all_text
            )
    else:
        matches["cpu"] = True

    # 4. GPU Match (Strict: discrete must match discrete chip; integrated must not match discrete RTX/GTX)
    gpu_chip = extract_core_gpu_chip(gpu_spec.get("model"))
    is_integrated = gpu_spec.get("integrated") is True or (
        not gpu_chip
        and any(
            k in ((gpu_spec.get("model") or "").lower())
            for k in ("integrated", "uhd", "iris", "radeon graphics", "intel graphics", "arc graphics")
        )
    )
    if gpu_chip and not is_integrated:
        matches["gpu"] = gpu_chip.lower() in all_text or normalize_token(gpu_chip) in norm_all_text
    elif is_integrated:
        # Ensure Icecat candidate doesn't contradict by having a dedicated RTX/GTX GPU
        has_contradicting_dgpu = bool(re.search(r"\b(geforce\s+rtx|geforce\s+gtx|rtx\s*\d{4}|gtx\s*\d{4})\b", all_text))
        matches["gpu"] = not has_contradicting_dgpu
    else:
        matches["gpu"] = True

    # 5. RAM Match
    ram_gb = mem_spec.get("capacity_gb")
    if ram_gb:
        ram_patterns = [f"{ram_gb} gb", f"{ram_gb}gb"]
        matches["ram"] = any(p in all_text for p in ram_patterns)
    else:
        matches["ram"] = True

    # 6. Storage Match
    storage_gb = storage_spec.get("capacity_gb")
    if storage_gb:
        if storage_gb in (1000, 1024):
            storage_patterns = ["1 tb", "1tb", "1000 gb", "1024 gb", "1.024 tb"]
        elif storage_gb in (2000, 2048):
            storage_patterns = ["2 tb", "2tb", "2000 gb", "2048 gb"]
        elif storage_gb in (4000, 4096):
            storage_patterns = ["4 tb", "4tb", "4000 gb", "4096 gb"]
        else:
            storage_patterns = [f"{storage_gb} gb", f"{storage_gb}gb"]
        matches["storage"] = any(p in all_text for p in storage_patterns)
    else:
        matches["storage"] = True

    # 7. Display Size Consistency (if both specify screen size, must not contradict)
    size_in = display_spec.get("size_inches")
    if size_in:
        m_icecat_size = re.search(r"\((\d{2}(?:\.\d)?)\s*(?:\"|''|inch)", all_text)
        if m_icecat_size:
            icecat_in = float(m_icecat_size.group(1))
            matches["display_size"] = abs(float(size_in) - icecat_in) <= 0.5
        else:
            matches["display_size"] = True
    else:
        matches["display_size"] = True

    # Classification: 100% shared hardware specs match -> EXACT_MATCH
    core_matched = (
        matches["brand"] and matches["family"] and matches["cpu"] and matches["gpu"] and matches["display_size"]
    )
    if core_matched and matches["ram"] and matches["storage"]:
        return "EXACT_MATCH", matches
    elif core_matched:
        return "VARIANT_MATCH", matches
    else:
        return "NO_MATCH", matches


def build_search_queries(laptop: dict[str, Any]) -> list[str]:
    """Construct pure spec-based search queries without regional SKU/MPN codes.

    1. Brand + Family + CPU + RAM + Storage + GPU (e.g. 'Lenovo LOQ 13650HX 16GB 512GB RTX 4050')
    2. Brand + Family + CPU + GPU (handles 1000GB vs 1TB formatting differences on Icecat)
    3. Brand + CPU + RAM + Storage + GPU (broad spec fallback if family naming differs)
    """
    queries: list[str] = []

    specs = laptop.get("specs", {}) or {}
    brand = sanitize_query_text(laptop.get("brand") or "")
    clean_family = extract_clean_family(laptop)
    cpu_spec = specs.get("cpu", {}) or {}
    cpu_model = cpu_spec.get("model") or ""
    cpu_line = cpu_spec.get("line") or ""
    gpu_Spec = specs.get("gpu", {}) or {}
    gpu_model = gpu_Spec.get("model") or ""
    ram_gb = (specs.get("memory", {}) or {}).get("capacity_gb")
    storage_gb = (specs.get("storage", {}) or {}).get("capacity_gb")

    cpu_chip = extract_core_cpu_chip(cpu_model)
    # Fix known store typo 13645HX -> 13650HX for search
    if cpu_chip.upper() == "13645HX":
        cpu_chip = "13650HX"
    elif cpu_chip.isdigit() and len(cpu_chip) == 3 and cpu_line:
        # E.g. 'Ryzen 5' + '170' -> 'Ryzen 5 170' so search token is specific
        cpu_chip = sanitize_query_text(f"{cpu_line} {cpu_chip}")

    gpu_chip = extract_core_gpu_chip(gpu_model) if not gpu_Spec.get("integrated") else ""

    storage_str = ""
    if storage_gb:
        if storage_gb in (1000, 1024):
            storage_str = "1TB"
        elif storage_gb in (2000, 2048):
            storage_str = "2TB"
        elif storage_gb in (4000, 4096):
            storage_str = "4TB"
        else:
            storage_str = f"{storage_gb}GB"

    # Query 1: Full Spec Query (Brand + Clean Family + CPU + RAM + Storage + GPU)
    q1_parts = [brand, clean_family, cpu_chip]
    if ram_gb:
        q1_parts.append(f"{ram_gb}GB")
    if storage_str:
        q1_parts.append(storage_str)
    if gpu_chip:
        q1_parts.append(gpu_chip)

    q1 = sanitize_query_text(" ".join(p for p in q1_parts if p))
    if q1:
        queries.append(q1)

    # Query 2: Brand + Clean Family + CPU + GPU (or RAM if integrated GPU)
    q2_parts = [brand, clean_family, cpu_chip]
    if gpu_chip:
        q2_parts.append(gpu_chip)
    elif ram_gb:
        q2_parts.append(f"{ram_gb}GB")
    q2 = sanitize_query_text(" ".join(p for p in q2_parts if p))
    if q2 and q2 not in queries:
        queries.append(q2)

    # Query 3: Brand + CPU + RAM + Storage + GPU (without family, in case store family label differs)
    if clean_family:
        q3_parts = [brand, cpu_chip]
        if ram_gb:
            q3_parts.append(f"{ram_gb}GB")
        if storage_str:
            q3_parts.append(storage_str)
        if gpu_chip:
            q3_parts.append(gpu_chip)
        q3 = sanitize_query_text(" ".join(p for p in q3_parts if p))
        if q3 and q3 not in queries:
            queries.append(q3)

    return queries


def load_checkpoint(
    output_path: Path = DEFAULT_OUTPUT_REPORT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    """Load previously completed matches from checkpoint or existing report's EXACT_MATCH entries."""
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, encoding="utf-8") as f:
                cp = json.load(f)
            processed_ids = set(cp.get("processed_ids", []))
            found = cp.get("found_laptops", [])
            not_found = cp.get("not_found_laptops", [])
            logger.info("Resuming from checkpoint with %d already processed laptops.", len(processed_ids))
            return found, not_found, processed_ids
        except Exception as e:
            logger.warning("Failed to load checkpoint (%s). Checking existing report...", e)

    if output_path.exists():
        try:
            with open(output_path, encoding="utf-8") as f:
                prev_report = json.load(f)
            exact_found = [
                item
                for item in prev_report.get("found_laptops", [])
                if item.get("match_status") == "EXACT_MATCH" and item.get("canonical_id")
            ]
            processed_ids = {item["canonical_id"] for item in exact_found}
            logger.info(
                "Loaded %d existing EXACT_MATCH laptops from %s. Will re-evaluate the remaining laptops.",
                len(exact_found),
                output_path.name,
            )
            return exact_found, [], processed_ids
        except Exception as e:
            logger.warning("Failed to load existing report (%s). Starting fresh.", e)

    return [], [], set()


def save_checkpoint(
    found: list[dict[str, Any]],
    not_found: list[dict[str, Any]],
    processed_ids: set[str],
) -> None:
    """Save run progress to checkpoint file."""
    try:
        data = {
            "saved_at": datetime.now(UTC).isoformat(),
            "processed_count": len(processed_ids),
            "processed_ids": list(processed_ids),
            "found_laptops": found,
            "not_found_laptops": not_found,
        }
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write checkpoint: %s", e)


def run_matcher(
    input_path: Path = DEFAULT_INPUT_CATALOG,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
    max_laptops: int | None = None,
    delay: float = 5.5,
    resume: bool = True,
) -> dict[str, Any]:
    """Execute Icecat matching against the catalog laptops."""
    start_time = time.perf_counter()

    if not input_path.exists():
        raise FileNotFoundError(f"Catalog input file not found: {input_path}")

    logger.info("Loading unified catalog from: %s", input_path)
    with open(input_path, encoding="utf-8") as f:
        catalog_data = json.load(f)

    laptops = catalog_data.get("laptops", [])
    total_catalog = len(laptops)
    if max_laptops:
        laptops = laptops[:max_laptops]
        logger.info("Restricted run to %d / %d laptops.", len(laptops), total_catalog)

    client = IcecatClient(base_delay=delay)
    client.warm_up()

    found_laptops: list[dict[str, Any]] = []
    not_found_laptops: list[dict[str, Any]] = []
    processed_ids: set[str] = set()

    if resume:
        found_laptops, not_found_laptops, processed_ids = load_checkpoint(output_path)

    print("=" * 80)
    print(f"Starting Icecat Catalog Spec Matcher ({len(laptops)} laptops)")
    print(f"Pacing: ~{delay}s delay per query (matches Icecat 10 req/min limit) | Category: 151")
    print("=" * 80)

    for idx, laptop in enumerate(laptops, 1):
        cid = laptop.get("canonical_id") or f"laptop_{idx}"
        if cid in processed_ids:
            continue

        brand = laptop.get("brand") or "Unknown"
        model_name = laptop.get("laptop_model") or "Unknown"
        catalog_title = laptop.get("title") or f"{brand} {model_name}"

        queries = build_search_queries(laptop)
        matched = False
        best_candidate: dict[str, Any] | None = None
        best_status = "NO_MATCH"
        matched_query_used = ""

        logger.info(
            "[%d/%d] Searching: %s %s (primary query: '%s')",
            idx,
            len(laptops),
            brand,
            model_name,
            queries[0] if queries else "",
        )

        for q in queries:
            count, products = client.search_products(q)
            if not products:
                continue

            for p in products:
                status, field_matches = evaluate_spec_match(laptop, p)
                if status == "EXACT_MATCH":
                    best_status = "EXACT_MATCH"
                    best_candidate = p
                    matched_query_used = q
                    matched = True
                    break
                elif status == "VARIANT_MATCH" and best_status != "EXACT_MATCH":
                    best_status = "VARIANT_MATCH"
                    best_candidate = p
                    matched_query_used = q
                    matched = True

            if best_status == "EXACT_MATCH":
                break

        if matched and best_candidate:
            record = {
                "canonical_id": cid,
                "catalog_title": catalog_title,
                "brand": brand,
                "laptop_model": model_name,
                "mpn": laptop.get("mpn"),
                "icecat_product_id": best_candidate.get("product_id"),
                "icecat_title": best_candidate.get("title"),
                "icecat_mpn": best_candidate.get("mpn"),
                "icecat_url": "https://icecat.biz" + str(best_candidate.get("url") or ""),
                "match_status": best_status,
                "matched_query": matched_query_used,
            }
            found_laptops.append(record)
            logger.info("  -> %s found: %s", best_status, record["icecat_title"][:80])
        else:
            not_found_laptops.append(
                {
                    "canonical_id": cid,
                    "catalog_title": catalog_title,
                    "brand": brand,
                    "laptop_model": model_name,
                    "mpn": laptop.get("mpn"),
                    "queries_attempted": queries,
                }
            )
            logger.info("  -> NOT FOUND on Icecat.")

        processed_ids.add(cid)

        # Checkpoint every 10 laptops
        if len(processed_ids) % 10 == 0:
            save_checkpoint(found_laptops, not_found_laptops, processed_ids)

    # Final summary
    elapsed = round(time.perf_counter() - start_time, 2)
    exact_count = sum(1 for f in found_laptops if f.get("match_status") == "EXACT_MATCH")
    variant_count = sum(1 for f in found_laptops if f.get("match_status") == "VARIANT_MATCH")
    total_processed = len(processed_ids)
    match_rate = round((len(found_laptops) / total_processed) * 100.0, 2) if total_processed else 0.0

    report = {
        "summary": {
            "total_laptops": total_processed,
            "total_found": len(found_laptops),
            "exact_matches": exact_count,
            "variant_matches": variant_count,
            "not_found": len(not_found_laptops),
            "match_rate_pct": match_rate,
            "elapsed_seconds": elapsed,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "found_laptops": found_laptops,
        "not_found_laptops": not_found_laptops,
    }

    # Write output report atomically
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("Matching complete! Report saved to: %s", output_path)

    # Clean up checkpoint on complete run
    if CHECKPOINT_PATH.exists() and len(processed_ids) >= len(laptops):
        try:
            CHECKPOINT_PATH.unlink()
        except Exception:
            pass

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Match catalog laptops against Icecat database.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_CATALOG, help="Input catalog path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_REPORT, help="Output report JSON path")
    parser.add_argument("--max", type=int, default=None, help="Maximum number of laptops to match (test mode)")
    parser.add_argument("--delay", type=float, default=5.5, help="Pacing delay in seconds between queries")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh without loading checkpoint")

    args = parser.parse_args()

    report = run_matcher(
        input_path=args.input,
        output_path=args.output,
        max_laptops=args.max,
        delay=args.delay,
        resume=not args.no_resume,
    )

    print("\n" + "=" * 80)
    print("Icecat Match Report Summary:")
    print(json.dumps(report["summary"], indent=2))
    print("=" * 80)


if __name__ == "__main__":
    main()
