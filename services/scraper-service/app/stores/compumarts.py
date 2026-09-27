from urllib.parse import quote_plus, urljoin

from app.matching.normalizer import ModelNormalizer
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class CompumartsStoreScraper(BaseStoreScraper):
    """Store scraper for Compumarts Egypt (https://www.compumarts.com).

    Customized for Shopify catalog search structure.
    """

    @property
    def store_name(self) -> str:
        return "Compumarts"

    @property
    def store_key(self) -> str:
        return "compumarts"

    @property
    def base_url(self) -> str:
        return "https://www.compumarts.com"

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        search_url = f"{self.base_url}/search?type=product&q={quote_plus(query)}"

        doc = self.engine.fetch(search_url, stealth=True, network_idle=True)
        raw_page = doc.raw

        candidates: list[RetailerProduct] = []
        if not hasattr(raw_page, "css"):
            return candidates

        # Shopify search product selectors
        cards = raw_page.css(
            "div.product-card, div.grid-product, div[class*=\"product-item\"], "
            "div[class*=\"productCard\"], li[class*=\"grid__item\"], div[class*=\"grid-item\"]"
        )

        seen_urls: set[str] = set()

        for card in cards:
            link_el = card.css("a[href*=\"/products/\"]")
            if not link_el:
                continue

            href = link_el[0].attrib.get("href", "")
            full_url = urljoin(self.base_url, href.split("?")[0])

            if full_url in seen_urls:
                continue

            # Extract Title
            title = ""
            title_el = card.css(".product-card__title, .grid-product__title, h2, h3, a[href*=\"/products/\"]")
            if title_el:
                title = title_el[0].text.strip()
            if not title and hasattr(link_el[0], "text"):
                title = link_el[0].text.strip()

            if not title or len(title) < 5:
                continue

            # Drop accessories (mouse, charger, bag, cover)
            if any(acc in title.lower() for acc in ["backpack", "sleeve", "bag", "adapter", "charger", "cable", "mouse"]):
                continue

            # Extract Price
            price_text = None
            price_el = card.css(
                "span.price-item--sale, span.price-item, .product-card__price, "
                ".price, [class*=\"price\"]"
            )
            if price_el:
                for p in price_el:
                    txt = p.text.strip()
                    if txt and any(c.isdigit() for c in txt):
                        price_text = txt
                        break

            price_val, price_str = self.parse_egp_price(price_text)

            # In Stock check
            card_text_lower = card.text.lower()
            in_stock = True
            if "sold out" in card_text_lower or "out of stock" in card_text_lower or "غير متوفر" in card_text_lower:
                in_stock = False

            # Extract thumbnail
            img_url = None
            img_el = card.css("img[src]")
            if img_el:
                src = img_el[0].attrib.get("src", "")
                if src.startswith("//"):
                    src = "https:" + src
                img_url = urljoin(self.base_url, src)

            seen_urls.add(full_url)

            # Extract product specs & description from detail page
            specs, raw_desc, page_price_val, page_price_str = self._extract_product_specs(full_url)
            final_price_val = price_val if price_val is not None else page_price_val
            final_price_str = price_str if price_str is not None else page_price_str

            # Parse model tokens from title and specs
            combined_text = f"{title} {' '.join(specs.values())}"
            tokens = ModelNormalizer.extract_model_tokens(combined_text)

            candidates.append(
                RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain="compumarts.com",
                    title=title,
                    product_url=full_url,
                    retailer_product_id=full_url.split("/")[-1],
                    mpn=tokens.get("mpn"),
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
        """Fetch the product page to extract granular specs table and description."""
        try:
            doc = self.engine.fetch(product_url, stealth=False)
            raw = doc.raw
            specs: dict[str, str] = {}
            raw_desc = None
            page_price_val = None
            page_price_str = None

            if hasattr(raw, "css"):
                # Price fallback
                price_el = raw.css("span.price-item, .price-item--regular, meta[property='product:price:amount']")
                if price_el:
                    txt = price_el[0].attrib.get("content") or price_el[0].text.strip()
                    page_price_val, page_price_str = self.parse_egp_price(txt)

                # Specification table
                table_rows = raw.css("table tr, div[class*=\"specification\"] tr, div[class*=\"spec\"] tr")
                for row in table_rows:
                    cells = row.css("td, th")
                    if len(cells) >= 2:
                        k = cells[0].text.strip()
                        v = cells[1].text.strip()
                        if k and v and len(k) < 60:
                            specs[k] = v

                # Description container
                desc_el = raw.css(
                    "div.product__description, div.product-single__description, "
                    "div[class*=\"description\"], div#description"
                )
                if desc_el:
                    raw_desc = desc_el[0].text.strip()[:1000]

            return specs, raw_desc, page_price_val, page_price_str
        except Exception as e:
            print(f"[{self.store_name}] Failed to extract product details from {product_url}: {e}")
            return {}, None, None, None
