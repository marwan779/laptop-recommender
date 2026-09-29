"""GigaByte Brand Scraper for official GigaByte Laptop catalog.

Crawls:
  - Level 1: Listing cards on https://www.gigabyte.com/Laptop/All-Series?page={page}
             (strictly sorted newest-first).
  - Level 2: Technical specifications from https://www.gigabyte.com/Laptop/{model}/sp#sp
             via structured DOM extraction (<ul class="spec-item-list">).
"""

from __future__ import annotations

import itertools
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from curl_cffi.curl import CurlHttpVersion

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import ConfigurationItem, LaptopDetail, LaptopSummary
from app.scrapers.base import BaseBrandScraper


class GigabyteDateExtractor:
    """Infers release date and generation year for GigaByte laptops."""

    YEAR_IN_NAME_RE = re.compile(r"\((\d{4})\)")

    HARDWARE_YEAR_MAP = [
        # RTX 50 Series / Intel Ultra Series 2 / AMD Ryzen 200 - 2025/2026
        (re.compile(r"\b(?:RTX\s*50|5090|5080|5070|5060|Series\s*2|288V|268V|258V|256V|Ryzen\s*(?:AI)?\s*[79]\s*2\d{2}|9955HX|Strix\s*Point)\b", re.I), 2025, "2025-01-01"),
        # Intel Core Ultra Series 1 / 14th Gen / RTX 40 Series Refresh - 2024
        (re.compile(r"\b(?:Ultra\s+[579]\s+1\d{2}[A-Za-z]?|14900HX|14700HX|14650HX|14th\s+Gen|Hawk\s+Point|8945HS|8845HS|2024)\b", re.I), 2024, "2024-01-01"),
        # 13th Gen Intel / RTX 40 Series Initial - 2023
        (re.compile(r"\b(?:13980HX|13900H|13700H|13500H|13th\s+Gen|RTX\s*40|2023)\b", re.I), 2023, "2023-01-01"),
        # 12th Gen Intel / RTX 30 Series Refresh - 2022
        (re.compile(r"\b(?:12900H|12700H|12500H|12th\s+Gen|2022)\b", re.I), 2022, "2022-01-01"),
        # 11th Gen Intel / RTX 30 Series - 2021
        (re.compile(r"\b(?:11980HK|11900H|11800H|11th\s+Gen|RTX\s*30|2021)\b", re.I), 2021, "2021-01-01"),
    ]

    @classmethod
    def extract_year_and_date(cls, name: str, specs_text: str = "") -> tuple[int | None, str | None]:
        # 1. Direct year tag in model name, e.g. "AORUS 16X (2024)"
        m = cls.YEAR_IN_NAME_RE.search(name)
        if m:
            yr = int(m.group(1))
            return yr, f"{yr}-01-01"

        # 2. Hardware mapping
        combined = f"{name} {specs_text}"
        for pattern, yr, dt in cls.HARDWARE_YEAR_MAP:
            if pattern.search(combined):
                return yr, dt

        return None, None


