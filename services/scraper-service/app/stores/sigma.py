import itertools
import json
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.core.patterns.engine import PatternEngine
from app.core.patterns.models import SpecExtractionResult
from app.core.patterns.registry import PatternRegistry
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class SigmaSpecResult(tuple):
    """2-tuple compatible container that also exposes SpecExtractionResult fields."""

    def __new__(cls, specs, raw_desc, spec_res=None):
        instance = super().__new__(cls, (specs, raw_desc))
        instance.specs = specs
        instance.raw_description = raw_desc
        instance.spec_res = spec_res
        instance.has_text_specs = getattr(spec_res, "has_text_specs", True) if spec_res else bool(specs)
        instance.specs_extraction_source = getattr(spec_res, "specs_extraction_source", "dom") if spec_res else "dom"
        instance.specs_fallback_reason = getattr(spec_res, "specs_fallback_reason", None) if spec_res else None
        instance.has_specs_image = getattr(spec_res, "has_specs_image", False) if spec_res else False
        instance.specs_image_url = getattr(spec_res, "specs_image_url", None) if spec_res else None
        instance.pattern_learned = getattr(spec_res, "pattern_learned", False) if spec_res else False
        instance.learned_pattern_type = getattr(spec_res, "learned_pattern_type", None) if spec_res else None
        return instance


