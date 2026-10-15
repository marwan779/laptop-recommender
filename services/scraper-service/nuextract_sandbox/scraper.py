import re
from typing import Any
from bs4 import BeautifulSoup
from app.stores.compumarts import CompumartsStoreScraper

class PDPScraper:
    """Layer 1: Fetch live PDP HTML using production CompumartsStoreScraper (with TLS impersonation and PatternEngine)."""

    def __init__(self, timeout_s: float = 25.0):
        self.store_scraper = CompumartsStoreScraper()

    def fetch_pdp(self, url: str) -> dict[str, Any]:
        """Fetch live PDP and extract complete un-sanitized raw table rows and metadata."""
        # 1. Fetch raw HTML to get exact title
        html_text = self.store_scraper._fetch_html(url)
        if not html_text:
            raise RuntimeError(f"Failed to fetch HTML from {url}")

        soup = BeautifulSoup(html_text, "html.parser")
        title = ""
        title_tag = soup.find("h1", class_=lambda c: c and ("product" in c.lower() or "title" in c.lower()))
        if not title_tag:
            title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)
        elif soup.title:
            title = soup.title.get_text(strip=True).split("–")[0].split("-")[0].strip()

        # 2. Extract complete 60+ spec table rows via PatternEngine
        spec_res = self.store_scraper._extract_product_specs(url, title=title)
        raw_specs = spec_res.specs or {}

        # 3. Metadata
        metadata = {
            "sku": spec_res.sku,
            "price_egp": spec_res.price_val,
            "price_str": spec_res.price_str,
            "in_stock": spec_res.in_stock,
        }

        return {
            "url": url,
            "title": title,
            "raw_specs": raw_specs,
            "raw_description": spec_res.raw_description or "",
            "metadata": metadata,
        }