class GigabyteBrandScraper(BaseBrandScraper):
    """Brand scraper for official GigaByte laptop catalog."""

    CATALOG_BASE_URL = "https://www.gigabyte.com/Laptop/All-Series"

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
    def brand_name(self) -> str:
        return "GigaByte"

    @property
    def catalog_url(self) -> str:
        return self.CATALOG_BASE_URL

    def _determine_family(self, text: str, url: str) -> str:
        combined = f"{text} {url}".lower()
        if "aorus master" in combined or "aorus elite" in combined or "aorus" in combined:
            return "AORUS"
        elif "aero" in combined:
            return "AERO"
        elif "eagle" in combined:
            return "GIGABYTE EAGLE"
        elif "gaming" in combined or re.search(r"\bg[567]x?\b", combined):
            return "GIGABYTE Gaming"
        return "GIGABYTE Laptop"

    def _extract_model_code(self, name: str, url: str) -> str | None:
        # Pattern 1: Suffix part code e.g. "GA6EH", "GL6J", "GA8J", "AM6H", "EG64H"
        m_code = re.search(r"\b([A-Z]{2}\d{1,2}[A-Z]{1,2})\b", name)
        if m_code:
            return m_code.group(1).upper()

        # Pattern 2: Series number e.g. "16X", "17X", "G6X", "G5", "G7"
        m_series = re.search(r"\b([A-Z]?\d{1,2}[A-Z]?)\b", name)
        if m_series and m_series.group(1).upper() not in ("AI", "PRO", "MAX"):
            return m_series.group(1).upper()

        # Pattern 3: URL slug part
        slug = url.rstrip("/").split("/")[-1]
        parts = slug.split("-")
        if parts:
            last = parts[-1]
            if re.match(r"^[A-Za-z0-9]{3,6}$", last):
                return last.upper()

        return None

    def _fetch_html(self, url: str, timeout: int = 35, retries: int = 3) -> str | None:
        """Fetch HTML content with curl_cffi Chrome impersonation (HTTP/1.1) and connection retry."""
        clean_url = url.split("#")[0]
        for attempt in range(1, retries + 1):
            try:
                resp = self._session.get(
                    clean_url,
                    headers=self._headers,
                    impersonate="chrome120",
                    http_version=CurlHttpVersion.V1_1,
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    time.sleep(0.15)  # Polite pacing to avoid CDN rate-limiting
                    return resp.text
                elif resp.status_code == 404:
                    return None
            except Exception as e:
                # Reset session on dead keep-alive socket or timeout
                self._session = cffi_requests.Session()
                time.sleep(0.5)
                if attempt == retries:
                    print(f"[{self.brand_name}] Failed to fetch {clean_url} after {retries} attempts: {e}")
                continue
        return None

    def _matches_watermark(self, identifier: str | None, until_model: str | list[str] | None) -> bool:
        if not until_model or not identifier:
            return False
        targets = [until_model] if isinstance(until_model, str) else list(until_model)
        ident_clean = re.sub(r"[^a-zA-Z0-9]", "", identifier).lower()
        for target in targets:
            if not target:
                continue
            t_clean = re.sub(r"[^a-zA-Z0-9]", "", str(target)).lower()
            if t_clean and (t_clean in ident_clean or ident_clean in t_clean):
                return True
        return False

    def get_laptop_summaries(
        self,
        limit: int | None = None,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
    ) -> list[LaptopSummary]:
        """Level 1: Scrape GigaByte listing cards across catalog pages (newest first)."""
        summaries: list[LaptopSummary] = []
        seen_urls: set[str] = set()
        watermark_hit = False

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )
        max_pages_display = str(max_pages) if max_pages is not None else "Unlimited (All Pages)"
        print(
            f"[{self.brand_name}] Starting Level 1 catalog scan "
            f"(newest first, until_model='{watermark_display}', max_pages={max_pages_display}, limit={limit or 'All'})"
        )

        for page_idx in itertools.count(1):
            if max_pages is not None and page_idx > max_pages:
                break
            if watermark_hit:
                break
            if limit and len(summaries) >= limit:
                break

            target_url = f"{self.catalog_url}?page={page_idx}"
            print(f"[{self.brand_name}] Fetching page {page_idx}: {target_url}...")

            html = self._fetch_html(target_url)
            if not html:
                print(f"[{self.brand_name}] Could not retrieve page {page_idx}. Ending catalog pagination.")
                break

            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(".gbt-cl-card")

            if not cards:
                print(f"[{self.brand_name}] No laptop cards found on page {page_idx}. Reached end of catalog.")
                break

            print(f"[{self.brand_name}] Page {page_idx}: Found {len(cards)} laptop cards.")
            cards_added = 0

            for card in cards:
                link_el = card.select_one('a[href*="/Laptop/"]')
                if not link_el:
                    continue

                href = link_el.get("href", "")
                if not href or any(x in href.lower() for x in ("all-series", "faq", "support", "utility")):
                    continue

                full_url = urljoin("https://www.gigabyte.com", href)
                if full_url in seen_urls:
                    continue

                # Title
                title_el = card.select_one(".gbt-cl-card-top-title, [class*='title']")
                name = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)
                if not name:
                    continue

                family = self._determine_family(name, full_url)
                model_code = self._extract_model_code(name, full_url)
                slug = full_url.rstrip("/").split("/")[-1]

                # Watermark check
                if until_model and (
                    self._matches_watermark(name, until_model)
                    or self._matches_watermark(model_code, until_model)
                    or self._matches_watermark(slug, until_model)
                ):
                    print(f"[{self.brand_name}] Reached watermark '{watermark_display}' at '{name}'. Halting Level 1 scan.")
                    watermark_hit = True
                    break

                # Extract thumbnail
                img_el = card.select_one("img[src], img[data-src]")
                img_url = None
                if img_el:
                    src = img_el.get("src") or img_el.get("data-src")
                    if src:
                        img_url = urljoin("https://www.gigabyte.com", src)

                # Card specs / tags
                tag_elems = card.select(".gbt-cl-card-bt-tags span, .gbt-chip, [class*='tag']")
                tags_text = " ".join(t.get_text(strip=True) for t in tag_elems)

                release_year, release_date = GigabyteDateExtractor.extract_year_and_date(name, tags_text)
                specs_url = f"{full_url.rstrip('/')}/sp"

                seen_urls.add(full_url)
                cards_added += 1

                summaries.append(
                    LaptopSummary(
                        brand=self.brand_name,
                        name=name,
                        price=None,
                        price_egp=None,
                        currency="EGP",
                        family=family,
                        model=model_code,
                        product_url=full_url,
                        specs_url=specs_url,
                        thumbnail_url=img_url,
                        release_date=release_date,
                        release_year=release_year,
                    )
                )

                if limit and len(summaries) >= limit:
                    break

            if cards_added == 0:
                print(f"[{self.brand_name}] No new laptop cards added on page {page_idx}. Ending catalog pagination.")
                break

        print(f"[{self.brand_name}] Level 1 complete: Scraped {len(summaries)} laptop summaries.")
        return summaries

    def get_laptop_detail(self, summary: LaptopSummary) -> LaptopDetail | None:
        """Level 2: Fetch and parse full hardware specs from {product_url}/sp."""
        target_url = (summary.specs_url or f"{summary.product_url.rstrip('/')}/sp").split("#")[0]
        print(f"[{self.brand_name}] Level 2 Crawl: Fetching specs for '{summary.name}' from {target_url}...")

        html = self._fetch_html(target_url)
        if not html:
            print(f"[{self.brand_name}] Specs page not found or unavailable for '{summary.name}'. Skipping.")
            self.record_skipped(
                name=summary.name,
                url=target_url,
                reason="Specs page not found or unavailable",
                stage="level2_specs",
            )
            return None

        soup = BeautifulSoup(html, "html.parser")
        all_specs: dict[str, str] = {}

        # GigaByte uses <ul class="spec-item-list"> with <li class="spec-title"> and <li class="spec-desc">
        for item in soup.select("ul.spec-item-list"):
            title_el = item.select_one("li.spec-title")
            desc_el = item.select_one("li.spec-desc")
            if title_el and desc_el:
                key = title_el.get_text(strip=True)
                val = desc_el.get_text(" \n ", strip=True)
                if key and val:
                    all_specs[key] = val

        # Fallback to general tables if spec-item-list was not present
        if not all_specs:
            for row in soup.select("table tr"):
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    k = th.get_text(strip=True)
                    v = td.get_text(" ", strip=True)
                    if k and v:
                        all_specs[k] = v

        if not all_specs:
            print(f"[{self.brand_name}] [!] No specifications found for '{summary.name}' (Placeholder). Skipping.")
            self.record_skipped(
                name=summary.name,
                url=target_url,
                reason="No specifications found on specs page (Placeholder)",
                stage="level2_specs",
            )
            return None

        # Build structured specs
        def _get_spec(*keys: str) -> str | None:
            for k in keys:
                for s_key, s_val in all_specs.items():
                    if k.lower() == s_key.strip().lower() or k.lower() in s_key.strip().lower():
                        return s_val
            return None

        structured_specs = {
            "processor": _get_spec("CPU", "Processor"),
            "operating_system": _get_spec("OS", "Operating System"),
            "graphics": _get_spec("Video Graphics", "Graphics", "GPU"),
            "display": _get_spec("Display", "Screen"),
            "memory": _get_spec("System Memory", "Memory", "RAM"),
            "storage": _get_spec("Storage", "SSD"),
            "keyboard_touchpad": _get_spec("Keyboard Type", "Keyboard"),
            "io_ports": _get_spec("I/O Port", "Ports"),
            "audio": _get_spec("Audio", "Sound"),
            "communications": _get_spec("Communications", "Wireless", "Network"),
            "webcam": _get_spec("Webcam", "Camera"),
            "security": _get_spec("Security", "TPM"),
            "battery": _get_spec("Battery"),
            "power_supply": _get_spec("Adapter", "Power Adapter"),
            "dimensions": _get_spec("Dimensions (W x D x H)", "Dimensions"),
            "weight": _get_spec("Weight"),
            "color": _get_spec("Color"),
        }

        # Date & Year refinement with specs corpus
        specs_corpus = " ".join(f"{k}: {v}" for k, v in all_specs.items())
        rel_year, rel_date = GigabyteDateExtractor.extract_year_and_date(summary.name, specs_corpus)
        if not rel_year:
            rel_year = summary.release_year
        if not rel_date:
            rel_date = summary.release_date

        # Extract configuration items
        configurations: list[ConfigurationItem] = [
            ConfigurationItem(
                model=summary.model or summary.name,
                model_series=summary.model,
                base_model=summary.model or summary.name,
                mpn=summary.model,
                official_specs=all_specs,
                stores=[],
            )
        ]

        # Extract distinct colors
        colors: list[str] = []
        raw_colors = structured_specs.get("color")
        if raw_colors:
            for c in re.split(r"[\n,/]+", raw_colors):
                c_clean = c.strip()
                if c_clean and len(c_clean) >= 3 and not c_clean.startswith("*"):
                    colors.append(c_clean)

        return LaptopDetail(
            brand=self.brand_name,
            name=summary.name,
            price=summary.price,
            price_egp=summary.price_egp,
            currency="EGP",
            family=summary.family,
            model=summary.model,
            base_model=summary.model or summary.name,
            product_url=summary.product_url,
            specs_url=target_url,
            thumbnail_url=summary.thumbnail_url,
            release_date=rel_date,
            release_year=rel_year,
            structured_specs=structured_specs,
            all_specs=all_specs,
            configurations=configurations,
            colors=colors,
            raw_markdown=html,
        )
