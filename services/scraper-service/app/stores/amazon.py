import itertools
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class AmazonStoreScraper(BaseStoreScraper):
    """Store scraper for Amazon Egypt (https://www.amazon.eg).

    Supports:
      - Level 1: Fast catalog card summary extracting ASIN, title, price, availability,
        and thumbnail without extra HTTP requests.
      - Level 2: Deep PDP specification table extraction from Amazon technical details tables.
      - Watermark stopping via `until_model` for incremental scraping (sorted by newest arrivals).
      - Candidate search via Amazon search query `https://www.amazon.eg/s?k={query}&language=en_AE`.
    """

    CATALOG_URL_TEMPLATE = (
        "https://www.amazon.eg/s?i=computers&rh=n%3A21832907031&s=date-desc-rank&language=en_AE&page={page}"
    )
    SEARCH_URL_TEMPLATE = "https://www.amazon.eg/s?k={query}&language=en_AE"


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
        return "Amazon Egypt"

    @property
    def store_key(self) -> str:
        return "amazon"

    @property
    def base_url(self) -> str:
        return "https://www.amazon.eg"

    @property
    def base_domain(self) -> str:
        return "amazon.eg"

    def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML using Scrapling engine or fallback curl_cffi session with Chrome 120 impersonation."""
        if self.engine:
            try:
                doc = self.engine.fetch(url, stealth=True)
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
        level: int = 1,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[RetailerProduct]:
        """Scrape the canonical laptops catalog sorted by newest first.

        Args:
            level: 1 for fast catalog card summaries, 2 for deep PDP spec crawling. Default: 1.
            until_model: Optional watermark pointer (name, MPN, SKU, or slug). Default: None.
            max_pages: Optional pagination ceiling. If None or 0, crawls all pages. Default: None.
            limit: Maximum products to return. Default: None.
        """
        products: list[RetailerProduct] = []
        seen_asins: set[str] = set()
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
            if not html_text:
                print(f"[{self.store_name}] Empty response for page {page}. Halting crawl.")
                break

            soup = BeautifulSoup(html_text, "html.parser")
            cards = soup.select("div.s-result-item[data-asin]")
            valid_cards = [c for c in cards if c.get("data-asin", "").strip()]

            if not valid_cards:
                print(f"[{self.store_name}] No product cards with ASIN found on page {page}. Halting.")
                break

            print(f"[{self.store_name}] Page {page}: Found {len(valid_cards)} product cards.")

            for card in valid_cards:
                asin = card.get("data-asin", "").strip()
                if not asin or asin in seen_asins:
                    continue

                # Title extraction
                title_el = card.select_one("h2 a span") or card.select_one("h2 span") or card.select_one("h2 a")
                title = title_el.get_text(strip=True) if title_el else ""

                if not title or len(title) < 5:
                    self.record_skipped(
                        name=title or asin,
                        url=f"https://www.amazon.eg/dp/{asin}",
                        reason="Title too short or missing",
                        stage="level1_parse",
                    )
                    continue

                # Link extraction
                link_el = card.select_one("h2 a[href]")
                raw_href = link_el.get("href", "") if link_el else ""
                clean_url = f"https://www.amazon.eg/dp/{asin}"

                # Pre-enrichment watermark check
                url_slug = raw_href.split("/")[1] if "/" in raw_href else asin
                if until_model and any(
                    self._matches_watermark(ident, until_model) for ident in [title, asin, url_slug, clean_url]
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

                seen_asins.add(asin)

                # Price extraction
                price_el = card.select_one(".a-price .a-offscreen")
                price_text = None
                if price_el:
                    price_text = price_el.get_text(strip=True)
                else:
                    whole_el = card.select_one(".a-price-whole")
                    frac_el = card.select_one(".a-price-fraction")
                    if whole_el:
                        w_text = whole_el.get_text(strip=True).replace(",", "")
                        f_text = frac_el.get_text(strip=True) if frac_el else "00"
                        price_text = f"{w_text}.{f_text} EGP"

                price_val, price_str = self.parse_egp_price(price_text)

                # Stock detection
                card_text_lower = card.get_text(" ", strip=True).lower()
                is_unavailable = (
                    "currently unavailable" in card_text_lower
                    or "out of stock" in card_text_lower
                    or "غير متوفر حالياً" in card_text_lower
                )
                in_stock = price_val is not None and not is_unavailable

                # Thumbnail image
                img_el = card.select_one("img.s-image[src]")
                thumbnail_url = img_el.get("src") if img_el else None

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

                    # Post-enrichment watermark check on PDP identifiers
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
                    retailer_product_id=asin,
                    retailer_sku=asin,
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
        """Search Amazon Egypt by query string and return raw candidate RetailerProducts."""
        search_url = self.SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
        print(f"[{self.store_name}] Searching query '{query}': {search_url}")
        html_text = self._fetch_html(search_url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.select("div.s-result-item[data-asin]")
        valid_cards = [c for c in cards if c.get("data-asin", "").strip()]

        candidates: list[RetailerProduct] = []
        seen_asins: set[str] = set()

        for card in valid_cards:
            asin = card.get("data-asin", "").strip()
            if not asin or asin in seen_asins:
                continue

            title_el = card.select_one("h2 a span") or card.select_one("h2 span") or card.select_one("h2 a")
            title = title_el.get_text(strip=True) if title_el else ""

            if not title or len(title) < 5 or self._is_standalone_accessory(title):
                continue

            seen_asins.add(asin)
            clean_url = f"https://www.amazon.eg/dp/{asin}"

            price_el = card.select_one(".a-price .a-offscreen")
            price_text = price_el.get_text(strip=True) if price_el else None
            price_val, price_str = self.parse_egp_price(price_text)

            card_text_lower = card.get_text(" ", strip=True).lower()
            in_stock = (
                price_val is not None
                and "currently unavailable" not in card_text_lower
                and "out of stock" not in card_text_lower
            )

            img_el = card.select_one("img.s-image[src]")
            thumbnail_url = img_el.get("src") if img_el else None

            # Enrich candidates with Level 2 PDP specs
            pdp_specs, pdp_desc, pdp_mpn, pdp_model, pdp_pval, pdp_pstr, pdp_stock = self._extract_product_specs(
                clean_url
            )
            final_price_val = price_val if price_val is not None else pdp_pval
            final_price_str = price_str if price_str is not None else pdp_pstr
            if pdp_stock is not None:
                in_stock = pdp_stock

            tokens = ModelNormalizer.extract_model_tokens(
                f"{title} {pdp_model or ''} {pdp_mpn or ''} {' '.join(pdp_specs.values())}"
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
                    retailer_product_id=asin,
                    retailer_sku=asin,
                    mpn=mpn,
                    model_code=model_code,
                    sub_model=tokens.get("sub_model"),
                    base_model=tokens.get("base_model"),
                    price_egp=final_price_val,
                    price_str=final_price_str,
                    in_stock=in_stock,
                    thumbnail_url=thumbnail_url,
                    specs=pdp_specs,
                    raw_description=pdp_desc,
                )
            )

            if len(candidates) >= limit:
                break

        return candidates

    def _extract_product_specs(
        self, product_url: str
    ) -> tuple[dict[str, str], str | None, str | None, str | None, float | None, str | None, bool | None]:
        """Fetch Amazon PDP HTML and extract tech spec table rows, description, price, stock, and MPN."""
        html_text = self._fetch_html(product_url)
        if not html_text:
            return {}, None, None, None, None, None, None

        soup = BeautifulSoup(html_text, "html.parser")
        specs: dict[str, str] = {}
        raw_desc: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        in_stock: bool | None = None

        # Stock check from availability div
        avail_el = soup.select_one("#availability, .availability")
        if avail_el:
            avail_text = avail_el.get_text(strip=True).lower()
            if "currently unavailable" in avail_text or "out of stock" in avail_text or "غير متوفر حالياً" in avail_text:
                in_stock = False
            elif "in stock" in avail_text or "متوفر" in avail_text:
                in_stock = True

        # Price fallback from PDP priceblock or price offscreen
        price_el = soup.select_one("#corePrice_feature_div .a-offscreen, #priceblock_ourprice, .a-price .a-offscreen")
        if price_el:
            price_val, price_str = self.parse_egp_price(price_el.get_text(strip=True))

        # Specs tables: #productDetails_techSpec_section_1, #poExpander, #detailBullets_feature_div
        for selector in [
            "#productDetails_techSpec_section_1 tr",
            "#productDetails_db_sections tr",
            "#poExpander tr",
            ".prodDetTable tr",
        ]:
            for row in soup.select(selector):
                th = row.select_one("th")
                td = row.select_one("td")
                if th and td:
                    k = th.get_text(strip=True)
                    v = td.get_text(" ", strip=True)
                    if k and v and len(k) < 60:
                        specs[k] = v

        # Bullets / overview fallback
        if not specs:
            for li in soup.select("#detailBullets_feature_div ul li, #productOverview_feature_div tr"):
                spans = li.select("span")
                if len(spans) >= 2:
                    k = spans[0].get_text(strip=True).rstrip(":\u200e\u200f ")
                    v = spans[1].get_text(" ", strip=True)
                    if k and v and len(k) < 60:
                        specs[k] = v

        # Description
        desc_el = soup.select_one("#productDescription, #feature-bullets")
        if desc_el:
            raw_desc = desc_el.get_text(" ", strip=True)[:1500]

        mpn = (
            specs.get("Item model number") or specs.get("Part Number") or specs.get("Model Number") or specs.get("MPN")
        )
        model_code = specs.get("Model Name") or specs.get("Model")

        return specs, raw_desc, mpn, model_code, price_val, price_str, in_stock