class SigmaComputerStoreScraper(BaseStoreScraper):
    """Store scraper for Sigma Computer Egypt (https://www.sigma-computer.com).

    Supports:
      1. Next.js App Router RSC (React Server Components) payload decoding.
      2. Level 1: Fast catalog crawl extracting up to 50 products per page directly
         from the decoded RSC stream without secondary PDP requests.
      3. Level 2: Deep crawl visiting each laptop's PDP to extract the complete
         structured specifications array (CPU, GPU, RAM, Storage, Screen, etc.).
      4. Watermark stopping via `until_model` for incremental scraping (newest added first).
      5. Targeted keyword/model search via /search?q={query}.
    """

    LAPTOPS_CATEGORY_ID = "9f5039de-5c80-46f3-9fe4-6e8f94189b8c"
    SEARCH_BASE_URL = "https://www.sigma-computer.com/en/search"
    ITEM_BASE_URL = "https://www.sigma-computer.com/en/item"


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
        return "Sigma Computer"

    @property
    def store_key(self) -> str:
        return "sigma"

    @property
    def base_url(self) -> str:
        return "https://www.sigma-computer.com"

    @property
    def base_domain(self) -> str:
        return "sigma-computer.com"

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

    def _decode_rsc_payload(self, html_text: str) -> str:
        """Decode Next.js App Router React Server Components (RSC) streamed chunks."""
        matches = re.findall(r'self\.__next_f\.push\((\[1,\s*".*?"\])\)', html_text)
        chunks: list[str] = []
        for m in matches:
            try:
                parsed = json.loads(m)
                if isinstance(parsed, list) and len(parsed) >= 2 and isinstance(parsed[1], str):
                    chunks.append(parsed[1])
            except Exception:
                pass
        return "".join(chunks)

    def _extract_products_from_rsc(self, rsc_text: str) -> list[dict]:
        """Extract the JSON products array from the decoded RSC payload."""
        idx = rsc_text.find('"products":[')
        if idx == -1:
            return []
        start = idx + len('"products":')
        bracket_count = 0
        end = -1
        for i in range(start, len(rsc_text)):
            if rsc_text[i] == "[":
                bracket_count += 1
            elif rsc_text[i] == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    end = i + 1
                    break
        if end == -1:
            return []
        try:
            return json.loads(rsc_text[start:end])
        except Exception:
            return []

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
          - level=1: Fast catalog card summaries directly from RSC payload (no PDP requests).
          - level=2: Deep specifications extraction visiting each product's PDP.
          - until_model: Watermark pointer stopping condition.
        """
        products: list[RetailerProduct] = []
        seen_slugs: set[str] = set()
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

        filters_dict = {
            "category_id": [self.LAPTOPS_CATEGORY_ID],
            "is_stock": 1,
        }

        for page in itertools.count(1):
            if max_pages and page > max_pages:
                break
            if watermark_hit:
                break

            params = {
                "filters": json.dumps(filters_dict),
                "sortBy": "created_at",
                "sortDir": "desc",
                "page": page,
                "pageSize": 50,
            }
            page_url = f"{self.SEARCH_BASE_URL}?{urlencode(params)}"
            print(f"[{self.store_name}] Fetching page {page}: {page_url}...")
            html_text = self._fetch_html(page_url)
            if not html_text:
                print(f"[{self.store_name}] Empty response for page {page}. Stopping.")
                break

            rsc_text = self._decode_rsc_payload(html_text)
            raw_products = self._extract_products_from_rsc(rsc_text)

            if not raw_products:
                # Fallback: attempt HTML DOM card parsing
                raw_products = self._extract_products_from_html(html_text)

            if not raw_products:
                print(f"[{self.store_name}] No products found on page {page}. Finished catalog crawl.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(raw_products)} products.")

            for raw in raw_products:
                slug = raw.get("slug")
                if not slug or slug in seen_slugs:
                    continue

                name = raw.get("name") or raw.get("title") or ""
                sku = raw.get("sku") or ""

                # Non-laptop accessory and used/refurbished check
                item_url = f"{self.ITEM_BASE_URL}?id={slug}"
                is_valid, reason = self.is_valid_new_laptop(
                    title=name, url=item_url
                )
                if not is_valid:
                    self.record_skipped(
                        name=name,
                        url=item_url,
                        reason=f"Filtered out as standalone accessory or non-laptop: {reason}",
                        stage="accessory_filter",
                    )
                    continue

                # Watermark pre-check before making any PDP request
                if until_model and any(self._matches_watermark(ident, until_model) for ident in [name, sku, slug]):
                    print(f"[{self.store_name}] Watermark matched '{until_model}' at '{name}'. Halting crawl.")
                    watermark_hit = True
                    break

                product = self._parse_product(raw, level=level)
                if not product:
                    self.record_skipped(
                        name=name,
                        url=urljoin(self.base_url, f"/product/{slug}"),
                        reason="Failed to parse product data or PDP",
                        stage="card_parse",
                    )
                    continue

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

                    seen_slugs.add(slug)
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
        newest in-stock collection with Level 2 extraction. Otherwise, queries /search?q={query}.
        """
        query_clean = query.strip().lower()
        if query_clean in ("laptop", "laptops", "", "all"):
            return self.scrape_catalog(level=2, limit=limit)

        params = {
            "q": query,
            "filters": json.dumps({"category_id": [self.LAPTOPS_CATEGORY_ID]}),
            "sortBy": "created_at",
            "sortDir": "desc",
        }
        search_url = f"{self.SEARCH_BASE_URL}?{urlencode(params)}"
        print(f"[{self.store_name}] Searching query '{query}': {search_url}")
        html_text = self._fetch_html(search_url)
        if not html_text:
            return []

        rsc_text = self._decode_rsc_payload(html_text)
        raw_products = self._extract_products_from_rsc(rsc_text)
        if not raw_products:
            raw_products = self._extract_products_from_html(html_text)

        candidates: list[RetailerProduct] = []
        seen_slugs: set[str] = set()

        for raw in raw_products:
            slug = raw.get("slug")
            if not slug or slug in seen_slugs:
                continue

            product = self._parse_product(raw, level=2)
            if product:
                seen_slugs.add(slug)
                candidates.append(product)

            if len(candidates) >= limit:
                break

        return candidates

    def _parse_product(self, raw: dict, level: int = 2) -> RetailerProduct | None:
        """Parse raw product dictionary (from RSC or HTML fallback) into RetailerProduct."""
        slug = raw.get("slug")
        if not slug:
            return None

        title = raw.get("name") or raw.get("title") or ""
        if not title or len(title) < 5:
            return None

        product_url = f"{self.ITEM_BASE_URL}?id={slug}"

        # Price parsing
        price_val: float | None = None
        price_str: str | None = None
        price_data = raw.get("price")
        if isinstance(price_data, dict):
            current_p = price_data.get("current") or price_data.get("base")
            if current_p is not None:
                price_val, price_str = self.parse_egp_price(str(current_p))
        elif isinstance(price_data, (int, float, str)):
            price_val, price_str = self.parse_egp_price(str(price_data))
        if price_val is None and raw.get("price_str"):
            price_val, price_str = self.parse_egp_price(raw.get("price_str"))

        # In-stock
        in_stock = raw.get("is_stock")
        if in_stock is None:
            in_stock = True

        # Thumbnail
        thumbnail_url = None
        thumb_data = raw.get("thumbnail")
        if isinstance(thumb_data, dict):
            thumbnail_url = thumb_data.get("url")
        elif isinstance(thumb_data, str):
            thumbnail_url = thumb_data

        # Manufacturer SKU / MPN
        raw_sku = raw.get("sku") or None

        # Level 1 vs Level 2 specs
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        has_text_specs: bool = True
        specs_extraction_source: str = "dom"
        specs_fallback_reason: str | None = None
        has_specs_image: bool = False
        specs_image_url: str | None = None
        pattern_learned: bool = False
        learned_pattern_type: str | None = None

        if level == 2:
            spec_res = self._extract_product_specs(product_url, title=title)
            if isinstance(spec_res, tuple) and hasattr(spec_res, "specs"):
                specs = spec_res.specs
                raw_desc = spec_res.raw_description
                has_text_specs = spec_res.has_text_specs
                specs_extraction_source = spec_res.specs_extraction_source
                specs_fallback_reason = spec_res.specs_fallback_reason
                has_specs_image = spec_res.has_specs_image
                specs_image_url = spec_res.specs_image_url
                pattern_learned = spec_res.pattern_learned
                learned_pattern_type = spec_res.learned_pattern_type
            elif isinstance(spec_res, tuple) and len(spec_res) >= 2:
                specs = spec_res[0]
                raw_desc = spec_res[1]
                has_text_specs = bool(specs)

            pdp_valid, pdp_reason = self.is_valid_new_laptop(
                title=title,
                specs=specs,
                url=product_url,
                description=raw_desc,
            )
            if not pdp_valid:
                self.record_skipped(
                    name=title,
                    url=product_url,
                    reason=f"Filtered out after PDP inspection: {pdp_reason}",
                    stage="pdp_filter",
                )
                return None

        # Model normalizer token extraction
        combined_text = f"{title} {raw_sku or ''} {' '.join(specs.values())}"
        tokens = ModelNormalizer.extract_model_tokens(combined_text)

        mpn = raw_sku or tokens.get("mpn")
        model_code = tokens.get("full_sku") or tokens.get("base_model")

        return RetailerProduct(
            store_name=self.store_name,
            store_key=self.store_key,
            store_domain=self.base_domain,
            title=title,
            product_url=product_url,
            retailer_product_id=slug,
            retailer_sku=raw_sku or slug,
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
            pattern_learned=pattern_learned,
            learned_pattern_type=learned_pattern_type,
        )

    def _extract_product_specs(self, product_url: str, title: str = "") -> SigmaSpecResult:
        """Fetch Sigma Computer PDP to extract structured specifications array and description."""
        html_text = self._fetch_html(product_url)
        if not html_text:
            empty_res = SpecExtractionResult(
                has_text_specs=False,
                specs_extraction_source="none",
                specs_fallback_reason="Failed to fetch PDP HTML",
            )
            return SigmaSpecResult({}, None, empty_res)

        soup = BeautifulSoup(html_text, "html.parser")
        for s in soup(["style"]):
            s.decompose()

        soup_title = title
        if not soup_title:
            title_tag = soup.find("title")
            if title_tag:
                soup_title = title_tag.get_text(strip=True).split("|")[0].split("-")[0].strip()

        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=soup_title,
            store_key=self.store_key,
            base_url=self.base_url,
        )

        return SigmaSpecResult(spec_res.specs, spec_res.raw_description, spec_res)

    def _extract_products_from_html(self, html_text: str) -> list[dict]:
        """Resilient DOM fallback for catalog cards if RSC extraction fails."""
        soup = BeautifulSoup(html_text, "html.parser")
        products: list[dict] = []
        links = soup.find_all("a", href=lambda h: h and "/en/item?id=" in h)
        seen = set()

        for a in links:
            href = a.get("href", "")
            slug = href.split("id=")[-1].split("&")[0]
            if not slug or slug in seen:
                continue

            card = a.parent
            for _ in range(4):
                if card and any("rounded" in c for c in card.get("class", [])):
                    break
                if card:
                    card = card.parent

            title = a.get_text(strip=True)
            if not title and card:
                title_elem = card.find(["h2", "h3", "h4", "p"])
                if title_elem:
                    title = title_elem.get_text(strip=True)

            price_str = None
            if card:
                price_elem = card.find(string=re.compile(r"EGP|\d+,\d+", re.I))
                if price_elem:
                    price_str = str(price_elem).strip()

            img_url = None
            if card:
                img_elem = card.find("img")
                if img_elem:
                    img_url = img_elem.get("src")

            if title and len(title) >= 5:
                seen.add(slug)
                products.append(
                    {
                        "slug": slug,
                        "name": title,
                        "sku": None,
                        "price_str": price_str,
                        "thumbnail": img_url,
                        "is_stock": True,
                    }
                )

        return products
