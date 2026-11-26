import json
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup, Tag


_EXCLUDED_RECOMMENDATION_SELECTORS = (
    ".product-recommendations",
    ".related-products",
    "[data-section-type='product-recommendations']",
    "recommended-products",
    "product-card",
    "[class*='related']",
    "[class*='recommend']",
    "[class*='carousel']",
    "nav",
    "footer",
    "aside",
)


def _iter_json_ld_products(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Yield Schema.org Product dictionaries from JSON-LD script tags."""
    products: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = json.loads(script.string or "")
        except Exception:
            continue

        candidates: list[Any] = []
        if isinstance(raw, list):
            candidates.extend(raw)
        elif isinstance(raw, dict):
            if isinstance(raw.get("@graph"), list):
                candidates.extend(raw["@graph"])
            candidates.append(raw)

        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            is_product = item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type)
            if is_product:
                products.append(item)
    return products


def _extract_offer_price_and_stock(offers_obj: Any) -> tuple[float | None, bool | None]:
    """Extract numeric price and availability from Schema.org offers dict or list."""
    offer_list: list[dict[str, Any]]
    if isinstance(offers_obj, dict):
        offer_list = [offers_obj]
    elif isinstance(offers_obj, list):
        offer_list = [o for o in offers_obj if isinstance(o, dict)]
    else:
        return None, None

    if not offer_list:
        return None, None

    price: float | None = None
    in_stock: bool | None = None
    for offer in offer_list:
        if price is None:
            raw_p = offer.get("price") or offer.get("lowPrice")
            if raw_p is not None and str(raw_p).strip():
                price = parse_egp_number(str(raw_p))

        avail = str(offer.get("availability", ""))
        if "InStock" in avail:
            in_stock = True
        elif any(tok in avail for tok in ("OutOfStock", "PreOrder", "SoldOut", "Discontinued", "BackOrder")) and in_stock is None:
            in_stock = False

    return price, in_stock


def _build_primary_scope(soup: BeautifulSoup, container_selectors: tuple[str, ...]) -> BeautifulSoup | Tag:
    """Return a copy of the primary PDP container stripped of related/recommendation widgets."""
    root: Tag | None = None
    for selector in container_selectors:
        found = soup.select_one(selector)
        if found is not None:
            root = found
            break

    working = BeautifulSoup(str(root or soup), "html.parser")
    for sel in _EXCLUDED_RECOMMENDATION_SELECTORS:
        for node in working.select(sel):
            node.decompose()
    return working


def _extract_target_slug(url: str) -> str | None:
    """Extract target product slug from a PDP URL (?id=<slug> or last path segment)."""
    if not url:
        return None
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if qs.get("id"):
        slug = str(qs["id"][0]).strip().lower()
        return slug or None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[-2].lower() in ("product", "products", "item", "items"):
        return parts[-1].strip().lower() or None
    return None


def _extract_balanced_json_object(text: str, anchor_pos: int) -> dict[str, Any] | None:
    """Locate and parse the innermost valid JSON object enclosing anchor_pos."""
    # Walk left to find opening '{' candidates, then match forward with string-escape tracking.
    start = anchor_pos
    attempts = 0
    while start >= 0 and attempts < 32:
        start = text.rfind("{", 0, start)
        if start == -1:
            return None
        attempts += 1

        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    if i >= anchor_pos:
                        try:
                            parsed = json.loads(text[start : i + 1])
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            break
                    else:
                        break
    return None


def _coerce_stock_value(raw_stock: Any) -> bool | None:
    """Coerce boolean, int, or string RSC stock flags into bool."""
    if isinstance(raw_stock, bool):
        return raw_stock
    if isinstance(raw_stock, (int, float)):
        return bool(raw_stock)
    if isinstance(raw_stock, str):
        cleaned = raw_stock.strip().lower()
        if cleaned in ("true", "1", "yes"):
            return True
        if cleaned in ("false", "0", "no"):
            return False
    return None


def _extract_sigma_rsc_price_and_stock(decoded: str, target_slug: str | None) -> tuple[float | None, bool | None, bool]:
    """Extract target product price & stock from Sigma RSC text without matching wrong items.

    Returns:
        tuple[price, in_stock, has_slugged_products]
    """
    slugged_objects: list[dict[str, Any]] = []
    seen_ranges: set[int] = set()
    for match in re.finditer(r'"slug"\s*:\s*"([^"]+)"', decoded):
        pos = match.start()
        if pos in seen_ranges:
            continue
        seen_ranges.add(pos)
        obj = _extract_balanced_json_object(decoded, pos)
        if isinstance(obj, dict) and isinstance(obj.get("slug"), str):
            if "price" in obj or "is_stock" in obj:
                slugged_objects.append(obj)

    selected: dict[str, Any] | None = None
    if slugged_objects:
        if target_slug:
            for obj in slugged_objects:
                if str(obj["slug"]).strip().lower() == target_slug:
                    selected = obj
                    break
            if selected is None:
                # Multiple/other products existed in RSC, none matched target_slug -> refuse mismatch.
                return None, None, True
        elif len(slugged_objects) == 1:
            selected = slugged_objects[0]
        else:
            return None, None, True

    if selected is not None:
        price: float | None = None
        price_obj = selected.get("price")
        if isinstance(price_obj, dict):
            raw_p = price_obj.get("current") if price_obj.get("current") is not None else price_obj.get("base")
            if raw_p is not None:
                price = parse_egp_number(str(raw_p))
        elif price_obj is not None:
            price = parse_egp_number(str(price_obj))

        stock = _coerce_stock_value(selected.get("is_stock"))
        return price, stock, True

    # Fallback when RSC has an anonymous product snippet with no slug fields
    price = None
    stock = None
    price_match = re.search(
        r'"price"\s*:\s*\{\s*"base"\s*:\s*([\d.]+)\s*,\s*"current"\s*:\s*([\d.]+)',
        decoded,
    )
    if price_match:
        price = float(price_match.group(2))
    stock_match = re.search(r'"is_stock"\s*:\s*(true|false)', decoded, re.IGNORECASE)
    if stock_match:
        stock = stock_match.group(1).lower() == "true"

    return price, stock, False


def parse_egp_number(raw_text: str | None) -> float | None:
    """Extract and parse a clean float price in EGP from mixed text."""
    if not raw_text:
        return None

    # Replace Arabic numerals with standard ASCII
    arabic_numerals = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    cleaned = str(raw_text).translate(arabic_numerals)

    # Remove currency words
    cleaned = re.sub(r"(?i)\b(?:egp|le|l\.e|جنيه|ج\.م)\b", "", cleaned)

    # Extract all digits, commas, and dots
    match = re.search(r"(\d[\d,\. ]*)", cleaned)
    if not match:
        return None

    val_str = match.group(1).strip()
    val_str = val_str.replace(" ", "")

    # Handle standard European vs Egyptian notation (e.g. 81,500.00 vs 81.500,00)
    if "," in val_str and "." in val_str:
        if val_str.rfind(".") > val_str.rfind(","):
            # 81,500.00 -> comma is thousands
            val_str = val_str.replace(",", "")
        else:
            # 81.500,00 -> dot is thousands
            val_str = val_str.replace(".", "").replace(",", ".")
    elif "," in val_str:
        # e.g. 81,500 -> thousands separator
        val_str = val_str.replace(",", "")

    try:
        val = float(val_str)
        return val if val > 0 else None
    except ValueError:
        return None


class BasePriceExtractor(ABC):
    """Abstract base class for high-speed store price and stock extractors."""

    @abstractmethod
    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        """Extract current price in EGP and stock availability from raw HTML.

        Returns:
            tuple[price_egp, in_stock]
        """
        pass


class CompumartsPriceExtractor(BasePriceExtractor):
    """Extractor for Compumarts Egypt (Shopify-based)."""

    _PRIMARY_SELECTORS: tuple[str, ...] = (
        ".product-info",
        ".product__info-wrapper",
        ".product__info-container",
        ".product-single",
        ".product-detail",
        "main .product",
        "main",
    )

    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        if not html:
            return None, False

        soup = BeautifulSoup(html, "html.parser")
        price: float | None = None
        in_stock: bool | None = None

        # 1. Primary: Schema.org Product JSON-LD (preferring matching product handle when available)
        products = _iter_json_ld_products(soup)
        if products:
            path_parts = [p for p in urlparse(url).path.split("/") if p]
            handle = path_parts[-1].lower() if path_parts else ""
            chosen = products[0]
            if handle:
                for prod in products:
                    prod_ref = str(prod.get("url") or prod.get("@id") or "").lower()
                    if handle in prod_ref:
                        chosen = prod
                        break
            price, in_stock = _extract_offer_price_and_stock(chosen.get("offers"))

        # Scope DOM fallbacks to primary PDP region excluding related/recommendation cards
        scope = _build_primary_scope(soup, self._PRIMARY_SELECTORS)

        # 2. Fallback: Scoped CSS price selectors
        if price is None:
            elem = scope.select_one(".price__current, .product-price, .price")
            if elem:
                price = parse_egp_number(elem.get_text(strip=True))

        # 3. Fallback: Scoped stock evaluation (explicit badges and primary cart form button)
        if in_stock is None:
            sold_out_badge = scope.select_one(".product-label--sold-out, .sold-out, [data-sold-out]")
            if sold_out_badge is not None:
                in_stock = False
            else:
                add_btn = scope.select_one(
                    "form[action*='/cart/add'] button[name='add'], "
                    "form[action*='/cart/add'] button[type='submit'], "
                    "button[name='add']"
                )
                if add_btn is not None:
                    btn_text = add_btn.get_text(" ", strip=True).lower()
                    is_disabled = (
                        add_btn.has_attr("disabled") or str(add_btn.get("aria-disabled", "")).lower() == "true"
                    )
                    if is_disabled or any(
                        kw in btn_text
                        for kw in (
                            "sold out",
                            "out of stock",
                            "coming soon",
                            "pre-order",
                            "preorder",
                            "notify me",
                            "قريبا",
                            "قريباً",
                            "غير متوفر",
                            "نفذت الكمية",
                        )
                    ):
                        in_stock = False
                    else:
                        in_stock = True

        resolved_stock = in_stock if in_stock is not None else True
        if price is not None and price < 5000.0:
            resolved_stock = False
        return price, resolved_stock


class ElBadrPriceExtractor(BasePriceExtractor):
    """Extractor for El Badr Group Egypt (OpenCart-based)."""

    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        if not html:
            return None, False

        soup = BeautifulSoup(html, "html.parser")

        price: float | None = None
        in_stock: bool = True

        # 1. Primary: Schema.org Product JSON-LD
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, dict) and data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        raw_p = offers.get("price")
                        if raw_p:
                            price = parse_egp_number(str(raw_p))
                        avail = str(offers.get("availability", ""))
                        if any(tok in avail for tok in ("OutOfStock", "PreOrder", "SoldOut", "Discontinued", "BackOrder")):
                            in_stock = False
                        elif "InStock" in avail:
                            in_stock = True
                    break
            except Exception:
                pass

        # 2. Fallback: CSS Selectors
        if price is None:
            elem = soup.select_one(".product-price-group .price-new, .product-price, .autocalc_price, .price")
            if elem:
                price = parse_egp_number(elem.get_text(strip=True))

        # Check stock element markers & placeholder prices (e.g., 1 EGP coming soon)
        oos_elem = soup.select_one(".product-out-of-stock, .out-of-stock, .stock-out, .coming-soon")
        if oos_elem:
            in_stock = False
        if price is not None and price < 5000.0:
            in_stock = False

        return price, in_stock


class SigmaPriceExtractor(BasePriceExtractor):
    """Extractor for Sigma Computer Egypt (Next.js App Router)."""

    _PRIMARY_SELECTORS: tuple[str, ...] = (
        "[data-testid='product-detail']",
        ".product-detail",
        "main article",
        "main",
    )

    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        if not html:
            return None, False

        price: float | None = None
        in_stock: bool | None = None
        has_slugged_products = False

        # 1. Primary: Next.js React Server Component (RSC) streamed payload matched by target slug
        matches = re.findall(r'self\.__next_f\.push\((\[1,\s*".*?"\])\)', html)
        if matches:
            chunks: list[str] = []
            for m in matches:
                try:
                    parsed = json.loads(m)
                    if isinstance(parsed, list) and len(parsed) >= 2 and isinstance(parsed[1], str):
                        chunks.append(parsed[1])
                except Exception:
                    pass
            decoded = "".join(chunks)
            price, in_stock, has_slugged_products = _extract_sigma_rsc_price_and_stock(
                decoded,
                _extract_target_slug(url),
            )

        # 2. Fallback: Scoped DOM extraction only when RSC did not already reject a slug mismatch
        if price is None and not has_slugged_products:
            soup = BeautifulSoup(html, "html.parser")
            scope = _build_primary_scope(soup, self._PRIMARY_SELECTORS)
            # Strip sibling recommendation cards linking to other items
            for card_link in scope.select("a[href*='/item?id='], a[href*='/product/']"):
                card_parent = card_link.find_parent(class_=re.compile(r"card|rounded|product-item", re.I))
                if card_parent is not None:
                    card_parent.decompose()

            for text_node in scope.find_all(string=re.compile(r"(?:EGP|LE|ج\.م)\s*[\d,]+|[\d,]+\s*(?:EGP|LE|ج\.م)")):
                p = parse_egp_number(str(text_node))
                if p and p > 5000:
                    price = p
                    break

            if in_stock is None:
                oos_badge = scope.select_one(".out-of-stock, .sold-out, [data-sold-out]")
                if oos_badge is not None:
                    in_stock = False

        resolved_stock = in_stock if in_stock is not None else True
        if price is not None and price < 5000.0:
            resolved_stock = False
        return price, resolved_stock


class GenericPriceExtractor(BasePriceExtractor):
    """Universal fallback extractor using standard e-commerce patterns."""

    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        if not html:
            return None, False

        soup = BeautifulSoup(html, "html.parser")

        # 1. JSON-LD
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, dict) and data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        p = offers.get("price") or offers.get("lowPrice")
                        if p:
                            price = parse_egp_number(str(p))
                            avail = str(offers.get("availability", ""))
                            in_stock = "OutOfStock" not in avail
                            return price, in_stock
            except Exception:
                pass

        # 2. OpenGraph / Schema Meta tags
        meta_price = soup.find("meta", property="product:price:amount") or soup.find("meta", property="og:price:amount")
        if meta_price and meta_price.get("content"):
            p = parse_egp_number(meta_price["content"])
            if p:
                return p, True

        # 3. Common price classes
        elem = soup.select_one(".price, .current-price, .product-price, [data-price], .special-price")
        if elem:
            p = parse_egp_number(elem.get_text(strip=True))
            if p:
                return p, True

        return None, True


_EXTRACTORS: dict[str, BasePriceExtractor] = {
    "compumarts": CompumartsPriceExtractor(),
    "elbadr": ElBadrPriceExtractor(),
    "sigma": SigmaPriceExtractor(),
}


def get_price_extractor(store_key: str) -> BasePriceExtractor:
    """Return the designated price & stock extractor for a given store."""
    return _EXTRACTORS.get(store_key.lower().strip(), GenericPriceExtractor())
