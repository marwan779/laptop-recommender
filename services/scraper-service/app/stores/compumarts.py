import html
import itertools
import json
import re
import time
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.core.patterns import PatternEngine, SpecExtractionResult
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class CompumartsSpecResult(tuple):
    """6-tuple compatible container that also exposes SpecExtractionResult fields."""

    def __new__(cls, specs, raw_desc, price_val, price_str, sku, in_stock, spec_res=None):
        instance = super().__new__(cls, (specs, raw_desc, price_val, price_str, sku, in_stock))
        instance.specs = specs
        instance.raw_description = raw_desc
        instance.price_val = price_val
        instance.price_str = price_str
        instance.sku = sku
        instance.in_stock = in_stock
        instance.spec_res = spec_res
        instance.has_text_specs = getattr(spec_res, "has_text_specs", True) if spec_res else bool(specs)
        instance.specs_extraction_source = getattr(spec_res, "specs_extraction_source", "dom") if spec_res else "dom"
        instance.specs_fallback_reason = getattr(spec_res, "specs_fallback_reason", None) if spec_res else None
        instance.has_specs_image = getattr(spec_res, "has_specs_image", False) if spec_res else False
        instance.specs_image_url = getattr(spec_res, "specs_image_url", None) if spec_res else None
        return instance


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
        "https://www.compumarts.com/collections/laptop?sort_by=created-descending&filter.v.availability=1"
    )
    COLLECTION_PAGE_TEMPLATE = (
        "https://www.compumarts.com/collections/laptop?filter.v.availability=1&sort_by=created-descending&page={page}"
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
        return "Compumarts"

    @property
    def store_key(self) -> str:
        return "compumarts"

    @property
    def base_url(self) -> str:
        return "https://www.compumarts.com"

    def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML using Scrapling engine or fallback curl_cffi session with Cloudflare resilience."""
        if self.engine:
            try:
                doc = self.engine.fetch(url, stealth=False)
                if doc and doc.html and len(doc.html) > 500:
                    return doc.html
            except Exception:
                pass

        impersonations = ["safari15_5", "chrome110", "edge99"]
        for attempt, imp in enumerate(impersonations):
            try:
                r = self._session.get(url, headers=self._headers, impersonate=imp, timeout=25.0)
                if r.status_code == 200 and len(r.text) > 500:
                    return r.text
                elif r.status_code == 429:
                    time.sleep((attempt + 1) * 1.5)
            except Exception as e:
                time.sleep(0.5)
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
        max_pages: int | None = None,
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

        max_pages_display = str(max_pages) if max_pages else "Unlimited (All Pages)"
        print(
            f"[{self.store_name}] Starting Level {level} catalog crawl "
            f"(newest first, in-stock only, until_model='{watermark_display}', max_pages={max_pages_display}, limit={limit or 'All'})"
        )

        for page in itertools.count(1):
            if max_pages and page > max_pages:
                break
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
                link_elem = card.find("a", class_=re.compile(r"card-link|js-prod-link", re.I)) or card.find(
                    "a", href=re.compile(r"/products/")
                )
                if link_elem and until_model:
                    href = link_elem.get("href", "").split("?")[0]
                    card_title = link_elem.get("aria-label", "") or link_elem.get_text(strip=True)
                    handle = href.split("/")[-1]
                    if any(self._matches_watermark(ident, until_model) for ident in [card_title, handle, href]):
                        print(
                            f"[{self.store_name}] Watermark matched '{until_model}' at '{card_title}'. Halting crawl."
                        )
                        watermark_hit = True
                        break

                product = self._parse_card(card, seen_urls, level=level)
                if product:
                    # Also check product SKU / MPN for watermark
                    if until_model and any(
                        self._matches_watermark(ident, until_model)
                        for ident in [product.title, product.retailer_sku, product.mpn]
                    ):
                        print(
                            f"[{self.store_name}] Watermark matched '{until_model}' at '{product.title}'. Halting crawl."
                        )
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
        link_elem = card.find("a", class_=re.compile(r"card-link|js-prod-link", re.I)) or card.find(
            "a", href=re.compile(r"/products/")
        )
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
            self.record_skipped(
                name=title or "Unknown",
                url=full_url,
                reason="Title too short or missing",
                stage="card_filter",
            )
            return None

        # Filter out non-laptop accessories and used/refurbished items
        is_valid, reason = self.is_valid_new_laptop(title=title, url=full_url)
        if not is_valid:
            self.record_skipped(
                name=title,
                url=full_url,
                reason=f"Filtered out as standalone accessory or non-laptop: {reason}",
                stage="card_filter",
            )
            return None

        # Extract price
        price_text = None
        price_elem = card.find(class_=re.compile(r"price__current", re.I)) or card.find(
            class_=re.compile(r"price", re.I)
        )
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
        has_text_specs: bool = True
        specs_extraction_source: str = "dom"
        specs_fallback_reason: str | None = None
        has_specs_image: bool = False
        specs_image_url: str | None = None

        if level == 2:
            # Level 2: Deep Product Detail Page (PDP) Extraction
            spec_res = self._extract_product_specs(full_url, title=title)
            if isinstance(spec_res, tuple) and not hasattr(spec_res, "specs"):
                specs = spec_res[0] if len(spec_res) > 0 else {}
                raw_desc = spec_res[1] if len(spec_res) > 1 else None
                pdp_price_val = spec_res[2] if len(spec_res) > 2 else None
                pdp_price_str = spec_res[3] if len(spec_res) > 3 else None
                pdp_sku = spec_res[4] if len(spec_res) > 4 else None
                pdp_in_stock = spec_res[5] if len(spec_res) > 5 else None
                has_text_specs = bool(specs)
                specs_extraction_source = "dom"
                specs_fallback_reason = None
                has_specs_image = False
                specs_image_url = None
            else:
                specs = spec_res.specs
                raw_desc = spec_res.raw_description
                pdp_price_val = spec_res.price_val
                pdp_price_str = spec_res.price_str
                pdp_sku = spec_res.sku
                pdp_in_stock = spec_res.in_stock
                has_text_specs = spec_res.has_text_specs
                specs_extraction_source = spec_res.specs_extraction_source
                specs_fallback_reason = spec_res.specs_fallback_reason
                has_specs_image = spec_res.has_specs_image
                specs_image_url = spec_res.specs_image_url

            # Level 2 validation: Verify PDP specs/condition do not reveal a used/refurbished or non-laptop product
            pdp_valid, pdp_reason = self.is_valid_new_laptop(
                title=title,
                specs=specs,
                url=full_url,
                description=raw_desc,
            )
            if not pdp_valid:
                self.record_skipped(
                    name=title,
                    url=full_url,
                    reason=f"Filtered out after PDP inspection: {pdp_reason}",
                    stage="pdp_filter",
                )
                return None

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
            has_text_specs=has_text_specs,
            specs_extraction_source=specs_extraction_source,
            specs_fallback_reason=specs_fallback_reason,
            has_specs_image=has_specs_image,
            specs_image_url=specs_image_url,
        )

    def _extract_product_specs(
        self, product_url: str, title: str = ""
    ) -> CompumartsSpecResult:
        """Fetch Compumarts PDP to extract Schema.org JSON-LD, specs table, and description.

        Returns CompumartsSpecResult (unpacks as 6-tuple for backward compatibility).
        """
        html_text = self._fetch_html(product_url)
        if not html_text:
            empty_res = SpecExtractionResult(
                has_text_specs=False,
                specs_extraction_source="none",
                specs_fallback_reason="Failed to fetch PDP HTML",
            )
            return CompumartsSpecResult({}, None, None, None, None, None, empty_res)

        soup = BeautifulSoup(html_text, "html.parser")
        for s in soup(["style"]):
            s.decompose()

        # 1. Parse Schema.org Product JSON-LD for SKU, Price, Availability
        sku: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        in_stock: bool | None = None
        json_desc: str | None = None

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, dict) and data.get("@type") == "Product":
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
                    json_desc = data.get("description")
                    break
            except Exception:
                pass

        if in_stock is None:
            sold_out_elem = soup.select_one(".product-label--sold-out, .sold-out, [data-sold-out]")
            if sold_out_elem or "sold out" in soup.get_text().lower():
                in_stock = False
            else:
                in_stock = True

        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=title,
            store_key=self.store_key,
            base_url=self.base_url,
            price_val=price_val,
            price_str=price_str,
        )

        final_sku = sku or spec_res.mpn
        final_price_val = price_val or spec_res.price_val
        final_price_str = price_str or spec_res.price_str
        final_desc = spec_res.raw_description or json_desc

        return CompumartsSpecResult(
            spec_res.specs,
            final_desc,
            final_price_val,
            final_price_str,
            final_sku,
            in_stock,
            spec_res,
        )
