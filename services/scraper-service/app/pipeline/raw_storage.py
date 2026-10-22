"""Raw scrape archival and loading module.

Saves raw scraped HTML and metadata to disk for auditability,
reproducibility, and offline regression verification.
"""

from __future__ import annotations

import hashlib
import json
from app.common.logger import get_logger
import re
from datetime import datetime, UTC
from pathlib import Path

from app.pipeline.schema import RawScrapedProduct

logger = get_logger(__name__)


class RawScrapeStorage:
    """Manages storage and retrieval of raw scraped PDP artifacts."""

    def __init__(self, base_dir: str = "raw_scrapes") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, product: RawScrapedProduct) -> Path:
        """Save raw product HTML and metadata to disk.

        Returns:
            Path to the saved metadata JSON file.
        """
        store_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", product.store.lower())
        store_dir = self.base_dir / store_slug
        store_dir.mkdir(parents=True, exist_ok=True)

        url_hash = hashlib.sha256(product.url.encode("utf-8")).hexdigest()[:12]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_prefix = f"{timestamp}_{url_hash}"

        html_file = store_dir / f"{file_prefix}.html"
        meta_file = store_dir / f"{file_prefix}.json"

        # 1. Write raw HTML
        html_file.write_text(product.raw_html, encoding="utf-8")

        # 2. Write metadata JSON
        meta_payload = {
            "url": product.url,
            "store": product.store,
            "title": product.title,
            "html_file": str(html_file),
            "price": product.price,
            "currency": product.currency,
            "in_stock": product.in_stock,
            "scraped_at": product.scraped_at,
            "raw_tables": product.raw_tables,
            "raw_sections": product.raw_sections,
        }
        meta_file.write_text(json.dumps(meta_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info("Archived raw scrape for %s to %s", product.url, html_file)
        return meta_file

    def load(self, meta_path: Path) -> RawScrapedProduct:
        """Load a saved raw scrape from its metadata path."""
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        html_file = Path(meta["html_file"])
        raw_html = html_file.read_text(encoding="utf-8") if html_file.exists() else ""

        return RawScrapedProduct(
            url=meta["url"],
            store=meta["store"],
            title=meta["title"],
            raw_html=raw_html,
            raw_tables=meta.get("raw_tables", {}),
            raw_sections=meta.get("raw_sections", {}),
            price=meta.get("price"),
            currency=meta.get("currency", "EGP"),
            in_stock=meta.get("in_stock", True),
            scraped_at=meta.get("scraped_at", ""),
        )
