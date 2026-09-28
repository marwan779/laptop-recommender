import re
from abc import ABC, abstractmethod
from typing import Sequence
from urllib.parse import urlparse

from app.engine.base import IScraperEngine
from app.matching.normalizer import ModelNormalizer
from app.schemas.laptop import ConfigurationItem, RetailerProduct


class BaseStoreScraper(ABC):
    """Abstract base class for Egyptian retail store candidate searchers."""

    NON_LAPTOP_KEYWORDS = [
        "backpack", "sleeve", "bag", "cover", "case", "adapter", "charger",
        "cable", "mouse", "headset", "earphones", "keyboard", "cooling pad",
        "laptop stand", "flash drive", "power bank", "docking",
    ]

    def __init__(self, engine: IScraperEngine):
        self.engine = engine

    @classmethod
    def _is_standalone_accessory(cls, title: str) -> bool:
        """Check if an item is purely an accessory and not a laptop or laptop bundle."""
        t = title.lower()
        # If it has core laptop hardware specs, it is definitely a computer/laptop (or bundle)
        has_cpu = bool(re.search(r"\b(i[3579]|ryzen|core\s*ultra|intel|amd|celeron|athlon)\b", t))
        has_specs = bool(re.search(r"\b(\d+\s*gb|ssd|nvme|fhd|ips|oled|wuxga|ddr\d?|rtx|gtx|radeon|geforce)\b", t))
        if has_cpu and has_specs:
            return False

        # If it contains accessory keywords without core laptop hardware, it is an accessory
        for acc in cls.NON_LAPTOP_KEYWORDS:
            if acc in t:
                # Special case: 'keyboard' in a laptop title usually refers to the built-in keyboard layout
                if acc == "keyboard":
                    if any(layout in t for layout in ["keyboard english", "keyboard arabic", "backlit", "rgb", "layout"]):
                        continue
                return True
        return False

    @staticmethod
    def _matches_watermark(identifier: str | None, until_model: str | list[str] | None) -> bool:
        """Check if any target watermark matches the product identifier."""
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

    @property
    @abstractmethod
    def store_name(self) -> str:
        """Display name of the store (e.g., 'Compumarts')."""
        pass

    @property
    @abstractmethod
    def store_key(self) -> str:
        """Machine-friendly slug (e.g., 'compumarts')."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base website URL (e.g., 'https://www.compumarts.com')."""
        pass

    @property
    def base_domain(self) -> str:
        """Domain of the store website without www (e.g., 'compumarts.com')."""
        return urlparse(self.base_url).netloc.replace("www.", "")

    @abstractmethod
    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        """Execute a store-specific search query and return raw candidate RetailerProducts."""
        pass

    def scrape_catalog(
        self,
        level: int = 2,
        until_model: str | list[str] | None = None,
        max_pages: int = 5,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape store catalog with Level 1 (fast summaries) or Level 2 (deep specs) and watermark stopping."""
        return self.search_candidates(query="laptop", limit=limit or 20)

    def collect_store_candidates(
        self,
        queries: Sequence[str],
        max_candidates: int = 20,
    ) -> list[RetailerProduct]:
        """Execute queries to collect candidates.

        Does NOT stop after the first successful query.
        Collects all candidates across useful queries and deduplicates them.
        """
        all_raw_candidates: list[RetailerProduct] = []
        for q in queries:
            try:
                candidates = self.search_candidates(q, limit=5)
                if candidates:
                    print(f"[{self.store_name}] Query '{q}' returned {len(candidates)} candidate(s)")
                    all_raw_candidates.extend(candidates)
                else:
                    print(f"[{self.store_name}] Query '{q}' returned 0 candidates")
            except Exception as e:
                print(f"[{self.store_name}] Search error for query '{q}': {e}")
                continue

            if len(all_raw_candidates) >= max_candidates:
                break

        # Deduplicate candidates across queries
        deduped = self.deduplicate_candidates(all_raw_candidates)
        print(f"[{self.store_name}] Total unique candidates collected: {len(deduped)}")
        return deduped

    @staticmethod
    def build_candidate_queries(
        brand: str,
        family_name: str,
        base_model: str | None,
        configurations: Sequence[ConfigurationItem],
    ) -> list[str]:
        """Generate a prioritized list of search queries covering all target configurations.

        Priority order:
        1. Full configuration SKUs (e.g. 'S3407AA-SF117W', 'S3407CA-LY065W')
        2. Sub-model series (e.g. 'S3407AA', 'S3407CA')
        3. Base model (e.g. 'S3407', 'ASUS S3407')
        4. Family + Model / Clean Name
        """
        queries: list[str] = []

        # 1. Full SKUs & Sub-models from configurations
        for config in configurations:
            model_code = config.model.strip()
            if len(model_code) >= 4 and not model_code.isdigit():
                queries.append(model_code)
                queries.append(f"{brand} {model_code}")

            if config.model_series and config.model_series != model_code:
                series = config.model_series.strip()
                if len(series) >= 4:
                    queries.append(series)
                    queries.append(f"{brand} {series}")

            if config.mpn:
                queries.append(config.mpn.strip())

        # 2. Base model queries
        if base_model and len(base_model) >= 4:
            queries.append(f"{brand} {base_model}")
            queries.append(base_model)

        # 3. Family + model
        clean_family = re.sub(r"\(.*?\)", "", family_name).strip()
        if base_model and clean_family:
            queries.append(f"{clean_family} {base_model}")

        # 4. Clean family name alone (broader candidate query)
        if clean_family:
            queries.append(clean_family)

        # Deduplicate queries preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            q_clean = q.strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                unique_queries.append(q_clean)

        return unique_queries

    @classmethod
    def deduplicate_candidates(cls, candidates: list[RetailerProduct]) -> list[RetailerProduct]:
        """Deduplicate candidates from multiple queries using:

        1. retailer_product_id / SKU
        2. canonical product URL (query params stripped)
        3. normalized title + MPN
        """
        seen_keys: set[str] = set()
        unique_candidates: list[RetailerProduct] = []

        for p in candidates:
            # 1. Check product URL without query params
            clean_url = urlparse(p.product_url)._replace(query="", fragment="").geturl().rstrip("/")

            # Keys to check
            keys = [f"url:{clean_url.lower()}"]
            if p.retailer_product_id:
                keys.append(f"id:{p.retailer_product_id.lower()}")
            if p.retailer_sku:
                keys.append(f"sku:{p.retailer_sku.lower()}")
            if p.mpn:
                keys.append(f"mpn:{ModelNormalizer.normalize_mpn(p.mpn)}")

            # Check if any key was seen
            if any(k in seen_keys for k in keys):
                continue

            for k in keys:
                seen_keys.add(k)
            unique_candidates.append(p)

        return unique_candidates

    @staticmethod
    def parse_egp_price(price_text: str | None) -> tuple[float | None, str | None]:
        """Extract float numeric value and normalized EGP string from price text.

        Handles formats like:
        '54,999.00 EGP', 'EGP 54,999', '54.999 ج.م', '54,999 L.E.', 'جنيه 61,999'
        """
        if not price_text:
            return None, None

        # Normalize Arabic digits if present
        arabic_to_eng = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        clean = price_text.translate(arabic_to_eng)

        # Extract digits with optional commas/dots
        match = re.search(r"([\d,]+(?:\.\d{2})?)", clean)
        if not match:
            return None, price_text.strip()

        num_str = match.group(1).replace(",", "")
        try:
            val = float(num_str)
            formatted = f"{val:,.2f} EGP"
            return val, formatted
        except ValueError:
            return None, price_text.strip()
