import itertools
import re
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.core.patterns import PatternEngine, SpecExtractionResult
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class ElBadrStoreScraper(BaseStoreScraper):
    """Store scraper for El Badr Group Egypt (https://elbadrgroupeg.store).

    Architecture & Implementation:
      - CMS / Platform: OpenCart 3 with Journal 3 theme (fully SSR HTML).
      - Category URL: /laptop (internal category path=61).
      - Sorting: Supports backend sort `sort=p.date_added&order=DESC` ensuring
        chronological newest-first order for watermark stopping (`until_model`).
      - Pagination: Supports `&limit=100` returning up to 100 products per request.
      - Level 1: Fast catalog card summary without secondary HTTP requests.
      - Level 2: Deep specifications extraction from PDP, including manufacturer MPN,
        model code from product stats, and 40+ granular hardware fields.
      - Candidate Search: Keyword/SKU search via /index.php?route=product/search&search={query}.
    """

    CATALOG_BASE_URL = "https://elbadrgroupeg.store/laptop?sort=p.date_added&order=DESC&limit=100"
    CATALOG_PAGE_TEMPLATE = (
        "https://elbadrgroupeg.store/index.php?route=product/category&path=61"
        "&limit=100&sort=p.date_added&order=DESC&page={page}"
    )
    SEARCH_URL_TEMPLATE = "https://elbadrgroupeg.store/index.php?route=product/search&search={query}&limit={limit}"

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
        return "El Badr Group"

    @property
    def store_key(self) -> str:
        return "elbadr"

    @property
    def base_url(self) -> str:
        return "https://elbadrgroupeg.store"

    @property
    def base_domain(self) -> str:
        return "elbadrgroupeg.store"

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
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape the canonical in-stock laptops collection sorted by newest first.

        Supports:
          - level=1: Fast catalog card summaries directly from category page (no PDP requests).
          - level=2: Deep specifications extraction visiting each product's PDP.
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

            url = self.CATALOG_PAGE_TEMPLATE.format(page=page)
            print(f"[{self.store_name}] Fetching page {page}: {url}...")
            html_content = self._fetch_html(url)
            if not html_content:
                print(f"[{self.store_name}] Empty response for page {page}. Halting crawl.")
                break

            soup = BeautifulSoup(html_content, "html.parser")
            # Select actual category product cards in main products container
            cards = soup.select(".main-products .product-layout")
            if not cards:
                print(f"[{self.store_name}] No product cards found on page {page}. Reached end of catalog.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(cards)} products.")

            for card in cards:
                # Fast Title & Link check
                link_el = card.select_one(".name a")
                if not link_el:
                    continue

                title = link_el.get_text(strip=True)
                product_url = urljoin(self.base_url, link_el.get("href", ""))
                clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

                if not title or clean_url in seen_urls:
                    continue

                # Filter out standalone accessories and non-laptop/used items
                is_valid, reason = self.is_valid_new_laptop(title=title, url=clean_url)
                if not is_valid:
                    self.record_skipped(
                        name=title,
                        url=clean_url,
                        reason=f"Filtered out as standalone accessory or non-laptop: {reason}",
                        stage="accessory_filter",
                    )
                    continue

                slug = clean_url.rstrip("/").split("/")[-1]

                # Check watermark stopping condition on title or slug
                if until_model and (
                    self._matches_watermark(title, until_model) or self._matches_watermark(slug, until_model)
                ):
                    print(f"[{self.store_name}] Watermark matched '{until_model}' at '{title}'. Halting crawl.")
                    watermark_hit = True
                    break

                seen_urls.add(clean_url)

                # Parse the product card (Level 1 or Level 2)
                product = self._parse_product_card(card, level=level, product_url=product_url, clean_url=clean_url)
                if not product:
                    if not any(s.url == clean_url for s in self.skipped_laptops):
                        self.record_skipped(
                            name=title,
                            url=clean_url,
                            reason="Failed to parse product card or PDP",
                            stage="card_parse",
                        )
                    continue

                # Watermark check on extracted MPN or SKU
                if until_model and (
                    self._matches_watermark(product.mpn, until_model)
                    or self._matches_watermark(product.retailer_sku, until_model)
                ):
                    print(
                        f"[{self.store_name}] Watermark matched MPN/SKU '{until_model}' "
                        f"at '{product.title}'. Halting crawl."
                    )
                    watermark_hit = True
                    break

                products.append(product)

                specs_count = len(product.specs)
                mode_str = f"Specs: {specs_count}" if level == 2 else "Level 1 Summary"
                price_disp = product.price_str or "Price N/A"
                print(
                    f"  [{len(products)}] {product.title[:55]}... | {price_disp} | "
                    f"SKU/MPN: {product.mpn or product.retailer_sku} | {mode_str}"
                )

                if limit and len(products) >= limit:
                    break

            if limit and len(products) >= limit:
                break

            # Check if there is a next page
            results_text = soup.select_one(".results")
            if results_text:
                m = re.search(r"Showing \d+ to (\d+) of (\d+)", results_text.get_text())
                if m and int(m.group(1)) >= int(m.group(2)):
                    print(f"[{self.store_name}] Reached total product count ({m.group(2)}). Crawl complete.")
                    break

        print(f"[{self.store_name}] Crawl complete. Ingested {len(products)} products (Level {level}).")
        return products

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        """Search store catalog by query string and return candidates."""
        url = self.SEARCH_URL_TEMPLATE.format(query=quote_plus(query), limit=limit)
        html_content = self._fetch_html(url)
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select(".main-products .product-layout")
        candidates: list[RetailerProduct] = []
        seen: set[str] = set()

        for card in cards:
            link_el = card.select_one(".name a")
            if not link_el:
                continue

            product_url = urljoin(self.base_url, link_el.get("href", ""))
            clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

            if clean_url in seen:
                continue

            title = link_el.get_text(strip=True)
            if self._is_standalone_accessory(title):
                continue

            seen.add(clean_url)
            # Candidates use Level 1 parsing for fast candidate generation
            product = self._parse_product_card(card, level=1, product_url=product_url, clean_url=clean_url)
            if product:
                candidates.append(product)
                if len(candidates) >= limit:
                    break

        return candidates

    def _parse_product_card(
        self,
        card: BeautifulSoup,
        level: int = 2,
        product_url: str | None = None,
        clean_url: str | None = None,
    ) -> RetailerProduct | None:
        """Parse OpenCart product card into RetailerProduct."""
        link_el = card.select_one(".name a")
        if not link_el:
            return None

        title = link_el.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        if not product_url:
            product_url = urljoin(self.base_url, link_el.get("href", ""))
        if not clean_url:
            clean_url = urlparse(product_url)._replace(query="", fragment="").geturl()

        slug = clean_url.rstrip("/").split("/")[-1]

        # Price parsing
        price_val: float | None = None
        price_str: str | None = None
        price_new_el = card.select_one(".price-new")
        price_reg_el = card.select_one(".price")

        price_text = None
        if price_new_el:
            price_text = price_new_el.get_text(strip=True)
        elif price_reg_el:
            price_text = price_reg_el.get_text(strip=True)

        if price_text:
            price_val, price_str = self.parse_egp_price(price_text)

        # In-Stock check
        card_text_lower = card.get_text().lower()
        has_zero_stock = "has-zero-stock" in card.get("class", [])
        is_out_of_stock = has_zero_stock or "out of stock" in card_text_lower or "غير متوفر" in card_text_lower
        in_stock = not is_out_of_stock

        # Thumbnail URL
        thumbnail_url = None
        img_el = card.select_one("img")
        if img_el:
            img_src = img_el.get("src") or img_el.get("data-src")
            if img_src:
                thumbnail_url = urljoin(self.base_url, img_src)

        # Level 1 vs Level 2 specs
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        pdp_mpn: str | None = None
        pdp_model: str | None = None

        has_text_specs: bool = True
        specs_extraction_source: str = "dom"
        specs_fallback_reason: str | None = None
        has_specs_image: bool = False
        specs_image_url: str | None = None

        if level == 2:
            spec_res = self._extract_product_specs(clean_url, title=title)
            if isinstance(spec_res, tuple):
                pdp_specs = spec_res[0] if len(spec_res) > 0 else {}
                pdp_desc = spec_res[1] if len(spec_res) > 1 else None
                mpn_found = spec_res[2] if len(spec_res) > 2 else None
                model_found = spec_res[3] if len(spec_res) > 3 else None
                pdp_price_val = spec_res[4] if len(spec_res) > 4 else None
                pdp_price_str = spec_res[5] if len(spec_res) > 5 else None
                has_text_specs = spec_res[6] if len(spec_res) > 6 else (len(pdp_specs) > 0)
                specs_extraction_source = spec_res[7] if len(spec_res) > 7 else "dom"
                specs_fallback_reason = spec_res[8] if len(spec_res) > 8 else None
                has_specs_image = spec_res[9] if len(spec_res) > 9 else False
                specs_image_url = spec_res[10] if len(spec_res) > 10 else None
            else:
                pdp_specs = spec_res.specs
                pdp_desc = spec_res.raw_description
                mpn_found = spec_res.mpn
                model_found = spec_res.model_code
                pdp_price_val = spec_res.price_val
                pdp_price_str = spec_res.price_str
                has_text_specs = spec_res.has_text_specs
                specs_extraction_source = spec_res.specs_extraction_source
                specs_fallback_reason = spec_res.specs_fallback_reason
                has_specs_image = spec_res.has_specs_image
                specs_image_url = spec_res.specs_image_url

            pdp_valid, pdp_reason = self.is_valid_new_laptop(
                title=title,
                specs=pdp_specs,
                url=clean_url,
                description=pdp_desc,
            )
            if not pdp_valid:
                self.record_skipped(
                    name=title,
                    url=clean_url,
                    reason=f"Filtered out after PDP inspection: {pdp_reason}",
                    stage="pdp_filter",
                )
                return None
            specs = pdp_specs
            raw_desc = pdp_desc
            pdp_mpn = mpn_found
            pdp_model = model_found
            if price_val is None and pdp_price_val is not None:
                price_val = pdp_price_val
                price_str = pdp_price_str

        # Model Normalizer token extraction
        combined_text = f"{title} {pdp_mpn or ''} {pdp_model or ''} {' '.join(specs.values())}"
        tokens = ModelNormalizer.extract_model_tokens(combined_text)

        mpn = pdp_mpn or tokens.get("mpn")
        model_code = pdp_model or tokens.get("full_sku") or tokens.get("base_model")

        return RetailerProduct(
            store_name=self.store_name,
            store_key=self.store_key,
            store_domain=self.base_domain,
            title=title,
            product_url=clean_url,
            retailer_product_id=slug,
            retailer_sku=pdp_mpn or slug,
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
            has_text_specs=has_text_specs,
            specs_extraction_source=specs_extraction_source,
            specs_fallback_reason=specs_fallback_reason,
            has_specs_image=has_specs_image,
            specs_image_url=specs_image_url,
        )

    def _extract_product_specs(self, product_url: str, title: str = "") -> SpecExtractionResult:
        """Fetch El Badr Group PDP to extract specifications, product stats, and description.

        Returns SpecExtractionResult (which also unpacks as legacy 6-tuple for backward compatibility).
        """
        html_text = self._fetch_html(product_url)
        if not html_text:
            return SpecExtractionResult(
                has_text_specs=False,
                specs_extraction_source="none",
                specs_fallback_reason="Failed to fetch PDP HTML",
            )

        soup = BeautifulSoup(html_text, "html.parser")
        for s in soup(["style", "script"]):
            s.decompose()

        # PDP Price Fallback
        price_val: float | None = None
        price_str: str | None = None
        price_group = soup.select_one(".product-price-group, .product-price")
        if price_group:
            price_new_el = price_group.select_one(".price-new")
            price_reg_el = price_group.select_one(".product-price, .price")
            p_text = (
                price_new_el.get_text(strip=True)
                if price_new_el
                else (price_reg_el.get_text(strip=True) if price_reg_el else None)
            )
            if p_text:
                price_val, price_str = self.parse_egp_price(p_text)

        # Delegate spec, stats, description, and OCR metadata extraction to PatternEngine
        return PatternEngine.extract_specs(
            soup=soup,
            title=title,
            store_key=self.store_key,
            base_url=self.base_url,
            price_val=price_val,
            price_str=price_str,
        )
