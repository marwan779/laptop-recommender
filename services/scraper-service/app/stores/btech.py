import itertools
import json
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class BTechStoreScraper(BaseStoreScraper):
    """Store scraper for B.TECH Egypt (https://btech.com/en/).

    Architecture & Implementation:
      - CMS / Platform: Magento 2 / Adobe Commerce.
      - Category URL: /en/laptops-pcs/laptops.html.
      - Sorting: Chronological newest-first via `product_list_order=entity_id&product_list_dir=desc`.
      - Level 1: Fast catalog card summary extracting title, price, stock, SKU, and image.
      - Level 2: Deep PDP specs table extraction from #product-attribute-specs-table or .additional-attributes.
      - Watermark stopping via `until_model` pointer.
      - Candidate search via /en/catalogsearch/result/?q={query}.
    """

    CATALOG_PAGE_TEMPLATE = (
        "https://btech.com/en/c/laptop-pc?p={page}&product_list_order=entity_id&product_list_dir=desc"
    )
    SEARCH_URL_TEMPLATE = "https://btech.com/en/catalogsearch/result/?q={query}"


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
        return "B.TECH"

    @property
    def store_key(self) -> str:
        return "btech"

    @property
    def base_url(self) -> str:
        return "https://btech.com"

    @property
    def base_domain(self) -> str:
        return "btech.com"

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

    def _parse_next_f_items(self, html_text: str) -> list[dict]:
        """Extract product items from B.TECH Next.js App Router (RSC) self.__next_f chunks."""
        needle = '\\"items\\":['
        pos = html_text.find(needle)
        if pos != -1:
            sub = html_text[pos + len(needle) - 1 :].replace('\\"', '"').replace("\\\\", "\\")
            try:
                arr, _ = json.JSONDecoder().raw_decode(sub)
                if isinstance(arr, list):
                    return arr
            except Exception:
                pass

        pos_u = html_text.find('"items":[')
        if pos_u != -1:
            sub_u = html_text[pos_u + 8 :]
            try:
                arr, _ = json.JSONDecoder().raw_decode(sub_u)
                if isinstance(arr, list):
                    return arr
            except Exception:
                pass

        return []

    def scrape_catalog(
        self,
        level: int = 1,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape B.TECH laptops catalog sorted by newest first (entity_id desc).

        Args:
            level: 1 for fast catalog card summaries, 2 for deep PDP spec crawling. Default: 1.
            until_model: Watermark pointer (name, MPN, SKU, or slug). Default: None.
            max_pages: Optional pagination safety ceiling. Default: None (unlimited).
            limit: Maximum products to return. Default: None.
        """
        products: list[RetailerProduct] = []
        seen_urls: set[str] = set()
        watermark_hit = False

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )
        max_pages_display = str(max_pages) if max_pages else "Unlimited (All Pages)"
        print(
            f"[{self.store_name}] Starting Level {level} catalog crawl "
            f"(newest first by entity_id, until_model='{watermark_display}', max_pages={max_pages_display}, limit={limit or 'All'})"
        )

        for page in itertools.count(1):
            if max_pages and page > max_pages:
                break
            if watermark_hit:
                break

            url = self.CATALOG_PAGE_TEMPLATE.format(page=page)
            print(f"[{self.store_name}] Fetching page {page}: {url}...")
            html_text = self._fetch_html(url)
            if not html_text:
                print(f"[{self.store_name}] Empty response for page {page}. Halting crawl.")
                break

            # Strategy A: Next.js App Router streaming items (self.__next_f)
            next_f_items = self._parse_next_f_items(html_text)
            if next_f_items:
                print(f"[{self.store_name}] Page {page}: Found {len(next_f_items)} products via Next.js state.")
                for it in next_f_items:
                    title = it.get("name", "")
                    sku = it.get("sku", "")
                    slug = it.get("slug", "")
                    if not slug and not sku:
                        continue
                    clean_url = f"https://btech.com/en/p/{slug}" if slug else f"https://btech.com/en/p/{sku}"

                    if not title or len(title) < 5 or clean_url in seen_urls:
                        continue

                    # Pre-enrichment watermark check
                    if until_model and any(
                        self._matches_watermark(ident, until_model) for ident in [title, sku, slug, clean_url]
                    ):
                        print(
                            f"[{self.store_name}] Pre-enrichment watermark matched '{until_model}' "
                            f"at '{title}' ({clean_url}). Halting crawl."
                        )
                        watermark_hit = True
                        break

                    # Accessory check
                    if self._is_standalone_accessory(title):
                        self.record_skipped(
                            name=title,
                            url=clean_url,
                            reason="Filtered out non-laptop accessory or peripheral",
                            stage="level1_filter",
                        )
                        continue

                    seen_urls.add(clean_url)

                    price_obj = it.get("price") or {}
                    raw_price = price_obj.get("final_price") or price_obj.get("base_price")
                    price_val = float(raw_price) if raw_price else None
                    price_str = f"{price_val:,.2f} EGP" if price_val else None

                    in_stock = it.get("is_in_stock", True)
                    thumb = it.get("thumbnail_url")
                    thumbnail_url = (
                        thumb
                        if (thumb and thumb.startswith("http"))
                        else (f"https://f.btech.com/media/catalog/product/{thumb.lstrip('/')}" if thumb else None)
                    )

                    tokens = ModelNormalizer.extract_model_tokens(title)
                    mpn = tokens.get("mpn")
                    model_code = tokens.get("full_sku")

                    specs: dict[str, str] = {}
                    raw_desc: str | None = None
                    if level >= 2:
                        pdp_specs, pdp_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = (
                            self._extract_product_specs(clean_url)
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
                            self._matches_watermark(ident, until_model) for ident in [mpn, model_code]
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
                        product_url=clean_url,
                        retailer_product_id=sku or slug,
                        retailer_sku=sku or slug,
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

                    if watermark_hit or (limit and len(products) >= limit):
                        break

                if watermark_hit or (limit and len(products) >= limit):
                    break
                continue

            # Strategy B: Legacy Magento 2 DOM cards fallback
            soup = BeautifulSoup(html_text, "html.parser")
            cards = soup.select(".products.wrapper .product-items > li.product-item")
            if not cards:
                cards = soup.select("li.product-item")
            if not cards:
                cards = soup.select(".product-item-info")

            if not cards:
                print(f"[{self.store_name}] No product cards found on page {page}. Reached end of catalog.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(cards)} product cards.")

            for card in cards:
                link_el = card.select_one(".product-item-name a, a.product-item-link")
                if not link_el:
                    continue

                title = link_el.get_text(strip=True)
                raw_href = link_el.get("href", "")
                product_url = urljoin(self.base_url, raw_href)
                clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

                if not title or len(title) < 5 or clean_url in seen_urls:
                    continue

                pid_el = card.find(attrs={"data-product-id": True})
                raw_pid = pid_el.get("data-product-id") if pid_el else None
                url_slug = clean_url.split("/")[-1].replace(".html", "")
                retailer_product_id = raw_pid or url_slug

                # Pre-enrichment watermark check
                if until_model and any(
                    self._matches_watermark(ident, until_model)
                    for ident in [title, retailer_product_id, url_slug, clean_url]
                ):
                    print(
                        f"[{self.store_name}] Pre-enrichment watermark matched '{until_model}' "
                        f"at '{title}' ({clean_url}). Halting crawl."
                    )
                    watermark_hit = True
                    break

                # Accessory check
                if self._is_standalone_accessory(title):
                    self.record_skipped(
                        name=title,
                        url=clean_url,
                        reason="Filtered out non-laptop accessory or peripheral",
                        stage="level1_filter",
                    )
                    continue

                seen_urls.add(clean_url)

                # Price extraction
                price_el = card.find(attrs={"data-price-type": "finalPrice"})
                if not price_el:
                    price_el = card.select_one(".special-price .price")
                if not price_el:
                    price_el = card.select_one(".price-wrapper .price, .price")
                price_text = price_el.get_text(strip=True) if price_el else None
                price_val, price_str = self.parse_egp_price(price_text)

                # Stock check
                has_oos_btn = bool(card.select(".out-of-stock-btn, .stock.unavailable"))
                card_text_lower = card.get_text(" ", strip=True).lower()
                in_stock = (
                    not has_oos_btn and "out of stock" not in card_text_lower and "غير متوفر" not in card_text_lower
                )

                # Thumbnail image
                img_el = card.select_one("img.product-image-photo, img[src]")
                thumbnail_url = urljoin(self.base_url, img_el.get("src", "")) if img_el else None

                tokens = ModelNormalizer.extract_model_tokens(title)
                mpn = tokens.get("mpn")
                model_code = tokens.get("full_sku")

                # Level 2 enrichment if requested
                specs: dict[str, str] = {}
                raw_desc: str | None = None
                if level >= 2:
                    pdp_specs, pdp_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = (
                        self._extract_product_specs(clean_url)
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
                    if until_model and any(self._matches_watermark(ident, until_model) for ident in [mpn, model_code]):
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
                    product_url=clean_url,
                    retailer_product_id=retailer_product_id,
                    retailer_sku=mpn or retailer_product_id,
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
        """Search B.TECH Egypt by query string and return candidate RetailerProducts."""
        search_url = self.SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
        print(f"[{self.store_name}] Searching query '{query}': {search_url}")
        html_text = self._fetch_html(search_url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.select(".products.wrapper .product-items > li.product-item")
        if not cards:
            cards = soup.select("li.product-item")
        if not cards:
            cards = soup.select(".product-item-info")
        candidates: list[RetailerProduct] = []
        seen_urls: set[str] = set()

        for card in cards:
            link_el = card.select_one(".product-item-name a, a.product-item-link")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            product_url = urljoin(self.base_url, link_el.get("href", ""))
            clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

            if not title or len(title) < 5 or clean_url in seen_urls or self._is_standalone_accessory(title):
                continue

            seen_urls.add(clean_url)
            price_el = card.find(attrs={"data-price-type": "finalPrice"}) or card.select_one(
                ".special-price .price, .price"
            )
            price_text = price_el.get_text(strip=True) if price_el else None
            price_val, price_str = self.parse_egp_price(price_text)

            has_oos_btn = bool(card.select(".out-of-stock-btn, .stock.unavailable"))
            card_text_lower = card.get_text(" ", strip=True).lower()
            in_stock = not has_oos_btn and "out of stock" not in card_text_lower and "غير متوفر" not in card_text_lower

            img_el = card.select_one("img.product-image-photo, img[src]")
            thumbnail_url = urljoin(self.base_url, img_el.get("src", "")) if img_el else None

            pid_el = card.select_one("[data-product-id]")
            url_slug = clean_url.split("/")[-1].replace(".html", "")
            retailer_product_id = pid_el.get("data-product-id") if pid_el else url_slug

            # Enrich with Level 2 PDP specs
            specs, raw_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = self._extract_product_specs(clean_url)
            final_price_val = price_val if price_val is not None else pdp_pval
            final_price_str = price_str if price_str is not None else pdp_pstr
            if pdp_stock is not None:
                in_stock = pdp_stock

            tokens = ModelNormalizer.extract_model_tokens(
                f"{title} {pdp_model or ''} {pdp_mpn or ''} {' '.join(specs.values())}"
            )
            mpn = pdp_mpn or tokens.get("mpn")
            model_code = pdp_model or tokens.get("full_sku")

            candidates.append(
                RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain=self.base_domain,
                    title=title,
                    product_url=clean_url,
                    retailer_product_id=retailer_product_id,
                    retailer_sku=mpn or retailer_product_id,
                    mpn=mpn,
                    model_code=model_code,
                    sub_model=tokens.get("sub_model"),
                    base_model=tokens.get("base_model"),
                    price_egp=final_price_val,
                    price_str=final_price_str,
                    in_stock=in_stock,
                    thumbnail_url=thumbnail_url,
                    specs=specs,
                    raw_description=raw_desc,
                )
            )

            if len(candidates) >= limit:
                break

        return candidates

    def _extract_product_specs(
        self, product_url: str
    ) -> tuple[dict[str, str], str | None, str | None, str | None, float | None, str | None, bool | None]:
        """Fetch B.TECH PDP HTML and extract Magento tech spec table rows, description, price, and stock."""
        html_text = self._fetch_html(product_url)
        if not html_text:
            return {}, None, None, None, None, None, None

        soup = BeautifulSoup(html_text, "html.parser")
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        in_stock: bool | None = None

        # Stock check
        stock_el = soup.select_one(".stock.available, .stock.unavailable")
        if stock_el:
            s_text = stock_el.get_text(strip=True).lower()
            classes = stock_el.get("class", [])
            in_stock = "unavailable" not in classes and "out of stock" not in s_text and "غير متوفر" not in s_text

        # Price fallback from PDP price-box or meta
        price_meta = soup.select_one("meta[property*='price:amount'], meta[itemprop='price']")
        if price_meta and price_meta.get("content"):
            price_val, price_str = self.parse_egp_price(price_meta.get("content"))

        if price_val is None:
            price_el = soup.find(attrs={"data-price-type": "finalPrice"}) or soup.select_one(
                ".special-price .price, .price"
            )
            if price_el:
                price_val, price_str = self.parse_egp_price(price_el.get_text(strip=True))

        # Strategy A: Next.js script specifications list
        needle = '\\"specifications\\":['
        pos = html_text.find(needle)
        if pos != -1:
            sub = html_text[pos + len(needle) - 1 :].replace('\\"', '"').replace("\\\\", "\\")
            try:
                arr, _ = json.JSONDecoder().raw_decode(sub)
                if isinstance(arr, list):
                    for entry in arr:
                        k = entry.get("key") or entry.get("name")
                        v = entry.get("value")
                        if k and v:
                            specs[str(k).strip()] = str(v).strip()
            except Exception:
                pass

        if not specs:
            pos_u = html_text.find('"specifications":[')
            if pos_u != -1:
                sub_u = html_text[pos_u + 17 :]
                try:
                    arr, _ = json.JSONDecoder().raw_decode(sub_u)
                    if isinstance(arr, list):
                        for entry in arr:
                            k = entry.get("key") or entry.get("name")
                            v = entry.get("value")
                            if k and v:
                                specs[str(k).strip()] = str(v).strip()
                except Exception:
                    pass

        # Strategy B: Specs table DOM fallback
        for row in soup.select(
            "#product-attribute-specs-table tr, .additional-attributes tr, table.data.table tr, table.w-full tr, table tr"
        ):
            th = row.select_one("th, td.label, .table-label") or row.select_one("th")
            td = row.select_one("td.data, td:last-child, .table-value") or row.select_one("td")
            if th and td:
                k = th.get_text(strip=True)
                v = td.get_text(" ", strip=True)
                if k and v and len(k) < 60 and k not in specs:
                    specs[k] = v

        # Description
        desc_el = soup.select_one(".product.attribute.overview, .description .value")
        if desc_el:
            raw_desc = desc_el.get_text(" ", strip=True)[:1500]

        mpn = (
            specs.get("MPN")
            or specs.get("Part Number")
            or specs.get("part_number")
            or specs.get("Barcode")
            or specs.get("SKU")
        )
        model_code = specs.get("Model") or specs.get("Model Name")

        return specs, raw_desc, mpn, model_code, price_val, price_str, in_stock
