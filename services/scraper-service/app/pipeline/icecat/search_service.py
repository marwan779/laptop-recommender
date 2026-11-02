"""Icecat Search & Spec-First Product Matching Service.

Queries Icecat's search endpoint (categoryId=151) using pure hardware
specifications (without regional SKU/MPN codes) and evaluates zero-contradiction
shared specification matches (`EXACT_MATCH`, `VARIANT_MATCH`, `NOT_FOUND`).
"""

from __future__ import annotations

import random
import re
import time
from typing import Any
from urllib.parse import quote

from curl_cffi import requests

from app.common.logger import get_logger

logger = get_logger("pipeline.icecat.search")

ICECAT_SEARCH_API = "https://icecat.biz/search/rest/get-products-list"
ICECAT_WARMUP_URL = "https://icecat.biz/en/search/computers-peripherals"
LAPTOPS_CATEGORY_ID = "151"

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


def sanitize_query_text(s: str | None) -> str:
    """Sanitize query string to ASCII-friendly tokens without symbols."""
    if not s:
        return ""
    s = s.replace("—", "-").replace("–", "-").replace("―", "-")
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("®", "").replace("™", "").replace("©", "")
    s = re.sub(r"[^\w\s\-\.\+]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_token(s: str | None) -> str:
    """Normalize string for token comparison (lowercase, alphanumeric only)."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def extract_clean_family(laptop: dict[str, Any]) -> str:
    """Extract clean marketing family/series without regional MPNs or SKUs."""
    raw_family = (
        laptop.get("laptop_family") or (laptop.get("specs", {}).get("identity", {}) or {}).get("laptop_family") or ""
    ).strip()
    brand = (laptop.get("brand") or (laptop.get("specs", {}).get("identity", {}) or {}).get("brand") or "").strip()

    if raw_family:
        cleaned = re.sub(r"\([^)]*\)", "", raw_family).strip()
        if brand and cleaned.lower().startswith(brand.lower() + " "):
            cleaned = cleaned[len(brand) :].strip()
        if cleaned and cleaned.lower() not in ("unknown", "none", "laptop", "notebook"):
            return sanitize_query_text(cleaned)

    combined = f"{laptop.get('laptop_model') or ''} {laptop.get('title') or ''}".lower()
    for kw in KNOWN_SERIES_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", combined):
            return kw.title()

    m_dell = re.search(r"\b(g15|g16|pro\s+1[3456])\b", combined)
    if m_dell:
        return m_dell.group(1).upper()

    return ""


def extract_core_cpu_chip(cpu_model: str | None) -> str:
    """Extract primary chip number (e.g. '12700H', '13620H', '8940HX', '240H', '150U', '350')."""
    if not cpu_model:
        return ""
    s = cpu_model.strip()
    m = re.search(r"\b(\d{4,5}[A-Z]{1,2}|\d{3}[A-Z]{1,2})\b", s, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m_snap = re.search(r"\b(X1[A-Z]?-\d{2}-\d{3})\b", s, re.IGNORECASE)
    if m_snap:
        return m_snap.group(1).upper()
    m_ai = re.search(r"\b(?:AI\s+\d+\s+(?:HX\s+)?|Ryzen\s+\d+\s+)(\d{3})\b", s, re.IGNORECASE)
    if m_ai:
        return m_ai.group(1)
    m_apple = re.search(r"\b(M[1-5](?:\s+(?:Pro|Max))?)\b", s, re.IGNORECASE)
    if m_apple:
        return m_apple.group(1).upper()
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
        raw = re.sub(r"^(RTX|GTX|RX|MX)(\d)", r"\1 \2", raw)
        return raw
    lower = gpu_model.lower()
    for igpu in ["arc 140v", "arc 130v", "radeon 890m", "radeon 880m", "radeon 860m", "radeon 780m"]:
        if igpu in lower:
            return igpu.upper()
    return ""


def evaluate_spec_match(
    catalog_laptop: dict[str, Any],
    candidate_product: dict[str, Any],
) -> tuple[str, dict[str, bool]]:
    """Determine if an Icecat product matches all shared specifications (Zero SKU/MPN, Zero Contradictions)."""
    specs = catalog_laptop.get("specs", {}) or {}
    cpu_spec = specs.get("cpu", {}) or {}
    gpu_spec = specs.get("gpu", {}) or {}
    mem_spec = specs.get("memory", {}) or {}
    storage_spec = specs.get("storage", {}) or {}
    display_spec = specs.get("display", {}) or {}

    brand = (catalog_laptop.get("brand") or (specs.get("identity", {}) or {}).get("brand") or "").strip().lower()
    clean_family = extract_clean_family(catalog_laptop).lower()

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

    # 2. Product Family / Line Consistency
    family_anchors = [a for a in CORE_FAMILY_ANCHORS if a in clean_family]
    if family_anchors:
        matches["family"] = any(a in all_text for a in family_anchors)
    else:
        matches["family"] = True

    # 3. CPU Chip Match
    cpu_chip = extract_core_cpu_chip(cpu_spec.get("model"))
    if cpu_chip:
        chip_low = cpu_chip.lower()
        if chip_low == "13645hx":
            matches["cpu"] = "13645hx" in all_text or "13650hx" in all_text
        else:
            matches["cpu"] = (
                bool(re.search(rf"\b{re.escape(chip_low)}\b", all_text)) or normalize_token(chip_low) in norm_all_text
            )
    else:
        matches["cpu"] = True

    # 4. GPU Match
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

    # 7. Display Size Consistency
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
    """Construct pure spec-based search queries without regional SKU/MPN codes."""
    queries: list[str] = []

    specs = laptop.get("specs", {}) or {}
    brand = sanitize_query_text(laptop.get("brand") or (specs.get("identity", {}) or {}).get("brand") or "")
    clean_family = extract_clean_family(laptop)
    cpu_spec = specs.get("cpu", {}) or {}
    cpu_model = cpu_spec.get("model") or ""
    cpu_line = cpu_spec.get("line") or ""
    gpu_spec = specs.get("gpu", {}) or {}
    gpu_model = gpu_spec.get("model") or ""
    ram_gb = (specs.get("memory", {}) or {}).get("capacity_gb")
    storage_gb = (specs.get("storage", {}) or {}).get("capacity_gb")

    cpu_chip = extract_core_cpu_chip(cpu_model)
    if cpu_chip.upper() == "13645HX":
        cpu_chip = "13650HX"
    elif cpu_chip.isdigit() and len(cpu_chip) == 3 and cpu_line:
        cpu_chip = sanitize_query_text(f"{cpu_line} {cpu_chip}")

    gpu_chip = extract_core_gpu_chip(gpu_model) if not gpu_spec.get("integrated") else ""

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

    # Query 1: Full Spec Query
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

    # Query 2: Brand + Clean Family + CPU + GPU
    q2_parts = [brand, clean_family, cpu_chip]
    if gpu_chip:
        q2_parts.append(gpu_chip)
    elif ram_gb:
        q2_parts.append(f"{ram_gb}GB")
    q2 = sanitize_query_text(" ".join(p for p in q2_parts if p))
    if q2 and q2 not in queries:
        queries.append(q2)

    # Query 3: Brand + CPU + RAM + Storage + GPU
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


class IcecatSearchService:
    """Service for searching and matching laptops against Icecat category 151."""

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
        """Query Icecat /search/rest/get-products-list with categoryId 151."""
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
                jitter = random.uniform(0.1, 0.4)
                time.sleep(self.base_delay + jitter)

                resp = self.session.post(ICECAT_SEARCH_API, json=payload, headers=headers, timeout=20)

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

    def match_laptop(self, laptop: dict[str, Any]) -> dict[str, Any]:
        """Run prioritized spec queries for a single laptop and return match result."""
        queries = build_search_queries(laptop)
        best_candidate: dict[str, Any] | None = None
        best_status = "NOT_FOUND"
        matched_query_used = ""

        for q in queries:
            _count, products = self.search_products(q)
            if not products:
                continue

            for p in products:
                status, _field_matches = evaluate_spec_match(laptop, p)
                if status == "EXACT_MATCH":
                    best_status = "EXACT_MATCH"
                    best_candidate = p
                    matched_query_used = q
                    break
                elif status == "VARIANT_MATCH" and best_status != "EXACT_MATCH":
                    best_status = "VARIANT_MATCH"
                    best_candidate = p
                    matched_query_used = q

            if best_status == "EXACT_MATCH":
                break

        if best_candidate and best_status in ("EXACT_MATCH", "VARIANT_MATCH"):
            return {
                "match_status": best_status,
                "icecat_product_id": best_candidate.get("product_id"),
                "icecat_title": best_candidate.get("title"),
                "icecat_mpn": best_candidate.get("mpn"),
                "icecat_url": "https://icecat.biz" + str(best_candidate.get("url") or ""),
                "matched_query": matched_query_used,
            }

        return {
            "match_status": "NOT_FOUND",
            "icecat_product_id": None,
            "icecat_title": None,
            "icecat_mpn": None,
            "icecat_url": None,
            "queries_attempted": queries,
        }
