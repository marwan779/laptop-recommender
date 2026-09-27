from urllib.parse import quote_plus, urljoin

from app.core.normalizer import ModelNormalizer
from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper


class SigmaComputerStoreScraper(BaseStoreScraper):
    """Store scraper for Sigma Computer Egypt (https://www.sigma-computer.com/en).

    Customized for OpenCart catalog search structure.
    """

    @property
    def store_name(self) -> str:
        return "Sigma Computer"

    @property
    def store_key(self) -> str:
        return "sigma"

    @property
    def base_url(self) -> str:
        return "https://www.sigma-computer.com/en"

    def search_candidates(self, query: str, limit: int = 5) -> list[RetailerProduct]:
        search_url = f"{self.base_url}/search?search={quote_plus(query)}"

        doc = self.engine.fetch(search_url, stealth=True, network_idle=True)
        raw_page = doc.raw

        candidates: list[RetailerProduct] = []
        if not hasattr(raw_page, "css"):
            return candidates

        cards = raw_page.css(
            "div.product-layout, div.product-thumb, div[class*=\"product-grid\"], "
            "div[class*=\"product-item\"], div.item"
        )

        seen_urls: set[str] = set()

        for card in cards:
            link_el = card.css("h4 a, a[href*=\"/item\"], a[href*=\"/product\"]")
            if not link_el:
                link_el = card.css("a[href]")
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
            title_el = card.css("h4 a, .caption h4, [class*=\"title\"]")
            if title_el:
                title = title_el[0].text.strip()
            if not title and hasattr(link_el[0], "text"):
                title = link_el[0].text.strip()

            if not title or len(title) < 5:
                continue

            # Avoid accessories
            if any(acc in title.lower() for acc in ["backpack", "sleeve", "bag", "adapter", "charger", "cable", "mouse", "headset"]):
                continue

            # Price
            price_text = None
            price_el = card.css("span.price-new, p.price, .price, [class*=\"price\"]")
            if price_el:
                price_text = price_el[0].text.strip()
                lines = price_text.splitlines()
                if lines:
                    price_text = lines[0].strip()

            price_val, price_str = self.parse_egp_price(price_text)

            # Stock check
            card_text_lower = card.text.lower()
            in_stock = True
            if "out of stock" in card_text_lower or "غير متوفر" in card_text_lower:
                in_stock = False

            # Thumbnail
            img_url = None
            img_el = card.css("img[src]")
            if img_el:
                img_url = urljoin(self.base_url, img_el[0].attrib.get("src", ""))

            seen_urls.add(full_url)

            # Deep spec extraction from product page
            specs, raw_desc, page_price_val, page_price_str = self._extract_product_specs(full_url)
            final_price_val = price_val if price_val is not None else page_price_val
            final_price_str = price_str if price_str is not None else page_price_str

            # Parse model tokens from title and specs
            combined_text = f"{title} {' '.join(specs.values())}"
            tokens = ModelNormalizer.extract_model_tokens(combined_text)

            # Extract retailer product ID if in query params (e.g. ?id=123)
            pid = None
            if "id=" in full_url:
                pid = full_url.split("id=")[-1].split("&")[0]

            candidates.append(
                RetailerProduct(
                    store_name=self.store_name,
                    store_key=self.store_key,
                    store_domain="sigma-computer.com",
                    title=title,
                    product_url=full_url,
                    retailer_product_id=pid,
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
        """Fetch Sigma Computer product page to extract specs table."""
        try:
            doc = self.engine.fetch(product_url, stealth=False)
            raw = doc.raw
            specs: dict[str, str] = {}
            raw_desc = None
            page_price_val = None
            page_price_str = None

            if hasattr(raw, "css"):
                # Price fallback
                price_el = raw.css("span.price-new, h2.price, .product-price")
                if price_el:
                    page_price_val, page_price_str = self.parse_egp_price(price_el[0].text.strip())

                # OpenCart specification table
                table_rows = raw.css("div#tab-specification tr, table.table-bordered tr, table tr")
                for row in table_rows:
                    cells = row.css("td, th")
                    if len(cells) >= 2:
                        k = cells[0].text.strip()
                        v = cells[1].text.strip()
                        if k and v and len(k) < 60:
                            specs[k] = v

                desc_el = raw.css("div#tab-description, div[class*=\"description\"]")
                if desc_el:
                    raw_desc = desc_el[0].text.strip()[:1000]

            return specs, raw_desc, page_price_val, page_price_str
        except Exception as e:
            print(f"[{self.store_name}] Failed to extract product details from {product_url}: {e}")
            return {}, None, None, None
