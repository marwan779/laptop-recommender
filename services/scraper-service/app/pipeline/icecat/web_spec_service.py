"""Scrapling-powered Web Specification Search Service for Stage 4 NOT_FOUND Laptops.

Searches DuckDuckGo Lite via Scrapling's Fetcher and extracts specification tables
and snippets from online hardware databases and manufacturer spec pages to populate
missing (null) chassis/hardware fields when a laptop is absent from Icecat and the
Egyptian retailer page lacks full specifications.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

from app.common.logger import get_logger
from app.matching.models import CanonicalLaptop

logger = get_logger("pipeline.icecat.web_spec_service")

# Silence noisy Scrapling/curl deprecation or info logs during batch runs
logging.getLogger("scrapling").setLevel(logging.ERROR)

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"

# Preferred hardware specification domains for scraping structured tables
PREFERRED_SPEC_DOMAINS = (
    "nanoreview.net",
    "notebookcheck.net",
    "laptopmedia.com",
    "ultrabookreview.com",
    "psref.lenovo.com",
    "lenovo.com",
    "asus.com",
    "rog.asus.com",
    "hp.com",
    "dell.com",
    "msi.com",
    "acer.com",
    "gigabyte.com",
    "techpowerup.com",
    "gadgets360.com",
    "91mobiles.com",
    "smartprix.com",
    "kimovil.com",
    "specspro.net",
    "noteb.com",
)

# Domains to skip (local stores already scraped, video sites, social media, forums)
SKIP_DOMAINS = (
    "compumarts.com",
    "elbadrgroupeg.store",
    "sigma-computer.com",
    "youtube.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "quora.com",
    "amazon.",
    "ebay.",
    "noon.com",
    "jumia.",
    "ubuy.",
)

# Keywords indicating relevant hardware spec rows
SPEC_ROW_KEYWORDS = re.compile(
    r"\b("
    r"battery|wh|whr|watt|adapter|charger|power supply|cell|"
    r"weight|kg|lbs|dimension|width|depth|height|thickness|mm|material|aluminum|plastic|chassis|color|colour|"
    r"port|usb|type-c|thunderbolt|hdmi|displayport|rj-?45|ethernet|lan|audio jack|headphone|sd card|card reader|"
    r"wi-?fi|wlan|802\.11|bluetooth|"
    r"webcam|camera|shutter|ir |infrared|microphone|speaker|audio|"
    r"backlit|backlight|keyboard|fingerprint|numpad|numeric|touchpad|lock|kensington|tpm|"
    r"display|screen|panel|ips|oled|wva|tn|mini-led|nits|brightness|srgb|dci-p3|ntsc|refresh|hz|aspect|resolution|touch|"
    r"memory|ram|ddr4|ddr5|lpddr|mhz|mt/s|slot|so-dimm|soldered|max|"
    r"storage|ssd|nvme|pcie|m\.2"
    r")\b",
    re.IGNORECASE,
)


class WebSpecSearchService:
    """Fetches online hardware specification snippets and tables using Scrapling."""

    def __init__(
        self,
        request_delay: float = 1.0,
        timeout: int = 10,
        max_chars: int = 2200,
    ) -> None:
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_chars = max_chars
        self._last_request_ts: float = 0.0

    def _wait_polite(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_ts = time.time()

    @staticmethod
    def build_search_query(lap: CanonicalLaptop) -> str:
        """Construct a clean search query targeting full laptop chassis and hardware specs."""
        brand = (lap.brand or "").strip()
        model = (lap.laptop_model or "").strip()
        family = (lap.laptop_family or "").strip()

        # Strip brand prefix if duplicated in model
        if brand and model.lower().startswith(brand.lower()):
            model_clean = model[len(brand) :].strip(" -")
        else:
            model_clean = model

        # Clean noisy tokens from model_clean
        model_clean = re.sub(r"\b(gaming|laptop|notebook)\b", "", model_clean, flags=re.IGNORECASE).strip()
        model_clean = re.sub(r"\s+", " ", model_clean)

        base_name = f"{brand} {model_clean}".strip()
        if len(base_name) < 6 and family:
            base_name = f"{brand} {family} {model_clean}".strip()

        return f"{base_name} specifications battery Wh weight kg ports dimensions"

    def fetch_online_specs(self, lap: CanonicalLaptop) -> str:
        """Search DuckDuckGo Lite via Scrapling and scrape spec tables from top results.

        Returns a compacted multi-line string of online specification evidence,
        or an empty string if nothing useful was found.
        """
        try:
            from scrapling.fetchers import Fetcher
        except ImportError:
            logger.warning("scrapling is not installed; skipping online web spec search.")
            return ""

        query = self.build_search_query(lap)
        self._wait_polite()

        try:
            fetcher = Fetcher()
            resp = fetcher.post(
                DDG_LITE_URL,
                data={"q": query},
                timeout=self.timeout,
                retries=1,
            )
        except Exception as e:
            logger.warning("DuckDuckGo Lite search failed for '%s': %s", query, e)
            return ""

        if getattr(resp, "status", 0) != 200:
            logger.warning("DuckDuckGo Lite returned HTTP %s for '%s'", getattr(resp, "status", None), query)
            return ""

        # 1. Extract search snippets and candidate URLs
        collected_lines: list[str] = []
        candidate_urls: list[str] = []

        links = resp.css("a.result-link")
        snippets = resp.css(".result-snippet")

        for idx, link_el in enumerate(links[:8]):
            href = (link_el.attrib.get("href") or "").strip()
            title = link_el.get_all_text(strip=True) if hasattr(link_el, "get_all_text") else (link_el.text or "")
            snippet = ""
            if idx < len(snippets):
                sn_el = snippets[idx]
                snippet = sn_el.get_all_text(strip=True) if hasattr(sn_el, "get_all_text") else (sn_el.text or "")
                snippet = re.sub(r"\s+", " ", snippet).strip()

            if not href or not href.startswith("http"):
                continue

            domain = urlparse(href).netloc.lower()
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue

            if snippet and SPEC_ROW_KEYWORDS.search(snippet):
                collected_lines.append(f"[Search Snippet - {title[:60]}]: {snippet}")

            if not href.lower().endswith(".pdf"):
                candidate_urls.append(href)

        # Sort candidate URLs so PREFERRED_SPEC_DOMAINS come first
        def _url_priority(u: str) -> int:
            dom = urlparse(u).netloc.lower()
            for i, pref in enumerate(PREFERRED_SPEC_DOMAINS):
                if pref in dom:
                    return i
            return 100

        candidate_urls.sort(key=_url_priority)

        # 2. Scrape structured spec rows from up to 2 top candidate pages
        pages_scraped = 0
        for target_url in candidate_urls[:4]:
            if pages_scraped >= 2:
                break
            page_rows = self._scrape_spec_page(fetcher, target_url)
            if page_rows:
                pages_scraped += 1
                domain = urlparse(target_url).netloc.lower()
                collected_lines.append(f"[Source: {domain}]")
                collected_lines.extend(page_rows)

            current_text = "\n".join(collected_lines)
            if len(current_text) >= self.max_chars:
                break

        final_text = "\n".join(collected_lines).strip()
        if len(final_text) > self.max_chars:
            final_text = final_text[: self.max_chars]
        return final_text

    def _scrape_spec_page(self, fetcher: Any, url: str) -> list[str]:
        """Fetch an HTML page with a strict timeout and extract specification rows."""
        self._wait_polite()
        try:
            page = fetcher.get(url, timeout=self.timeout, retries=1)
        except Exception as e:
            logger.debug("Skipping slow/unreachable spec page %s: %s", url, e)
            return []

        if getattr(page, "status", 0) != 200:
            return []

        rows: list[str] = []
        seen: set[str] = set()

        # Extract from <table><tr>
        for tr in page.css("table tr"):
            txt = tr.get_all_text(separator=": ", strip=True) if hasattr(tr, "get_all_text") else (tr.text or "")
            txt = re.sub(r"\s+", " ", txt).strip()
            if 4 <= len(txt) <= 220 and SPEC_ROW_KEYWORDS.search(txt) and txt not in seen:
                seen.add(txt)
                rows.append(txt)
                if len(rows) >= 35:
                    return rows

        # Also check definition lists (<dl><dt>/<dd>) or spec list items (<li>) if table rows were sparse
        if len(rows) < 10:
            for li in page.css("dl div, ul li"):
                txt = li.get_all_text(separator=": ", strip=True) if hasattr(li, "get_all_text") else (li.text or "")
                txt = re.sub(r"\s+", " ", txt).strip()
                if 6 <= len(txt) <= 180 and ":" in txt and SPEC_ROW_KEYWORDS.search(txt) and txt not in seen:
                    seen.add(txt)
                    rows.append(txt)
                    if len(rows) >= 30:
                        break

        return rows
