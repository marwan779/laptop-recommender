from urllib.parse import quote_plus, urljoin

from app.core.normalizer import ModelNormalizer
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class TwoBStoreScraper(BaseStoreScraper):
    """Store scraper for 2B Egypt (https://2b.com.eg).

    Customized for Magento 2 catalog search and attribute specs structure.
    """

    @property
    def store_name(self) -> str:
        return "2B"

    @property
    def store_key(self) -> str:
        return "twob"

    @property
    def base_url(self) -> str:
        return "https://2b.com.eg"

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        # Prefer English catalogsearch endpoint for Latin model names, works with Arabic as well
        search_url = f"{self.base_url}/en/catalogsearch/result/?q={quote_plus(query)}"

        doc = self.engine.fetch(search_url, stealth=True, network_idle=True)
        raw_page = doc.raw

        candidates: list[RetailerProduct] = []
        if not hasattr(raw_page, "css"):
            return candidates

        # Magento 2 product listing selectors
        cards = raw_page.css(
            "li.product-item, div.product-item-info, div.product-item, "
            "div[class*=\"product-item-details\"]"
        )

        seen_urls: set[str] = set()

        for card in cards:
            link_el = card.css("a.product-item-link, a[class*=\"product-item-photo\"], a[href*=\".html\"]")
            if not link_el:
                continue

            href = link_el[0].attrib.get("href", "")
            if not href or href == "#":
                continue

            full_url = urljoin(self.base_url, href)
            if full_url in seen_urls:
                continue

            # Title
            title = ""
            title_el = card.css("a.product-item-link, strong.product-name a, h2, h3")
            if title_el:
                title = title_el[0].text.strip()
            if not title and hasattr(link_el[0], "text"):
                title = link_el[0].text.strip()

            if not title or len(title) < 5:
                continue

            # Avoid accessories
            if self._is_standalone_accessory(title):
                continue

            # Price
            price_text = None
            price_el = card.css(
                "span[data-price-type=\"finalPrice\"] span.price, "
                "span.price-wrapper span.price, span.price, [class*=\"price\"]"
            )
            if price_el:
                price_text = price_el[0].text.strip()

            price_val, price_str = self.parse_egp_price(price_text)

            # Stock check
            card_text_lower = card.text.lower()
            in_stock = True
            if "out of stock" in card_text_lower or "غير متوفر" in card_text_lower or "unavailable" in card_text_lower:
                in_stock = False

            # Thumbnail
            img_url = None
            img_el = card.css("img.product-image-photo, img[src]")
            if img_el:
                img_url = urljoin(self.base_url, img_el[0].attrib.get("src", ""))

            seen_urls.add(full_url)

            # Deep spec extraction from product page (and price fallback)
            specs, raw_desc, page_price_val, page_price_str = self._extract_product_specs(full_url)
            final_price_val = price_val if price_val is not None else page_price_val
            final_price_str = price_str if price_str is not None else page_price_str

            # Parse MPN, Part Number, and Model directly from specs table or text
            mpn = (
                specs.get("MPN")
                or specs.get("Part Number")
                or specs.get("part_number")
                or specs.get("mpn")
            )
            extracted_model = specs.get("Model") or title

            combined_text = f"{title} {extracted_model} {mpn or ''} {' '.join(specs.values())}"
            tokens = ModelNormalizer.extract_model_tokens(combined_text)

            candidates.append(
                RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain="2b.com.eg",
                    title=title,
                    product_url=full_url,
                    retailer_product_id=full_url.split("/")[-1].replace(".html", ""),
                    mpn=mpn or tokens.get("mpn"),
                    model_code=tokens.get("full_sku"),
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
    ) -> tuple[dict[str, str], str | None, float | None, str | None]:
        """Fetch 2B product page to extract Magento specification table and price fallback."""
        try:
            doc = self.engine.fetch(product_url, stealth=False)
            raw = doc.raw
            specs: dict[str, str] = {}
            raw_desc = None
            page_price_val = None
            page_price_str = None

            if hasattr(raw, "css"):
                # Price fallback from product page meta or price-box
                price_meta = raw.css("meta[property*='price:amount'], meta[itemprop='price']")
                if price_meta:
                    p_txt = price_meta[0].attrib.get("content")
                    if p_txt:
                        page_price_val, page_price_str = self.parse_egp_price(p_txt)

                if page_price_val is None:
                    page_price_el = raw.css(
                        "span[data-price-type='finalPrice'] span.price, .price-box span.price, span.price"
                    )
                    if page_price_el:
                        page_price_val, page_price_str = self.parse_egp_price(page_price_el[0].text.strip())

                # Magento 2 additional attributes table
                table_rows = raw.css(
                    "table#product-attribute-specs-table tr, "
                    "div.additional-attributes-wrapper tr, table tr"
                )
                for row in table_rows:
                    cells = row.css("td, th")
                    if len(cells) >= 2:
                        k = cells[0].text.strip()
                        v = cells[1].text.strip()
                        if k and v and len(k) < 60:
                            specs[k] = v

                desc_el = raw.css("div.product.attribute.overview, div.description div.value")
                if desc_el:
                    raw_desc = desc_el[0].text.strip()[:1000]

            return specs, raw_desc, page_price_val, page_price_str
        except Exception as e:
            print(f"[{self.store_name}] Failed to extract product details from {product_url}: {e}")
            return {}, None, None, None
