import json
import re
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup


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

    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        if not html:
            return None, False

        soup = BeautifulSoup(html, "html.parser")

        price: float | None = None
        in_stock: bool | None = None

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
                        if "InStock" in avail:
                            in_stock = True
                        elif "OutOfStock" in avail:
                            in_stock = False
                    break
            except Exception:
                pass

        # 2. Fallback: Micro CSS selectors
        if price is None:
            elem = soup.select_one(".price__current, .product-price, .price")
            if elem:
                price = parse_egp_number(elem.get_text(strip=True))

        # 3. Stock evaluation fallback
        if in_stock is None:
            sold_out = soup.select_one(".product-label--sold-out, .sold-out, [data-sold-out]")
            if sold_out or "sold out" in soup.get_text().lower():
                in_stock = False
            else:
                in_stock = True

        return price, in_stock if in_stock is not None else True


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
                        if "OutOfStock" in avail:
                            in_stock = False
                        elif "InStock" in avail or "PreOrder" in avail:
                            in_stock = True
                    break
            except Exception:
                pass

        # 2. Fallback: CSS Selectors
        if price is None:
            elem = soup.select_one(".product-price-group .price-new, .product-price, .autocalc_price, .price")
            if elem:
                price = parse_egp_number(elem.get_text(strip=True))

        # Check stock element markers
        oos_elem = soup.select_one(".product-out-of-stock, .out-of-stock, .stock-out")
        if oos_elem:
            in_stock = False

        return price, in_stock


class SigmaPriceExtractor(BasePriceExtractor):
    """Extractor for Sigma Computer Egypt (Next.js App Router)."""

    def extract_price_and_stock(self, html: str, url: str) -> tuple[float | None, bool]:
        if not html:
            return None, False

        price: float | None = None
        in_stock: bool = True

        # 1. Primary: Next.js React Server Component (RSC) streamed payload
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

            # Extract the item's price object: "price":{"base":..., "current":...}
            price_match = re.search(r'"price":\s*\{\s*"base":\s*(\d+),\s*"current":\s*(\d+)', decoded)
            if price_match:
                price = float(price_match.group(2))

            # Extract stock boolean
            stock_match = re.search(r'"is_stock":\s*(true|false)', decoded, re.IGNORECASE)
            if stock_match:
                in_stock = stock_match.group(1).lower() == "true"

        # 2. Fallback: Standard DOM regex if RSC was not present
        if price is None:
            soup = BeautifulSoup(html, "html.parser")
            for text_node in soup.find_all(string=re.compile(r"(?:EGP|LE|ج\.م)\s*[\d,]+|[\d,]+\s*(?:EGP|LE|ج\.م)")):
                p = parse_egp_number(str(text_node))
                if p and p > 5000:
                    price = p
                    break

        return price, in_stock


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
