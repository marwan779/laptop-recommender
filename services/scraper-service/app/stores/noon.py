import html
import itertools
import json
import re
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class NoonStoreScraper(BaseStoreScraper):
    """Store scraper for Noon Egypt (https://www.noon.com/egypt-en/).

    Supports:
      - Level 1: Fast catalog parsing using Next.js __NEXT_DATA__ JSON script tags or HTML fallback.
      - Level 2: Deep PDP specification extraction from Noon NEXT_DATA product details or specifications tables.
      - Watermark stopping via `until_model` for incremental scraping (sorted by newest/created_at).
      - Candidate search via `https://www.noon.com/egypt-en/search/?q={query}`.
    """

    CATALOG_URL_TEMPLATE = (
        "https://www.noon.com/egypt-en/electronics-and-mobiles/computers-and-accessories/laptops-and-notebooks/"
        "?sort%5Bby%5D=created_at&sort%5Bdir%5D=desc&page={page}"
    )
    CATALOG_API_TEMPLATE = (
        "https://www.noon.com/_svc/catalog/api/v3/u/egypt-en/electronics-and-mobiles/computers-and-accessories/laptops-and-notebooks/"
        "?sort[by]=created_at&sort[dir]=desc&page={page}"
    )
    SEARCH_URL_TEMPLATE = (
        "https://www.noon.com/egypt-en/search/?q={query}"
    )
    SEARCH_API_TEMPLATE = (
        "https://www.noon.com/_svc/catalog/api/v3/u/egypt-en/search/?q={query}&page=1"
    )

    NON_LAPTOP_KEYWORDS = [
        "backpack", "sleeve", "bag", "cover", "case", "adapter", "charger",
        "cable", "mouse", "headset", "earphones", "keyboard", "cooling pad",
        "laptop stand", "flash drive", "power bank", "docking", "privacy screen",
        "screen protector", "hub", "dongle", "stylus", "pen", "printer",
        "monitor", "desktop", "all-in-one", "all in one", "projector", "tablet", "ipad", "tv",
        "extender", "router", "hard disk", "hard drive", "external hard", "external hdd", "webcam",
        "memory card", "sd card", "microsd", "micsd", "sdxc", "flash", "usb drive", "mac mini", "mini pc", "thermal paste",
        "cooler", "cooling", "microphone", "mic", "sata ssd", "internal ssd", "nvme ssd", "m.2 ssd", "portable ssd", "external ssd",
        "cartridge", "toner", "drum unit", "ink tank", "ribbon",
    ]

    def __init__(self, engine: IScraperEngine | None = None):
        super().__init__(engine=engine or None)
        self._session = cffi_requests.Session()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "x-platform": "web",
            "x-locale": "en-eg",
        }

    @property
    def store_name(self) -> str:
        return "Noon"

    @property
    def store_key(self) -> str:
        return "noon"

    @property
    def base_url(self) -> str:
        return "https://www.noon.com"

    @property
    def base_domain(self) -> str:
        return "noon.com"

    def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML using Scrapling engine or fallback curl_cffi session."""
        if self.engine:
            try:
                doc = self.engine.fetch(url, stealth=True)
                if (
                    doc
                    and doc.html
                    and len(doc.html) > 500
                    and "sec-if-cpt-container" not in doc.html
                    and "akamai" not in doc.html.lower()
                ):
                    return doc.html
            except Exception:
                pass
        try:
            r = self._session.get(url, headers=self._headers, impersonate="chrome120", timeout=25.0)
            if r.status_code == 200 and "sec-if-cpt-container" not in r.text:
                return r.text
            return ""
        except Exception as e:
            print(f"[{self.store_name}] Failed to fetch {url}: {e}")
            return ""

    def _fetch_catalog_api(self, page: int = 1) -> list[dict]:
        """Fetch catalog directly from Noon's catalog REST API, bypassing Akamai web challenge."""
        url = self.CATALOG_API_TEMPLATE.format(page=page)
        try:
            headers = dict(self._headers)
            headers["Accept"] = "application/json, text/plain, */*"
            r = self._session.get(url, headers=headers, impersonate="chrome120", timeout=25.0)
            if r.status_code == 200:
                data = r.json()
                hits = data.get("hits", [])
                raw_items: list[dict] = []
                for h in hits:
                    pdp_path = h.get("pdp_url") or h.get("url") or ""
                    pdp_url = (
                        f"https://www.noon.com{pdp_path}"
                        if pdp_path.startswith("/")
                        else (f"https://www.noon.com/egypt-en/{pdp_path}/p/" if pdp_path else "")
                    )
                    price_val = float(h.get("sale_price") or h.get("price") or 0) or None
                    img_key = h.get("image_key")
                    img_url = h.get("image_url") or (
                        f"https://f.nooncdn.com/p/{img_key}.jpg" if img_key else None
                    )
                    raw_items.append({
                        "sku": h.get("sku", ""),
                        "title": h.get("name", ""),
                        "url": pdp_url,
                        "price_val": price_val,
                        "price_text": f"{price_val:,.2f} EGP" if price_val else "",
                        "in_stock": h.get("is_buyable", True),
                        "thumbnail_url": img_url,
                        "mpn": h.get("model_number"),
                        "model_code": h.get("model_name"),
                        "brand": h.get("brand"),
                    })
                return raw_items
        except Exception as e:
            print(f"[{self.store_name}] Catalog API error on page {page}: {e}")
        return []

    def _fetch_search_api(self, query: str) -> list[dict]:
        """Fetch candidates from Noon search REST API."""
        try:
            api_url = self.SEARCH_API_TEMPLATE.format(query=quote_plus(query))
            headers = dict(self._headers)
            headers["Accept"] = "application/json, text/plain, */*"
            r = self._session.get(api_url, headers=headers, impersonate="chrome120", timeout=25.0)
            if r.status_code == 200:
                hits = r.json().get("hits", [])
                raw_items: list[dict] = []
                for h in hits:
                    pdp_path = h.get("pdp_url") or h.get("url") or ""
                    pdp_url = (
                        f"https://www.noon.com{pdp_path}"
                        if pdp_path.startswith("/")
                        else (f"https://www.noon.com/egypt-en/{pdp_path}/p/" if pdp_path else "")
                    )
                    price_val = float(h.get("sale_price") or h.get("price") or 0) or None
                    img_key = h.get("image_key")
                    img_url = h.get("image_url") or (
                        f"https://f.nooncdn.com/p/{img_key}.jpg" if img_key else None
                    )
                    raw_items.append({
                        "sku": h.get("sku", ""),
                        "title": h.get("name", ""),
                        "url": pdp_url,
                        "price_val": price_val,
                        "price_text": f"{price_val:,.2f} EGP" if price_val else "",
                        "in_stock": h.get("is_buyable", True),
                        "thumbnail_url": img_url,
                        "mpn": h.get("model_number"),
                        "model_code": h.get("model_name"),
                        "brand": h.get("brand"),
                    })
                return raw_items
        except Exception as e:
            print(f"[{self.store_name}] Search API fallback error for '{query}': {e}")
        return []

    def scrape_catalog(
        self,
        level: int = 1,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape Noon Egypt laptops catalog.

        Args:
            level: 1 for fast catalog card/JSON summaries, 2 for deep PDP spec crawling. Default: 1.
            until_model: Watermark pointer (name, MPN, SKU, or slug). Default: None.
            max_pages: Optional pagination safety ceiling. Default: None (unlimited).
            limit: Maximum products to return. Default: None.
        """
        products: list[RetailerProduct] = []
        seen_skus: set[str] = set()
        watermark_hit = False

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )
        max_pages_display = str(max_pages) if max_pages else "Unlimited (All Pages)"
        print(
            f"[{self.store_name}] Starting Level {level} catalog crawl "
            f"(newest first, until_model='{watermark_display}', max_pages={max_pages_display}, limit={limit or 'All'})"
        )

        for page in itertools.count(1):
            if max_pages and page > max_pages:
                break
            if watermark_hit:
                break

            url = self.CATALOG_URL_TEMPLATE.format(page=page)
            print(f"[{self.store_name}] Fetching page {page}: {url}...")
            html_text = self._fetch_html(url)

            # Strategy A: Extract NEXT_DATA JSON from HTML (used in unit test mocks)
            raw_items = self._parse_next_data_hits(html_text) if (html_text and "__NEXT_DATA__" in html_text) else []

            # Strategy B: Direct Catalog REST API (primary in live environments; immune to Akamai challenge & provides complete prices/images)
            if not raw_items:
                raw_items = self._fetch_catalog_api(page=page)

            # Strategy C: DOM fallback if both NEXT_DATA and Catalog API return empty
            if not raw_items and html_text:
                raw_items = self._parse_dom_cards(html_text)

            if not raw_items:
                print(f"[{self.store_name}] No products found on page {page}. Halting.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(raw_items)} product items.")

            for item in raw_items:
                sku = item.get("sku", "")
                title = item.get("title", "")
                product_url = item.get("url", "")
                price_text = item.get("price_text", "")
                price_val = item.get("price_val")
                in_stock = item.get("in_stock", True)
                thumbnail_url = item.get("thumbnail_url")

                if not title or len(title) < 5:
                    self.record_skipped(
                        name=title or sku or "Unknown",
                        url=product_url,
                        reason="Title too short or missing",
                        stage="level1_parse",
                    )
                    continue

                if not sku:
                    match = re.search(r"([NZ][A-Z0-9]{8,12}[A-Z0-9]?)", product_url)
                    sku = match.group(1) if match else title

                if sku in seen_skus:
                    continue

                # Pre-enrichment watermark check
                url_slug = product_url.split("/")[-2] if "/" in product_url else sku
                if until_model and any(
                    self._matches_watermark(ident, until_model)
                    for ident in [title, sku, url_slug, product_url]
                ):
                    print(
                        f"[{self.store_name}] Pre-enrichment watermark matched '{until_model}' "
                        f"at '{title}' ({product_url}). Halting crawl."
                    )
                    watermark_hit = True
                    break

                # Accessory check
                if self._is_standalone_accessory(title):
                    self.record_skipped(
                        name=title,
                        url=product_url,
                        reason="Filtered out non-laptop accessory or peripheral",
                        stage="level1_filter",
                    )
                    continue

                seen_skus.add(sku)

                if price_val is None and price_text:
                    price_val, price_str = self.parse_egp_price(price_text)
                else:
                    price_str = f"{price_val:,.2f} EGP" if price_val else None

                tokens = ModelNormalizer.extract_model_tokens(title)
                mpn = item.get("mpn") or tokens.get("mpn")
                model_code = item.get("model_code") or tokens.get("full_sku")

                specs: dict[str, str] = {}
                raw_desc: str | None = None
                if level >= 2:
                    pdp_specs, pdp_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = (
                        self._extract_product_specs(product_url)
                    )
                    specs = pdp_specs
                    raw_desc = pdp_desc
                    if pdp_mpn:
                        mpn = pdp_mpn
                    if pdp_model:
                        model_code = pdp_model
                    if pdp_pval is not None:
                        price_val = pdp_pval
                        price_str = pdp_pstr
                    if pdp_stock is not None:
                        in_stock = pdp_stock

                    # Post-enrichment watermark check
                    if until_model and any(
                        self._matches_watermark(ident, until_model)
                        for ident in [mpn, model_code]
                    ):
                        print(
                            f"[{self.store_name}] Post-enrichment watermark matched '{until_model}' "
                            f"at '{title}'. Halting crawl."
                        )
                        watermark_hit = True

                product = RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain=self.base_domain,
                    title=title,
                    product_url=product_url,
                    retailer_product_id=sku,
                    retailer_sku=sku,
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
                products.append(product)

                if limit and len(products) >= limit:
                    break

            if watermark_hit or (limit and len(products) >= limit):
                break

        print(f"[{self.store_name}] Crawl complete. Scraped {len(products)} products (Level {level}).")
        return products

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        """Search Noon Egypt by query string and return candidate RetailerProducts."""
        search_url = self.SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
        print(f"[{self.store_name}] Searching query '{query}': {search_url}")
        html_text = self._fetch_html(search_url)
        # Strategy A: Extract NEXT_DATA JSON from HTML (used in unit test mocks)
        raw_items = self._parse_next_data_hits(html_text) if (html_text and "__NEXT_DATA__" in html_text) else []

        # Strategy B: Search REST API (primary in live environments; immune to Akamai challenge)
        if not raw_items:
            raw_items = self._fetch_search_api(query=query)

        # Strategy C: DOM fallback if both fail
        if not raw_items and html_text:
            raw_items = self._parse_dom_cards(html_text)

        candidates: list[RetailerProduct] = []
        seen_skus: set[str] = set()

        for item in raw_items:
            sku = item.get("sku", "")
            title = item.get("title", "")
            product_url = item.get("url", "")

            if not title or len(title) < 5 or self._is_standalone_accessory(title):
                continue

            if not sku:
                match = re.search(r"([NZ][A-Z0-9]{8,12}[A-Z0-9]?)", product_url)
                sku = match.group(1) if match else title

            if sku in seen_skus:
                continue

            seen_skus.add(sku)
            price_val = item.get("price_val")
            price_text = item.get("price_text")
            if price_val is None and price_text:
                price_val, price_str = self.parse_egp_price(price_text)
            else:
                price_str = f"{price_val:,.2f} EGP" if price_val else None

            # Deep spec extraction
            specs, raw_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = (
                self._extract_product_specs(product_url)
            )
            final_price_val = price_val if price_val is not None else pdp_pval
            final_price_str = price_str if price_str is not None else pdp_pstr
            in_stock = item.get("in_stock", True) if pdp_stock is None else pdp_stock

            tokens = ModelNormalizer.extract_model_tokens(
                f"{title} {pdp_model or ''} {pdp_mpn or ''} {' '.join(specs.values())}"
            )
            mpn = pdp_mpn or item.get("mpn") or tokens.get("mpn")
            model_code = pdp_model or item.get("model_code") or tokens.get("full_sku")

            candidates.append(
                RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain=self.base_domain,
                    title=title,
                    product_url=product_url,
                    retailer_product_id=sku,
                    retailer_sku=sku,
                    mpn=mpn,
                    model_code=model_code,
                    sub_model=tokens.get("sub_model"),
                    base_model=tokens.get("base_model"),
                    price_egp=final_price_val,
                    price_str=final_price_str,
                    in_stock=in_stock,
                    thumbnail_url=item.get("thumbnail_url"),
                    specs=specs,
                    raw_description=raw_desc,
                )
            )

            if len(candidates) >= limit:
                break

        return candidates

    def _parse_next_data_hits(self, html_text: str) -> list[dict]:
        """Extract product hits from Next.js __NEXT_DATA__ JSON script tag."""
        soup = BeautifulSoup(html_text, "html.parser")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            return []

        try:
            data = json.loads(script_tag.string)
            page_props = data.get("props", {}).get("pageProps", {})
            catalog = page_props.get("catalog", {}) or page_props.get("productResponse", {})
            hits = catalog.get("hits") or catalog.get("products") or page_props.get("products", [])

            items = []
            for hit in hits:
                name = hit.get("name") or hit.get("title") or ""
                sku = hit.get("sku") or hit.get("product_code") or ""
                price = hit.get("price") or hit.get("offer_price") or hit.get("sale_price")
                url_key = hit.get("url") or hit.get("product_url") or hit.get("url_key")
                if url_key and not url_key.startswith("http"):
                    if "/p/" in url_key:
                        p_url = urljoin("https://www.noon.com/egypt-en/", url_key)
                    else:
                        p_url = f"https://www.noon.com/egypt-en/{url_key.lstrip('/')}/{sku}/p/"
                elif sku:
                    p_url = f"https://www.noon.com/egypt-en/p/?o={sku}"
                else:
                    p_url = ""

                is_oos = hit.get("is_out_of_stock") or hit.get("out_of_stock", False)
                image_key = hit.get("image_key") or hit.get("image")
                img_url = (
                    f"https://f.nooncdn.com/p/{image_key}.jpg"
                    if image_key and not str(image_key).startswith("http")
                    else image_key
                )

                items.append({
                    "title": name,
                    "sku": sku,
                    "url": p_url,
                    "price_val": float(price) if price else None,
                    "in_stock": not is_oos,
                    "thumbnail_url": img_url,
                    "mpn": hit.get("model_number"),
                    "model_code": hit.get("model_name"),
                })

            return items
        except Exception as e:
            print(f"[{self.store_name}] Failed to parse __NEXT_DATA__: {e}")
            return []

    def _parse_dom_cards(self, html_text: str) -> list[dict]:
        """Fallback DOM parser for Noon product cards."""
        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.select("div[class*='productContainer'], div.productBox, div[data-qa='product-name']")
        if not cards:
            cards = soup.select("a[href*='/p/'], a[href*='-N'], a[href*='-Z']")

        items = []
        for card in cards:
            link_el = card if card.name == "a" else card.select_one("a[href]")
            if not link_el:
                continue

            href = link_el.get("href", "")
            p_url = urljoin("https://www.noon.com", href)

            title_el = card.select_one("[data-qa='product-name'], .productName, h2, h3")
            title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)

            price_el = card.select_one(".amount, span[class*='price']")
            price_text = price_el.get_text(strip=True) if price_el else None

            match = re.search(r"([NZ][A-Z0-9]{8,12}[A-Z0-9]?)", href)
            sku = match.group(1) if match else ""

            img_el = card.select_one("img[src]")
            img_url = img_el.get("src") if img_el else None

            items.append({
                "title": title,
                "sku": sku,
                "url": p_url,
                "price_text": price_text,
                "price_val": None,
                "in_stock": True,
                "thumbnail_url": img_url,
            })

        return items

    def _extract_product_specs(
        self, product_url: str
    ) -> tuple[dict[str, str], str | None, str | None, str | None, float | None, str | None, bool | None]:
        """Fetch Noon PDP and parse specs table and JSON product data."""
        html_text = self._fetch_html(product_url)
        if not html_text:
            return {}, None, None, None, None, None, None

        soup = BeautifulSoup(html_text, "html.parser")
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        in_stock: bool | None = None
        mpn: str | None = None
        model_code: str | None = None

        # Check __NEXT_DATA__ on PDP
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag and script_tag.string:
            try:
                data = json.loads(script_tag.string)
                prod = data.get("props", {}).get("pageProps", {}).get("product", {})
                if prod:
                    mpn = prod.get("model_number")
                    model_code = prod.get("model_name")
                    raw_desc = prod.get("description")
                    raw_p = prod.get("price") or prod.get("sale_price")
                    if raw_p:
                        price_val, price_str = self.parse_egp_price(str(raw_p))
                    in_stock = not prod.get("is_out_of_stock", False)

                    # Specifications list
                    spec_list = prod.get("specifications", [])
                    if isinstance(spec_list, list):
                        for s in spec_list:
                            if isinstance(s, dict):
                                k = s.get("name") or s.get("code")
                                v = s.get("value")
                                if k and v:
                                    specs[str(k).strip()] = str(v).strip()
            except Exception:
                pass

        # Specs table DOM fallback
        if not specs:
            for row in soup.select("div[class*='specifications'] tr, table.specifications tr, .spec-row, table tr"):
                cells = row.select("td, th, div")
                if len(cells) >= 2:
                    k = cells[0].get_text(strip=True)
                    v = cells[1].get_text(" ", strip=True)
                    if k and v and len(k) < 60:
                        specs[k] = v

        mpn = mpn or specs.get("Model Number") or specs.get("MPN")
        model_code = model_code or specs.get("Model Name")

        return specs, raw_desc, mpn, model_code, price_val, price_str, in_stock
