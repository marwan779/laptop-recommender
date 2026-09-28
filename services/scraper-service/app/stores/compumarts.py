import html
import json
import re
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class CompumartsStoreScraper(BaseStoreScraper):
    """Store scraper for Compumarts Egypt (https://www.compumarts.com).

    Supports:
      1. Level 1: Fast collection crawl extracting catalog cards without secondary HTTP requests.
      2. Level 2: Deep crawl visiting each laptop's PDP to extract Schema.org JSON-LD
         (exact MPN/SKU, offers, availability) and the complete HTML specifications table.
      3. Watermark stopping via `until_model` for incremental scraping (newest added first).
      4. Targeted keyword/model search via /search?type=product&q={query}.
    """

    COLLECTION_BASE_URL = (
        "https://www.compumarts.com/collections/laptop"
        "?sort_by=created-descending&filter.v.availability=1"
    )
    COLLECTION_PAGE_TEMPLATE = (
        "https://www.compumarts.com/collections/laptop"
        "?filter.v.availability=1&sort_by=created-descending&page={page}"
    )

    NON_LAPTOP_KEYWORDS = [
        "backpack", "sleeve", "bag", "adapter", "charger", "cable",
        "mouse", "headset", "earphones", "keyboard", "cooling pad",
        "flash drive", "power bank",
    ]

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
    def store_name(self) -> str:
        return "Compumarts"

    @property
    def store_key(self) -> str:
        return "compumarts"

    @property
    def base_url(self) -> str:
        return "https://www.compumarts.com"

    def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML using Scrapling engine or fallback curl_cffi session."""
        if self.engine:
            try:
                doc = self.engine.fetch(url, stealth=False)
                if doc and doc.html and len(doc.html) > 500:
                    return doc.html
            except Exception:
                pass
        try:
            r = self._session.get(url, headers=self._headers, impersonate="chrome120", timeout=25.0)
            return r.text if r.status_code == 200 else ""
        except Exception as e:
            print(f"[{self.store_name}] Failed to fetch {url}: {e}")
            return ""

    def _matches_watermark(self, identifier: str | None, until_model: str | list[str] | None) -> bool:
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

    def scrape_catalog(
        self,
        level: int = 2,
        until_model: str | list[str] | None = None,
        max_pages: int = 20,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape the canonical in-stock laptops collection sorted by newest first.

        Supports:
          - level=1: Fast catalog card summaries without fetching PDP.
          - level=2: Deep specifications extraction from each product's PDP.
          - until_model: Watermark pointer stopping condition.
        """
        products: list[RetailerProduct] = []
        seen_urls: set[str] = set()
        watermark_hit = False

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )

        print(
            f"[{self.store_name}] Starting Level {level} catalog crawl "
            f"(newest first, in-stock only, until_model='{watermark_display}', max_pages={max_pages}, limit={limit or 'All'})"
        )

        for page in range(1, max_pages + 1):
            if watermark_hit:
                break

            page_url = self.COLLECTION_PAGE_TEMPLATE.format(page=page)
            print(f"[{self.store_name}] Fetching page {page}: {page_url}...")
            html_text = self._fetch_html(page_url)
            if not html_text:
                print(f"[{self.store_name}] Empty response for page {page}. Stopping.")
                break

            soup = BeautifulSoup(html_text, "html.parser")
            cards = soup.find_all("product-card")
            if not cards:
                cards = soup.find_all(attrs={"class": re.compile(r"card--product|grid__item", re.I)})

            if not cards:
                print(f"[{self.store_name}] No product cards found on page {page}. Finished collection crawl.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(cards)} product cards.")

            for card in cards:
                # Pre-check card link and title for watermark before doing any deep work
                link_elem = card.find("a", class_=re.compile(r"card-link|js-prod-link", re.I)) or card.find("a", href=re.compile(r"/products/"))
                if link_elem and until_model:
                    href = link_elem.get("href", "").split("?")[0]
                    card_title = link_elem.get("aria-label", "") or link_elem.get_text(strip=True)
                    handle = href.split("/")[-1]
                    if any(self._matches_watermark(ident, until_model) for ident in [card_title, handle, href]):
                        print(f"[{self.store_name}] Watermark matched '{until_model}' at '{card_title}'. Halting crawl.")
                        watermark_hit = True
                        break

                product = self._parse_card(card, seen_urls, level=level)
                if product:
                    # Also check product SKU / MPN for watermark
                    if until_model and any(self._matches_watermark(ident, until_model) for ident in [product.title, product.retailer_sku, product.mpn]):
                        print(f"[{self.store_name}] Watermark matched '{until_model}' at '{product.title}'. Halting crawl.")
                        watermark_hit = True
                        break

                    products.append(product)
                    specs_info = f"Specs: {len(product.specs)}" if level == 2 else "Level 1 Summary"
                    print(
                        f"  [{len(products)}] {product.title[:55]}... | "
                        f"{product.price_str or 'N/A'} | SKU/MPN: {product.retailer_sku or product.mpn or 'N/A'} | "
                        f"{specs_info}"
                    )

                if limit and len(products) >= limit:
                    break

            if watermark_hit or (limit and len(products) >= limit):
                break

        print(f"[{self.store_name}] Crawl complete. Ingested {len(products)} products (Level {level}).")
        return products

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        """Search store candidates.

        If query is generic (e.g. 'laptop', 'laptops', ''), uses the canonical
        newest in-stock collection with Level 2 extraction. Otherwise, queries /search?type=product&q={query}.
        """
        query_clean = query.strip().lower()
        if query_clean in ("laptop", "laptops", "", "all"):
            return self.scrape_catalog(level=2, limit=limit)

        search_url = f"{self.base_url}/search?type=product&q={quote_plus(query)}"
        print(f"[{self.store_name}] Searching query '{query}': {search_url}")
        html_text = self._fetch_html(search_url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.find_all("product-card")
        if not cards:
            cards = soup.find_all(attrs={"class": re.compile(r"card--product|grid__item", re.I)})

        candidates: list[RetailerProduct] = []
        seen_urls: set[str] = set()

        for card in cards:
            product = self._parse_card(card, seen_urls, level=2)
            if product:
                candidates.append(product)

            if len(candidates) >= limit:
                break

        return candidates

    def _parse_card(
        self,
        card: BeautifulSoup,
        seen_urls: set[str],
        level: int = 2,
    ) -> RetailerProduct | None:
        """Parse a single product-card element and crawl its PDP if level=2."""
        link_elem = card.find("a", class_=re.compile(r"card-link|js-prod-link", re.I)) or card.find("a", href=re.compile(r"/products/"))
        if not link_elem:
            return None

        href = link_elem.get("href", "").split("?")[0]
        full_url = urljoin(self.base_url, href)

        if full_url in seen_urls:
            return None

        # Extract title
        title = ""
        title_elem = card.find(class_=re.compile(r"card__title|title", re.I))
        if title_elem:
            title = title_elem.get_text(strip=True)
        if not title:
            title = link_elem.get("aria-label", "").strip() or link_elem.get_text(strip=True)

        if not title or len(title) < 5:
            return None

        # Filter out non-laptop accessories
        if self._is_standalone_accessory(title):
            return None

        # Extract price
        price_text = None
        price_elem = card.find(class_=re.compile(r"price__current", re.I)) or card.find(class_=re.compile(r"price", re.I))
        if price_elem:
            price_val_elem = price_elem.find(class_="js-value")
            if price_val_elem:
                price_text = price_val_elem.get_text(strip=True)
            else:
                price_text = price_elem.get_text(separator=" ", strip=True)

        price_val, price_str = self.parse_egp_price(price_text)

        # In-stock check
        sold_out_elem = card.find(class_=re.compile(r"product-label--sold-out|sold-out", re.I))
        in_stock = sold_out_elem is None and "sold out" not in card.get_text().lower()

        # Extract thumbnail image
        thumbnail_url = None
        img_elem = card.find("img")
        if img_elem:
            src = img_elem.get("src") or img_elem.get("data-src", "")
            if src.startswith("//"):
                src = "https:" + src
            thumbnail_url = urljoin(self.base_url, src)

        seen_urls.add(full_url)

        # ---------------------------------------------------------------------
        # Level 1 vs Level 2 Branching
        # ---------------------------------------------------------------------
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        pdp_sku: str | None = None

        if level == 2:
            # Level 2: Deep Product Detail Page (PDP) Extraction
            specs, raw_desc, pdp_price_val, pdp_price_str, pdp_sku, pdp_in_stock = (
                self._extract_product_specs(full_url)
            )
            if pdp_price_val is not None:
                price_val, price_str = pdp_price_val, pdp_price_str
            if pdp_in_stock is not None:
                in_stock = pdp_in_stock

        # Normalization and model token extraction
        combined_text = f"{title} {pdp_sku or ''} {' '.join(specs.values())}"
        tokens = ModelNormalizer.extract_model_tokens(combined_text)

        retailer_product_id = href.split("/")[-1]
        mpn = pdp_sku or tokens.get("mpn")
        model_code = tokens.get("full_sku") or tokens.get("base_model")

        return RetailerProduct(
            store_name=self.store_name,
            store_key=self.store_key,
            store_domain=self.base_domain,
            title=title,
            product_url=full_url,
            retailer_product_id=retailer_product_id,
            retailer_sku=pdp_sku or retailer_product_id,
            mpn=mpn,
            model_code=model_code,
            sub_model=tokens.get("sub_model"),
            base_model=tokens.get("base_model"),
            price_egp=price_val,
            price_str=price_str,
            in_stock=in_stock,
            thumbnail_url=thumbnail_url,
            specs=specs,
            raw_description=raw_desc,
        )

    def _extract_product_specs(
        self, product_url: str
    ) -> tuple[dict[str, str], str | None, float | None, str | None, str | None, bool | None]:
        """Fetch PDP to extract Schema.org Product JSON-LD, specs table, and description.

        Returns:
            (specs, raw_description, price_val, price_str, sku, in_stock)
        """
        html_text = self._fetch_html(product_url)
        if not html_text:
            return {}, None, None, None, None, None

        soup = BeautifulSoup(html_text, "html.parser")
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        sku: str | None = None
        in_stock: bool | None = None

        # 1. Parse Schema.org Product JSON-LD
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if data.get("@type") == "Product":
                    sku = data.get("sku")
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        raw_p = offers.get("price")
                        if raw_p:
                            price_val, price_str = self.parse_egp_price(str(raw_p))
                        avail = offers.get("availability", "")
                        if "InStock" in avail:
                            in_stock = True
                        elif "OutOfStock" in avail:
                            in_stock = False
                    raw_desc = data.get("description")
                    break
            except Exception:
                pass

        # 2. Parse Specifications Tables
        tables = soup.find_all("table")
        for tbl in tables:
            for row in tbl.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    k = cells[0].get_text(separator=" ", strip=True)
                    v = cells[1].get_text(separator=" ", strip=True)
                    # Clean up footnote symbols and spaces
                    k = re.sub(r"[:\*]+$", "", k).strip()
                    v = html.unescape(v).replace("\xa0", " ").strip()
                    if k and v and len(k) < 60 and k.lower() != "category":
                        specs[k] = v

        # 3. Fallback description from RTE content
        if not raw_desc:
            desc_elem = soup.find(class_=re.compile(r"product-description|rte", re.I))
            if desc_elem:
                raw_desc = desc_elem.get_text(separator="\n", strip=True)[:1000]

        return specs, raw_desc, price_val, price_str, sku, in_stock
