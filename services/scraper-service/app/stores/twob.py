import html
import re
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class TwoBStoreScraper(BaseStoreScraper):
    """Store scraper for 2B Egypt (https://2b.com.eg).

    Architecture & Implementation:
      - CMS / Platform: Magento 2.
      - Category URL: /en/computers/laptops.html.
      - Pagination: Supports `?p={page}&product_list_limit=45` (default max 45 per page, ~87 laptops total).
      - Sorting: Default order is Magento 2 'position' (curated by store admin / 'Most Selling').
        Note: The catalog is NOT strictly chronological by creation date; newer items (e.g. high entity IDs)
        can appear anywhere in the 87 items. Because the full catalog is small (~87 laptops, 2 pages),
        Level 1 scraping should ideally scan all pages rather than relying on early watermark stopping.
      - Level 1: Fast catalog card summary without secondary HTTP requests. Includes accurate
        in-stock / out-of-stock detection directly from catalog card action buttons (.out-of-stock-btn).
      - Level 2: Deep specifications extraction from PDP (#product-attribute-specs-table),
        extracting MPN, Part Number, Processor Information, RAM Information, Storage,
        Display, Graphics Card, and OS.
      - Candidate Search: Keyword/SKU search via /en/catalogsearch/result/?q={query}.
    """

    CATALOG_PAGE_TEMPLATE = (
        "https://2b.com.eg/en/computers/laptops.html?p={page}&product_list_limit=45"
    )
    SEARCH_URL_TEMPLATE = (
        "https://2b.com.eg/en/catalogsearch/result/?q={query}"
    )

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
        return "2B"

    @property
    def store_key(self) -> str:
        return "twob"

    @property
    def base_url(self) -> str:
        return "https://2b.com.eg"

    @property
    def base_domain(self) -> str:
        return "2b.com.eg"

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

    def scrape_catalog(
        self,
        level: int = 2,
        until_model: str | list[str] | None = None,
        max_pages: int = 20,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape the canonical in-stock laptops collection sorted by newest first.

        Architecture:
          - Phase 1: Collects catalog cards across category pages up to max_pages.
          - Phase 2: Sorts cards by Magento's auto-incrementing integer entity_id (data-product-id)
            in descending order, establishing a true chronological newest-first order.
          - Phase 3: Evaluates watermark stopping (until_model), Level 1 card summaries,
            and Level 2 deep PDP spec extractions in newest-first order.
        """
        raw_cards_info: list[dict] = []
        seen_urls: set[str] = set()

        watermark_display = (
            ", ".join(until_model)
            if isinstance(until_model, (list, tuple, set))
            else (until_model or "None (Full Catalog)")
        )

        print(
            f"[{self.store_name}] Starting Level {level} catalog crawl "
            f"(newest first by entity_id, until_model='{watermark_display}', max_pages={max_pages}, limit={limit or 'All'})"
        )

        # Phase 1: Ingest cards across pages
        for page in range(1, max_pages + 1):
            url = self.CATALOG_PAGE_TEMPLATE.format(page=page)
            print(f"[{self.store_name}] Fetching page {page}: {url}...")
            html_content = self._fetch_html(url)
            if not html_content:
                print(f"[{self.store_name}] Empty response for page {page}. Halting crawl.")
                break

            soup = BeautifulSoup(html_content, "html.parser")
            cards = soup.select(".products.wrapper .product-items > li.product-item")
            if not cards:
                print(f"[{self.store_name}] No product cards found on page {page}. Reached end of catalog.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(cards)} products.")

            for card in cards:
                link_el = card.select_one(".product-item-name a, a.product-item-link")
                if not link_el:
                    continue

                title = link_el.get_text(strip=True)
                product_url = urljoin(self.base_url, link_el.get("href", ""))
                clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

                if not title or clean_url in seen_urls:
                    continue

                # Filter out standalone accessories (backpacks, mice, etc.)
                if self._is_standalone_accessory(title):
                    continue

                seen_urls.add(clean_url)

                # Entity ID (Magento auto-incrementing integer)
                pid_el = card.find(attrs={"data-product-id": True})
                raw_pid = pid_el.get("data-product-id") if pid_el else None
                numeric_pid = int(raw_pid) if raw_pid and raw_pid.isdigit() else 0
                url_slug = clean_url.split("/")[-1].replace(".html", "")
                retailer_product_id = raw_pid or url_slug

                # Price extraction from catalog card (prioritize finalPrice / special-price over was/old-price)
                price_el = card.find(attrs={"data-price-type": "finalPrice"})
                if not price_el:
                    price_el = card.select_one(".special-price .price")
                if not price_el:
                    price_el = card.select_one(".price-wrapper .price, .price")
                card_price_text = price_el.get_text(strip=True) if price_el else None
                card_price_val, card_price_str = self.parse_egp_price(card_price_text)

                # Stock extraction from card
                has_oos_btn = bool(card.select(".out-of-stock-btn, .stock.unavailable"))
                card_text_lower = card.get_text(" ", strip=True).lower()
                card_in_stock = not has_oos_btn and "out of stock" not in card_text_lower and "غير متوفر" not in card_text_lower

                # Thumbnail
                img_el = card.select_one("img.product-image-photo, img[src]")
                img_url = urljoin(self.base_url, img_el.get("src", "")) if img_el else None

                raw_cards_info.append({
                    "numeric_pid": numeric_pid,
                    "retailer_product_id": retailer_product_id,
                    "title": title,
                    "clean_url": clean_url,
                    "url_slug": url_slug,
                    "card_price_val": card_price_val,
                    "card_price_str": card_price_str,
                    "card_in_stock": card_in_stock,
                    "img_url": img_url,
                })

        # Phase 2: Sort cards by entity_id descending (newest added first)
        raw_cards_info.sort(key=lambda x: x["numeric_pid"], reverse=True)
        print(f"[{self.store_name}] Total unique laptops indexed: {len(raw_cards_info)}. Processing newest first...")

        # Phase 3: Build products and apply watermark stopping & Level 2 enrichment
        products: list[RetailerProduct] = []
        for item in raw_cards_info:
            title = item["title"]
            clean_url = item["clean_url"]
            url_slug = item["url_slug"]
            tokens = ModelNormalizer.extract_model_tokens(title)

            # Watermark check in chronological order
            if until_model:
                if (
                    self._matches_watermark(title, until_model)
                    or self._matches_watermark(clean_url, until_model)
                    or self._matches_watermark(url_slug, until_model)
                    or self._matches_watermark(tokens.get("mpn"), until_model)
                    or self._matches_watermark(tokens.get("full_sku"), until_model)
                    or self._matches_watermark(tokens.get("sub_model"), until_model)
                ):
                    print(
                        f"[{self.store_name}] Reached watermark '{watermark_display}' "
                        f"at '{title}' ({clean_url}). Halting crawl."
                    )
                    break

            specs: dict[str, str] = {}
            raw_desc: str | None = None
            mpn = tokens.get("mpn")
            model_code = tokens.get("full_sku")
            final_price_val = item["card_price_val"]
            final_price_str = item["card_price_str"]
            final_in_stock = item["card_in_stock"]

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
                    final_price_val = pdp_pval
                    final_price_str = pdp_pstr
                if pdp_stock is not None:
                    final_in_stock = pdp_stock

                # Re-extract tokens with combined specs text
                combined_text = f"{title} {model_code or ''} {mpn or ''} {' '.join(specs.values())}"
                enriched_tokens = ModelNormalizer.extract_model_tokens(combined_text)
                tokens = {**tokens, **{k: v for k, v in enriched_tokens.items() if v}}

            product = RetailerProduct(
                store_name=self.store_name,
                store_key=self.store_key,
                store_domain=self.base_domain,
                title=title,
                product_url=clean_url,
                retailer_product_id=item["retailer_product_id"],
                retailer_sku=mpn or tokens.get("mpn") or item["retailer_product_id"],
                mpn=mpn or tokens.get("mpn"),
                model_code=model_code or tokens.get("full_sku"),
                sub_model=tokens.get("sub_model"),
                base_model=tokens.get("base_model"),
                price_egp=final_price_val,
                price_str=final_price_str,
                in_stock=final_in_stock,
                thumbnail_url=item["img_url"],
                specs=specs,
                raw_description=raw_desc,
            )
            products.append(product)

            if limit and len(products) >= limit:
                break

        print(f"[{self.store_name}] Crawl completed: Scraped {len(products)} products.")
        return products

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        """Search 2B by query (model, SKU, MPN) and return candidate RetailerProducts."""
        search_url = self.SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
        html_content = self._fetch_html(search_url)
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select(".products.wrapper .product-items > li.product-item")
        candidates: list[RetailerProduct] = []
        seen_urls: set[str] = set()

        for card in cards:
            link_el = card.select_one(".product-item-name a, a.product-item-link")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            product_url = urljoin(self.base_url, link_el.get("href", ""))
            clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

            if not title or len(title) < 5 or clean_url in seen_urls:
                continue

            # Avoid accessories
            if self._is_standalone_accessory(title):
                continue

            seen_urls.add(clean_url)

            # Price from card (prioritize finalPrice / special-price over was/old-price)
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
            in_stock = not has_oos_btn and "out of stock" not in card_text_lower and "غير متوفر" not in card_text_lower

            # Thumbnail
            img_el = card.select_one("img.product-image-photo, img[src]")
            img_url = urljoin(self.base_url, img_el.get("src", "")) if img_el else None

            # Product ID
            pid_el = card.select_one("[data-product-id]")
            url_slug = clean_url.split("/")[-1].replace(".html", "")
            retailer_product_id = pid_el.get("data-product-id") if pid_el else url_slug

            # Deep spec extraction from product page
            specs, raw_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = (
                self._extract_product_specs(clean_url)
            )
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
                    retailer_sku=mpn or tokens.get("mpn") or retailer_product_id,
                    mpn=mpn,
                    model_code=model_code,
                    sub_model=tokens.get("sub_model"),
                    base_model=tokens.get("base_model"),
                    price_egp=final_price_val,
                    price_str=final_price_str,
                    in_stock=in_stock,
                    thumbnail_url=img_url,
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
        """Fetch 2B product page to extract Magento specification table, SKU/MPN, and price/stock fallbacks."""
        try:
            html_content = self._fetch_html(product_url)
            if not html_content:
                return {}, None, None, None, None, None, None

            soup = BeautifulSoup(html_content, "html.parser")
            specs: dict[str, str] = {}
            raw_desc = None
            page_price_val = None
            page_price_str = None
            in_stock = None

            # Stock check
            stock_el = soup.select_one(".stock.available, .stock.unavailable")
            if stock_el:
                s_text = stock_el.get_text(strip=True).lower()
                classes = stock_el.get("class", [])
                in_stock = "unavailable" not in classes and "out of stock" not in s_text and "غير متوفر" not in s_text

            # Price fallback from product page meta or price-box
            price_meta = soup.select_one("meta[property*='price:amount'], meta[itemprop='price']")
            if price_meta and price_meta.get("content"):
                page_price_val, page_price_str = self.parse_egp_price(price_meta.get("content"))

            if page_price_val is None:
                price_el = soup.find(attrs={"data-price-type": "finalPrice"})
                if not price_el:
                    price_el = soup.select_one(".special-price .price")
                if not price_el:
                    price_el = soup.select_one(".price-wrapper .price, .price")
                if price_el:
                    page_price_val, page_price_str = self.parse_egp_price(price_el.get_text(strip=True))

            # Specs table: #product-attribute-specs-table tr or .additional-attributes tr
            for row in soup.select("#product-attribute-specs-table tr, .additional-attributes tr"):
                th = row.select_one("th")
                td = row.select_one("td")
                if th and td:
                    k = th.get_text(strip=True)
                    v = td.get_text(" ", strip=True)
                    if k and v and len(k) < 60:
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
            )
            model_code = specs.get("Model")

            return specs, raw_desc, mpn, model_code, page_price_val, page_price_str, in_stock
        except Exception as e:
            print(f"[{self.store_name}] Failed to extract product details from {product_url}: {e}")
            return {}, None, None, None, None, None, None
