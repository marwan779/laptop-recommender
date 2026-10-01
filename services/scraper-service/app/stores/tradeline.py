import html
import itertools
import json
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class TradelineStoreScraper(BaseStoreScraper):
    """Store scraper for Tradeline Egypt (https://tradelinestores.com).

    Tradeline is the premier Apple Authorized Reseller in Egypt.
    Features:
      - CMS / Platform: Shopify
      - Catalog Endpoints:
          /collections/{collection}/products.json?sort_by=created-descending&page={page}&limit=250
          /collections/{collection}?sort_by=created-descending&page={page}
      - Multi-Variant Support: Handles configurable options (RAM, SSD, Color, CPU cores).
      - Sorting: Chronological newest-first order (`sort_by=created-descending`).
      - Level 1: Fast catalog JSON/card summaries.
      - Level 2: Deep specifications extraction from PDP and specs sheets.
      - Watermark stopping: Dual pre-enrichment and post-enrichment checks via `until_model`.
    """

    BASE_URL = "https://tradelinestores.com"
    COLLECTIONS = ["macbook-air", "macbook-pro", "macbook-neo"]
    COLLECTION_JSON_TEMPLATE = (
        "https://tradelinestores.com/collections/{collection}/products.json"
        "?sort_by=created-descending&page={page}&limit=250"
    )
    COLLECTION_HTML_TEMPLATE = (
        "https://tradelinestores.com/collections/{collection}?sort_by=created-descending&page={page}"
    )

    NON_LAPTOP_KEYWORDS = [
        "backpack",
        "sleeve",
        "bag",
        "adapter",
        "charger",
        "cable",
        "mouse",
        "magic mouse",
        "headset",
        "earphones",
        "airpods",
        "power adapter",
        "magsafe charger",
        "screen protector",
        "case",
        "hub",
        "dock",
        "pencil",
        "keyboard cover",
    ]

    def __init__(self, engine: IScraperEngine | None = None):
        super().__init__(engine=engine or None)
        self._session = cffi_requests.Session()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @property
    def store_name(self) -> str:
        return "Tradeline"

    @property
    def store_key(self) -> str:
        return "tradeline"

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    @property
    def base_domain(self) -> str:
        return "tradelinestores.com"

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
            print(f"[{self.store_name}] Failed to fetch HTML {url}: {e}")
            return ""

    def _fetch_json(self, url: str) -> dict[str, Any] | None:
        """Fetch JSON endpoint using curl_cffi."""
        try:
            r = self._session.get(url, headers=self._headers, impersonate="chrome120", timeout=25.0)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[{self.store_name}] Failed to fetch JSON {url}: {e}")
        return None

    def scrape_catalog(
        self,
        level: int = 1,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape Tradeline MacBooks catalog with Level 1/2 extraction and watermark stopping.

        Args:
            level: 1 for fast catalog summaries, 2 for deep PDP spec crawling.
            until_model: Watermark pointer (name, MPN, SKU, or slug). Halts crawling when matched.
            max_pages: Maximum pages per collection. None for full pagination.
            limit: Maximum items to return across all collections. None for unlimited.
        """
        products: list[RetailerProduct] = []
        seen_variants: set[str] = set()
        watermark_hit = False

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )
        max_pages_display = str(max_pages) if max_pages else "Unlimited (All Pages)"

        print(
            f"[{self.store_name}] Starting Level {level} catalog crawl "
            f"(newest first, collections={self.COLLECTIONS}, until_model='{watermark_display}', "
            f"max_pages={max_pages_display}, limit={limit or 'All'})"
        )

        for collection in self.COLLECTIONS:
            if watermark_hit or (limit and len(products) >= limit):
                break

            print(f"[{self.store_name}] Crawling collection: '{collection}'...")

            for page in itertools.count(1):
                if max_pages and page > max_pages:
                    break
                if watermark_hit or (limit and len(products) >= limit):
                    break

                json_url = self.COLLECTION_JSON_TEMPLATE.format(collection=collection, page=page)
                data = self._fetch_json(json_url)
                items = data.get("products", []) if data else []

                # Fallback to HTML if JSON returns empty on page 1
                if not items and page == 1:
                    print(f"[{self.store_name}] JSON empty for '{collection}', attempting HTML fallback...")
                    html_products = self._scrape_collection_html(
                        collection, page=page, level=level, until_model=until_model
                    )
                    for hp in html_products:
                        if hp.retailer_sku not in seen_variants:
                            seen_variants.add(hp.retailer_sku)
                            products.append(hp)
                            if limit and len(products) >= limit:
                                break
                    break

                if not items:
                    print(f"[{self.store_name}] Reached end of collection '{collection}' at page {page}.")
                    break

                print(f"[{self.store_name}] Page {page}: processing {len(items)} products...")

                for item in items:
                    title = item.get("title", "").strip()
                    handle = item.get("handle", "").strip()
                    product_url = urljoin(self.base_url, f"/products/{handle}")

                    # 1. Filter out accessories
                    if self._is_standalone_accessory(title):
                        self.record_skipped(
                            name=title,
                            reason="Filtered out non-laptop accessory or peripheral",
                            url=product_url,
                            stage="level1_filter",
                        )
                        continue

                    # 2. Iterate through all variants (changeable options: RAM, SSD, Color, CPU)
                    variants = item.get("variants", [])
                    if not variants:
                        variants = [{"id": item.get("id"), "title": "Default Title", "price": 0, "available": True}]

                    for variant in variants:
                        variant_id = str(variant.get("id"))
                        variant_sku = (variant.get("sku") or "").strip()
                        variant_title = variant.get("title") or ""

                        if variant_id in seen_variants or (variant_sku and variant_sku in seen_variants):
                            continue

                        # 3. Dual Watermark Check (Pre-enrichment)
                        if until_model and any(
                            self._matches_watermark(ident, until_model)
                            for ident in [title, handle, variant_sku, variant_title]
                        ):
                            print(
                                f"[{self.store_name}] Watermark matched '{until_model}' "
                                f"at product '{title}' (SKU: {variant_sku}). Halting crawl."
                            )
                            watermark_hit = True
                            break

                        product = self._parse_product_variant(
                            item=item,
                            variant=variant,
                            collection=collection,
                            level=level,
                        )

                        if not product:
                            self.record_skipped(
                                name=f"{title} - {variant_title}",
                                reason="Product variant could not be parsed or zero/invalid price",
                                url=product_url,
                                stage="level1_parse",
                            )
                            continue

                        # 4. Dual Watermark Check (Post-enrichment on discovered MPN / SKU)
                        if until_model and any(
                            self._matches_watermark(ident, until_model)
                            for ident in [product.mpn, product.retailer_sku, product.model_code]
                        ):
                            print(
                                f"[{self.store_name}] Watermark matched '{until_model}' "
                                f"at MPN/SKU '{product.mpn}'. Halting crawl."
                            )
                            watermark_hit = True
                            break

                        seen_variants.add(variant_id)
                        if variant_sku:
                            seen_variants.add(variant_sku)
                        products.append(product)

                        specs_info = f"Specs: {len(product.specs)}" if level == 2 else "L1 Summary"
                        print(
                            f"  [{len(products)}] {product.title[:50]}... | "
                            f"{product.price_str or 'N/A'} | SKU/MPN: {product.retailer_sku or product.mpn or 'N/A'} | "
                            f"{specs_info}"
                        )

                        if limit and len(products) >= limit:
                            break

                    if watermark_hit or (limit and len(products) >= limit):
                        break

        print(f"[{self.store_name}] Crawl complete. Ingested {len(products)} products (Level {level}).")
        return products

    def _parse_product_variant(
        self,
        item: dict[str, Any],
        variant: dict[str, Any],
        collection: str,
        level: int = 1,
    ) -> RetailerProduct | None:
        """Parse a single Shopify variant into a RetailerProduct."""
        base_title = item.get("title", "").strip()
        handle = item.get("handle", "").strip()
        variant_title = (variant.get("title") or "").strip()

        # Build descriptive title if variant has custom attributes (e.g. Color, Storage)
        if variant_title and variant_title.lower() != "default title" and variant_title not in base_title:
            title = f"{base_title} - {variant_title}"
        else:
            title = base_title

        if self._is_standalone_accessory(title):
            return None

        # Price parsing
        raw_price = variant.get("price")
        price_val: float | None = None
        price_str: str | None = None
        if raw_price is not None:
            # Shopify API sometimes returns cents or decimal strings
            try:
                p_float = float(raw_price)
                # If price is suspiciously large without decimals (e.g. 19550000 cents), normalize
                if p_float > 1_000_000 and ".00" not in str(raw_price):
                    p_float /= 100.0
                price_val = p_float
                price_str = f"{price_val:,.2f} EGP"
            except Exception:
                price_val, price_str = self.parse_egp_price(str(raw_price))

        in_stock = bool(variant.get("available", True))
        variant_sku = (variant.get("sku") or "").strip()
        product_url = urljoin(self.base_url, f"/products/{handle}")
        retailer_product_id = f"{item.get('id')}_{variant.get('id')}"

        # Image thumbnail
        thumbnail_url = None
        images = item.get("images", [])
        if images:
            thumbnail_url = images[0].get("src")

        # Initial specs parsed from title, tags, and product type
        specs: dict[str, str] = {}
        for tag in item.get("tags", []):
            tag_clean = tag.strip()
            if any(
                k in tag_clean.lower()
                for k in ["ssd", "ram", "cpu", "gpu", "chip", "inch", "m1", "m2", "m3", "m4", "m5"]
            ):
                specs[f"Tag_{tag_clean}"] = tag_clean

        # Extract specs using regex from title (Chip, RAM, SSD, Screen, Color)
        self._extract_specs_from_title(title, specs)

        raw_desc: str | None = item.get("body_html")

        # Level 2 deep extraction
        pdp_sku: str | None = None
        if level == 2:
            pdp_specs, pdp_desc, pdp_price_val, pdp_price_str, pdp_sku, pdp_in_stock = self._extract_product_specs(
                product_url
            )
            specs.update(pdp_specs)
            if pdp_desc:
                raw_desc = pdp_desc
            if pdp_price_val is not None:
                price_val, price_str = pdp_price_val, pdp_price_str
            if pdp_in_stock is not None:
                in_stock = pdp_in_stock

        # Extract model tokens and MPN
        combined_text = f"{title} {variant_sku} {pdp_sku or ''} {' '.join(specs.values())}"
        tokens = ModelNormalizer.extract_model_tokens(combined_text)

        # Apple part number (MPN): e.g. MGEA4AE/A, MDHE4AE/A
        mpn = variant_sku or pdp_sku or tokens.get("mpn")
        # Try to find Apple MPN pattern from title or handle if still missing
        if not mpn:
            mpn_match = re.search(r"\b([A-Z0-9]{4,6}[A-Z]{2}/[A-Z])\b", f"{title} {handle.upper()}")
            if mpn_match:
                mpn = mpn_match.group(1)

        model_code = tokens.get("full_sku") or mpn or tokens.get("base_model")

        return RetailerProduct(
            store_name=self.store_name,
            store_key=self.store_key,
            store_domain=self.base_domain,
            title=title,
            product_url=product_url,
            retailer_product_id=retailer_product_id,
            retailer_sku=variant_sku or mpn or str(item.get("id")),
            mpn=mpn,
            model_code=model_code,
            sub_model=tokens.get("sub_model") or item.get("product_type"),
            base_model=tokens.get("base_model") or "MacBook",
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
        """Fetch PDP to extract specifications, Schema.org JSON-LD, and descriptions.

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
                    sku = data.get("sku") or sku
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

        # 2. Extract from Shopify JS analytics meta script if present
        meta_match = re.search(r"var meta\s*=\s*(\{.*?\});", html_text, re.DOTALL)
        if meta_match:
            try:
                meta_json = json.loads(meta_match.group(1))
                prod_meta = meta_json.get("product", {})
                for v in prod_meta.get("variants", []):
                    if v.get("sku"):
                        sku = v.get("sku")
                        break
            except Exception:
                pass

        # 3. Parse Specifications Table / Accordions / DL lists
        for tbl in soup.find_all("table"):
            for row in tbl.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    k = cells[0].get_text(separator=" ", strip=True)
                    v = cells[1].get_text(separator=" ", strip=True)
                    k = re.sub(r"[:\*]+$", "", k).strip()
                    v = html.unescape(v).replace("\xa0", " ").strip()
                    if k and v and len(k) < 60:
                        specs[k] = v

        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds, strict=False):
                k = dt.get_text(strip=True).rstrip(":")
                v = dd.get_text(strip=True)
                if k and v and len(k) < 60:
                    specs[k] = v

        # 4. Fallback description from RTE content
        if not raw_desc:
            desc_elem = soup.find(class_=re.compile(r"product__description|product-description|rte", re.I))
            if desc_elem:
                raw_desc = desc_elem.get_text(separator="\n", strip=True)[:1500]

        return specs, raw_desc, price_val, price_str, sku, in_stock

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        """Search Tradeline candidates using Shopify Predictive Search API.

        If query is generic (e.g. 'macbook', 'laptop'), falls back to catalog crawl.
        """
        query_clean = query.strip().lower()
        if query_clean in ("laptop", "laptops", "macbook", "mac", "", "all"):
            return self.scrape_catalog(level=2, limit=limit)

        search_url = (
            f"{self.base_url}/search/suggest.json"
            f"?q={quote_plus(query)}&resources[type]=product&resources[limit]={limit * 2}"
        )
        print(f"[{self.store_name}] Searching query '{query}': {search_url}")

        data = self._fetch_json(search_url)
        candidates: list[RetailerProduct] = []

        if data and "resources" in data:
            results = data.get("resources", {}).get("results", {}).get("products", [])
            for item in results:
                title = item.get("title", "")
                handle = item.get("handle", "")
                product_url = urljoin(self.base_url, item.get("url") or f"/products/{handle}")

                if self._is_standalone_accessory(title):
                    self.record_skipped(
                        name=title,
                        reason="Filtered out non-laptop accessory or peripheral",
                        url=product_url,
                        stage="search_filter",
                    )
                    continue

                # Fetch Level 2 details for candidates
                specs, raw_desc, p_val, p_str, sku, in_stock = self._extract_product_specs(product_url)
                if p_val is None and item.get("price"):
                    p_val, p_str = self.parse_egp_price(str(item.get("price")))

                tokens = ModelNormalizer.extract_model_tokens(f"{title} {sku or ''}")

                product = RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain=self.base_domain,
                    title=title,
                    product_url=product_url,
                    retailer_product_id=str(item.get("id")),
                    retailer_sku=sku or str(item.get("id")),
                    mpn=sku or tokens.get("mpn"),
                    model_code=tokens.get("full_sku") or tokens.get("base_model"),
                    sub_model=tokens.get("sub_model"),
                    base_model=tokens.get("base_model") or "MacBook",
                    price_egp=p_val,
                    price_str=p_str,
                    in_stock=in_stock if in_stock is not None else True,
                    thumbnail_url=item.get("image"),
                    specs=specs,
                    raw_description=raw_desc,
                )
                candidates.append(product)
                if len(candidates) >= limit:
                    break

        # Fallback to HTML search if Predictive Search gave 0 results
        if not candidates:
            html_search_url = f"{self.base_url}/search?type=product&q={quote_plus(query)}"
            html_text = self._fetch_html(html_search_url)
            if html_text:
                soup = BeautifulSoup(html_text, "html.parser")
                for a in soup.find_all("a", href=re.compile(r"/products/")):
                    t = a.get_text(strip=True)
                    if t and not self._is_standalone_accessory(t) and len(t) > 5:
                        p_url = urljoin(self.base_url, a.get("href", "").split("?")[0])
                        p_sku = p_url.split("/")[-1]
                        candidates.append(
                            RetailerProduct(
                                store_name=self.store_name,
                                store_key=self.store_key,
                                store_domain=self.base_domain,
                                title=t,
                                product_url=p_url,
                                retailer_product_id=p_sku,
                                retailer_sku=p_sku,
                                in_stock=True,
                            )
                        )
                        if len(candidates) >= limit:
                            break

        return candidates

    def _scrape_collection_html(
        self,
        collection: str,
        page: int = 1,
        level: int = 1,
        until_model: str | list[str] | None = None,
    ) -> list[RetailerProduct]:
        """Fallback method to scrape collection via standard HTML if JSON is unavailable."""
        url = self.COLLECTION_HTML_TEMPLATE.format(collection=collection, page=page)
        html_text = self._fetch_html(url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        products: list[RetailerProduct] = []

        cards = soup.find_all(attrs={"class": re.compile(r"card--product|product-card|grid__item", re.I)})
        for card in cards:
            link = card.find("a", href=re.compile(r"/products/"))
            if not link:
                continue
            href = link.get("href", "").split("?")[0]
            full_url = urljoin(self.base_url, href)

            title_elem = card.find(class_=re.compile(r"title|name", re.I)) or link
            title = title_elem.get_text(strip=True)
            if not title:
                continue
            if self._is_standalone_accessory(title):
                self.record_skipped(
                    name=title,
                    reason="Filtered out non-laptop accessory or peripheral",
                    url=full_url,
                    stage="html_fallback_filter",
                )
                continue

            price_elem = card.find(class_=re.compile(r"price", re.I))
            price_text = price_elem.get_text(strip=True) if price_elem else None
            price_val, price_str = self.parse_egp_price(price_text)

            sku = href.split("/")[-1]
            products.append(
                RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain=self.base_domain,
                    title=title,
                    product_url=full_url,
                    retailer_product_id=sku,
                    retailer_sku=sku,
                    price_egp=price_val,
                    price_str=price_str,
                    in_stock=True,
                )
            )

        return products

    @staticmethod
    def _extract_specs_from_title(title: str, specs: dict[str, str]) -> None:
        """Extract Apple hardware specifications from product title using regex."""
        # Screen size: e.g. 13-inch, 14-inch, 16-inch
        screen_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|\s*)inch", title, re.I)
        if screen_m:
            specs["Display_Size"] = f"{screen_m.group(1)}-inch"

        # Processor / Chip: Apple M1, M2, M3, M4, M5, Pro, Max
        chip_m = re.search(r"(Apple\s+M\d+(?:\s+(?:Pro|Max))?)\s+chip", title, re.I)
        if chip_m:
            specs["Processor"] = chip_m.group(1).strip()
        else:
            m_chip = re.search(r"\b(M\d+(?:\s+(?:Pro|Max))?)\b", title, re.I)
            if m_chip:
                specs["Processor"] = f"Apple {m_chip.group(1).strip()}"

        # CPU / GPU cores: e.g. 10-core CPU and 10-core GPU
        cpu_gpu_m = re.search(r"(\d+)-core\s+CPU\s+and\s+(\d+)-core\s+GPU", title, re.I)
        if cpu_gpu_m:
            specs["CPU_Cores"] = f"{cpu_gpu_m.group(1)}-core"
            specs["GPU_Cores"] = f"{cpu_gpu_m.group(2)}-core"

        # RAM / Unified Memory: e.g. 16GB RAM, 24GB Unified Memory (prevent matching SSD)
        ram_m = re.search(r"\b(\d+GB)\s*(?:Unified\s+Memory|RAM|Memory)\b", title, re.I)
        if not ram_m:
            # Fallback: check if there's a standalone GB not followed by SSD
            standalone_gb = re.findall(r"\b(\d+GB)\b(?!\s*SSD)", title, re.I)
            if standalone_gb:
                specs["RAM"] = standalone_gb[0]
        else:
            specs["RAM"] = ram_m.group(1)

        # Storage / SSD: e.g. 256GB SSD, 512GB SSD, 1TB SSD, 2TB SSD
        ssd_m = re.search(r"\b(\d+(?:GB|TB))\s*SSD\b", title, re.I)
        if ssd_m:
            specs["Storage"] = f"{ssd_m.group(1)} SSD"

        # Color: Space Black, Silver, Space Gray, Midnight, Starlight
        color_m = re.search(r"-\s*(Space Black|Silver|Space Gray|Midnight|Starlight|Gold)\b", title, re.I)
        if color_m:
            specs["Color"] = color_m.group(1).strip()
