import html
import itertools
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from app.core.normalizer import ModelNormalizer
from app.engine.base import IScraperEngine, ScrapedDocument
from app.schemas.laptop import ConfigurationItem, LaptopDetail, LaptopSummary
from app.scrapers.base import BaseBrandScraper


def parse_date_param(val: Any) -> datetime | None:
    """Normalize input date parameter (datetime, date, or str) into datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        if re.match(r"^\d{4}$", val_str):
            return datetime(int(val_str), 1, 1)
        try:
            return datetime.fromisoformat(val_str)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
    return None


def clean_html_text(raw_html: str | None) -> str:
    """Convert HTML snippet to clean, well-formatted plain text."""
    if not raw_html:
        return ""
    text = raw_html
    # Replace list items with clean bullet points
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean up excessive whitespace
    lines = [l.strip() for l in text.splitlines()]
    clean_lines = [l for l in lines if l]
    return " \n ".join(clean_lines) if clean_lines else ""


class LenovoDateExtractor:
    """Infers release date and generation year for Lenovo laptops."""

    HARDWARE_YEAR_MAP = [
        # Qualcomm Snapdragon X Elite / Plus - Mid 2024
        (re.compile(r"\b(?:Snapdragon|X\s+Elite|X\s+Plus)\b", re.I), 2024, "2024-06-01"),
        # Intel Core Ultra Series 2 (Lunar Lake) - Late 2024 / 2025
        (re.compile(r"\b(?:Ultra\s+[579]\s+2\d{2}[A-Za-z]?|288V|268V|258V|256V|228V|226V|Lunar\s+Lake)\b", re.I), 2024, "2024-09-01"),
        # AMD Strix Point (Ryzen AI 300) - Mid 2024
        (re.compile(r"\b(?:Ryzen\s+AI\s+9|HX\s+370|HX\s+365|Strix\s+Point)\b", re.I), 2024, "2024-07-01"),
        # Intel Core Ultra Series 1 (Meteor Lake) - Early 2024
        (re.compile(r"\b(?:Ultra\s+[579]\s+1\d{2}[A-Za-z]?|185H|165H|155H|135H|125H|Meteor\s+Lake)\b", re.I), 2024, "2024-01-01"),
        # AMD Hawk Point (Ryzen 8000) - Early 2024
        (re.compile(r"\b(?:Ryzen\s+[579]\s+8\d{3}|8945HS|8845HS|8645HS|Hawk\s+Point)\b", re.I), 2024, "2024-01-01"),
        # Intel 14th Gen HX / Refresh - 2024
        (re.compile(r"\b(?:14900HX|14700HX|14650HX|14th\s+Gen)\b", re.I), 2024, "2024-01-01"),
        # Intel 13th Gen (Raptor Lake) - 2023
        (re.compile(r"\b(?:13980HX|13900H|13700H|13500H|1335U|13th\s+Gen|Raptor\s+Lake)\b", re.I), 2023, "2023-01-01"),
        # AMD Phoenix (Ryzen 7000) - 2023
        (re.compile(r"\b(?:Ryzen\s+[579]\s+7\d{3}|7940HS|7840HS|7735HS|7535HS)\b", re.I), 2023, "2023-01-01"),
        # Intel 12th Gen (Alder Lake) - 2022
        (re.compile(r"\b(?:12900H|12700H|12500H|12th\s+Gen|Alder\s+Lake)\b", re.I), 2022, "2022-01-01"),
    ]

    GEN_YEAR_MAP = {
        "gen 12": (2024, "2024-03-01"),
        "gen 11": (2023, "2023-04-01"),
        "gen 10": (2022, "2022-04-01"),
        "gen 9": (2024, "2024-01-01"),
        "gen 8": (2023, "2023-01-01"),
        "gen 7": (2022, "2022-01-01"),
    }

    @classmethod
    def extract(cls, name: str, specs_text: str) -> tuple[str | None, int | None]:
        combined = f"{name} {specs_text}".lower()

        # 1. Hardware processor regex (Highest precision)
        for pattern, yr, dt in cls.HARDWARE_YEAR_MAP:
            if pattern.search(specs_text) or pattern.search(name):
                return dt, yr

        # 2. Generation patterns in name (e.g. "Gen 9", "Gen 12")
        for gen_str, (yr, dt) in cls.GEN_YEAR_MAP.items():
            if gen_str in combined:
                return dt, yr


        # 3. Model number suffix patterns (e.g. LOQ 15IRX10 -> Gen 10 = 2024/2025; LOQ 16IRH8 -> Gen 8 = 2023)
        match_suffix = re.search(r"\b\d{2}[A-Z]{3}(\d{1,2})\b", name)
        if match_suffix:
            gen_num = int(match_suffix.group(1))
            if gen_num >= 10:
                return "2024-01-01", 2024
            elif gen_num == 9:
                return "2024-01-01", 2024
            elif gen_num == 8:
                return "2023-01-01", 2023
            elif gen_num == 7:
                return "2022-01-01", 2022

        return None, None


class LenovoBrandScraper(BaseBrandScraper):
    """Official brand scraper for Lenovo Egypt catalog with deep Level 2 specification extraction."""

    PAGE_FILTER_ID = "d736b9e6-f1f1-46f4-8960-37d5996bb4b8"
    DLP_API_URL = "https://openapi.lenovo.com/eg/en/ofp/search/dlp/product/query/get/_tsc"
    TECH_SPECS_API_URL = "https://www.lenovo.com/eg/en/online/product/getTechSpecs.jhtm"

    @property
    def brand_name(self) -> str:
        return "Lenovo"

    @property
    def catalog_url(self) -> str:
        return "https://www.lenovo.com/eg/en/laptops/subseries-results/"

    def _determine_family(self, text: str, url: str) -> str:
        combined = f"{text} {url}".lower()
        if "thinkpad" in combined:
            return "ThinkPad"
        elif "legion" in combined:
            return "Legion"
        elif "loq" in combined:
            return "LOQ"
        elif "yoga" in combined:
            return "Yoga"
        elif "thinkbook" in combined:
            return "ThinkBook"
        elif "ideapad" in combined:
            return "IdeaPad"
        return "Lenovo Laptop"

    def _extract_model_code(self, name: str, url: str) -> str | None:
        """Extract primary model identifier from product name or URL slug."""
        # e.g., LOQ 16IRH8 -> 16IRH8; ThinkPad E16 (16" Intel) -> E16; Legion Pro 5 16IRX9 -> 16IRX9
        # Pattern 1: Lenovo model codes with generation suffix (e.g. 16IRH8, 15IRX9, 14IAH7)
        match_code = re.search(r"\b(\d{2}[A-Z]{3}\d{1,2})\b", name)
        if match_code:
            return match_code.group(1).upper()

        # Pattern 2: ThinkPad style (e.g. E14, E16, T14, T16, P14s, P16, X1 Carbon, X1 Yoga)
        match_tp = re.search(r"\b([EPTXL]\d{2}[a-z]?|X1\s+(?:Carbon|Yoga|2-in-1))\b", name, re.IGNORECASE)
        if match_tp:
            return match_tp.group(1).strip()

        # Pattern 3: URL slug part
        slug_match = re.search(r"/p/laptops/[^/]+/([^/]+)/", url)
        if slug_match:
            slug = slug_match.group(1)
            parts = slug.split("-")
            for p in reversed(parts):
                if re.match(r"^\d{2}[a-zA-Z]{3}\d{1,2}$", p):
                    return p.upper()
                if re.match(r"^[a-zA-Z]\d{2}[a-zA-Z]?$", p):
                    return p.upper()

        return None

    def get_laptop_summaries(
        self,
        limit: int | None = None,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
    ) -> list[LaptopSummary]:
        """Level 1: Fetch listing cards from Lenovo Egypt catalog via OpenAPI with watermark stopping."""
        pointers: list[str] = []
        if until_model:
            if isinstance(until_model, str):
                pointers = [p.strip() for p in until_model.split(",") if p.strip()]
            elif isinstance(until_model, (list, tuple, set)):
                pointers = [str(p).strip() for p in until_model if str(p).strip()]

        def matches_pointer(name_str: str, model_code: str | None, url_str: str) -> bool:
            if not pointers:
                return False
            name_clean = name_str.strip().lower()
            model_clean = (model_code or "").strip().lower()
            url_clean = url_str.strip().lower()

            for ptr in pointers:
                ptr_clean = ptr.strip().lower()
                if not ptr_clean:
                    continue
                if model_clean and (ptr_clean == model_clean or ptr_clean in model_clean or model_clean in ptr_clean):
                    return True
                if ptr_clean in name_clean or name_clean in ptr_clean:
                    return True
                if ptr_clean in url_clean:
                    return True
            return False

        summaries: list[LaptopSummary] = []
        seen_codes: set[str] = set()
        reached_watermark = False

        watermark_msg = f" (Watermark: {', '.join(pointers)})" if pointers else " (Full catalog)"
        max_pages_display = str(max_pages) if max_pages is not None else "Unlimited (All Pages)"
        print(f"[Lenovo Scraper] Starting Level 1 catalog scan{watermark_msg} up to {max_pages_display} page(s)...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.lenovo.com/eg/en/laptops/subseries-results/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        for page_idx in itertools.count(1):
            if max_pages is not None and page_idx > max_pages:
                break
            if reached_watermark:
                break
            if limit and len(summaries) >= limit:
                break

            print(f"[Lenovo Scraper] Fetching catalog page {page_idx} (max: {max_pages_display}, sorted by newest)...")

            params_dict = {
                "pageFilterId": self.PAGE_FILTER_ID,
                "page": str(page_idx),
                "pageSize": "20",
                "version": "v2",
                "init": True if page_idx == 1 else False,
                "sorts": ["newest"],
            }
            double_encoded = urllib.parse.quote(urllib.parse.quote(json.dumps(params_dict)))
            api_url = f"{self.DLP_API_URL}?pageFilterId={self.PAGE_FILTER_ID}&loyalty=false&params={double_encoded}"

            try:
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"[Lenovo Scraper] [!] Failed to fetch catalog page {page_idx}: {e}")
                break

            data_obj = payload.get("data", {})
            page_count = data_obj.get("pageCount", 1)
            groups = data_obj.get("data", [])

            if not groups:
                print(f"[Lenovo Scraper] No products returned on page {page_idx}. Ending pagination.")
                break

            added_this_page = 0
            for group in groups:
                products = group.get("products", [])
                for p in products:
                    product_code = p.get("productCode") or p.get("id")
                    if not product_code or product_code in seen_codes:
                        continue
                    seen_codes.add(product_code)

                    name = p.get("productName", "").strip()
                    if not name:
                        continue

                    rel_url = p.get("url", "")
                    if rel_url.startswith("http"):
                        full_url = rel_url
                    elif rel_url.startswith("/eg/en"):
                        full_url = f"https://www.lenovo.com{rel_url}"
                    else:
                        rel_clean = rel_url if rel_url.startswith("/") else f"/{rel_url}"
                        full_url = f"https://www.lenovo.com/eg/en{rel_clean}"

                    model_code = self._extract_model_code(name, rel_url)
                    family = self._determine_family(name, rel_url)


                    # Check watermark
                    if matches_pointer(name, model_code, rel_url):
                        print(f"[Lenovo Scraper] [->] Watermark reached at '{name}' ({model_code}). Halting catalog scan.")
                        reached_watermark = True
                        break

                    # Image URL
                    thumb = p.get("media", {}).get("image", {}).get("imageAddress")
                    if thumb and thumb.startswith("//"):
                        thumb = f"https:{thumb}"

                    # Price
                    price_val = p.get("price")
                    price_str = f"{price_val} EGP" if price_val else None

                    # Date estimation
                    prelim_date, prelim_year = LenovoDateExtractor.extract(name, "")

                    summaries.append(
                        LaptopSummary(
                            brand=self.brand_name,
                            name=name,
                            price=price_str,
                            price_egp=float(price_val) if price_val else None,
                            currency="EGP",
                            family=family,
                            model=model_code,
                            product_url=full_url,
                            specs_url=full_url,
                            thumbnail_url=thumb,
                            release_date=prelim_date,
                            release_year=prelim_year,
                        )
                    )
                    added_this_page += 1

                    if limit and len(summaries) >= limit:
                        break

                if reached_watermark or (limit and len(summaries) >= limit):
                    break

            print(f"[Lenovo Scraper] Page {page_idx}: Added {added_this_page} laptops. Total so far: {len(summaries)}.")

            if page_idx >= page_count:
                print(f"[Lenovo Scraper] Reached the final page ({page_count}). Ending catalog pagination.")
                break

        print(f"[Lenovo Scraper] Level 1 complete: Found {len(summaries)} laptop(s).")
        return summaries

    def _fetch_specs_via_api(self, product_number: str) -> list[dict[str, Any]]:
        """Fetch specification tables directly from Lenovo's Tech Specs API endpoint."""
        url = f"{self.TECH_SPECS_API_URL}?productNumber={product_number}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.lenovo.com/eg/en/laptops/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("data", {}).get("tables", [])
        except Exception as e:
            print(f"[Lenovo Scraper] Tech Specs API fetch failed for {product_number}: {e}")
            return []

    def _extract_tables_from_html(self, html_content: str) -> list[dict[str, Any]]:
        """Extract techSpecs tables from embedded page script using robust JSON decoding."""
        decoder = json.JSONDecoder()
        for m in re.finditer(r'window\["techSpecs_[^"]+"\]\s*=\s*({)', html_content):
            try:
                start = m.start(1)
                data, _ = decoder.raw_decode(html_content[start:])
                api_data = data.get("data", {}).get("requestApiData", [])
                if api_data:
                    tables = api_data[0].get("data", {}).get("data", {}).get("tables", [])
                    if tables:
                        return tables
            except Exception:
                continue

        # Fallback to regex
        pattern = r'window\["techSpecs_[^"]+"\]\s*=\s*({.*?});\s*(?:flash_fe_core_tool|</script>)'
        for m in re.finditer(pattern, html_content, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                api_data = data.get("data", {}).get("requestApiData", [])
                if api_data:
                    tables = api_data[0].get("data", {}).get("data", {}).get("tables", [])
                    if tables:
                        return tables
            except Exception:
                continue
        return []

    def get_laptop_detail(self, summary: LaptopSummary) -> LaptopDetail | None:
        """Level 2: Deep crawl extracting all hardware specifications, chassis attributes, and configurations."""
        target_url = summary.product_url
        print(f"[Lenovo Scraper] Level 2 Crawl: Fetching full specs for '{summary.name}' from {target_url}...")

        # 1. Fetch PDP HTML using scraper engine
        doc = self.engine.fetch(target_url, stealth=True, network_idle=True, disable_resources=True)
        raw_html = doc.html

        # Extract product number / product code from URL or HTML
        product_number = ""
        m_pn = re.search(r'<meta\s+name=["\'](?:productid|subseriesPHcode)["\']\s+content=["\'](.*?)["\']', raw_html, re.IGNORECASE)
        if m_pn:
            product_number = m_pn.group(1).upper()

        if not product_number:
            last_segment = target_url.split("?")[0].strip("/").split("/")[-1]
            if re.match(r"^[a-zA-Z0-9]{8,15}$", last_segment):
                product_number = last_segment.upper()

        # 2. Extract structured specification tables
        tables = self._extract_tables_from_html(raw_html)
        if not tables and product_number:
            print(f"[Lenovo Scraper] Embedded specs not found in HTML, calling official Tech Specs API for {product_number}...")
            tables = self._fetch_specs_via_api(product_number)


        all_specs: dict[str, str] = {}
        spec_sections: dict[str, dict[str, str]] = {}

        for table in tables:
            group_name = table.get("groupHeadline") or "General"
            group_dict: dict[str, str] = {}
            for item in table.get("specs", []):
                headline = item.get("headline", "").strip()
                raw_text = item.get("text", "")
                clean_text = clean_html_text(raw_text)
                if headline and clean_text:
                    group_dict[headline] = clean_text
                    all_specs[headline] = clean_text
            if group_dict:
                spec_sections[group_name] = group_dict

        # 3. Fallback to Meta tags if spec tables were completely absent
        if not all_specs:
            meta_map = {
                "Processor": "Processor",
                "Graphics": "graphics",
                "Memory": "memory",
                "Storage": "hard_drive",
                "Display": "display_type",
                "Operating System": "operating_system",
            }
            for headline, meta_name in meta_map.items():
                m = re.search(rf'<meta\s+name=["\']{meta_name}["\']\s+content=["\'](.*?)["\']', raw_html, re.IGNORECASE)
                if m and m.group(1).strip():
                    val = clean_html_text(m.group(1))
                    all_specs[headline] = val

        core_keys = {"processor", "graphics", "memory", "storage", "display", "operating system"}
        has_core = any(k.lower() in core_keys for k in all_specs.keys())
        if not has_core:
            print(f"[Lenovo Scraper] [!] '{summary.name}' has no hardware specs (Placeholder/Unreleased). Skipping.")
            return None

        # 4. Map into Standardized Hardware Fields
        def _get_spec(*candidates: str) -> str | None:
            for c in candidates:
                c_lower = c.strip().lower()
                for k, v in all_specs.items():
                    k_lower = k.strip().lower()
                    if k_lower == c_lower or c_lower in k_lower:
                        if v and v.strip():
                            return v.strip()
            return None

        structured_specs: dict[str, str | None] = {
            "processor": _get_spec("Processor", "CPU"),
            "operating_system": _get_spec("Operating System", "OS"),
            "graphics": _get_spec("Graphics", "GPU", "Video Card"),
            "display": _get_spec("Display", "Screen"),
            "memory": _get_spec("Memory", "RAM"),
            "storage": _get_spec("Storage", "Hard Drive", "SSD"),
            "battery": _get_spec("Battery"),
            "audio": _get_spec("Audio", "Speakers", "Sound"),
            "camera": _get_spec("Camera", "Webcam"),
            "io_ports": _get_spec("Ports/Slots", "Ports", "I/O Ports"),
            "network_communication": _get_spec("Wireless", "WiFi", "Network and Communication"),
            "dimensions": _get_spec("Dimensions (H x W x D)", "Dimensions (W x D x H)", "Dimensions"),
            "weight": _get_spec("Weight"),
            "keyboard_touchpad": _get_spec("Keyboard", "Keyboard & Touchpad"),
            "color": _get_spec("Colors", "Color"),
            "security": _get_spec("Security"),
            "included_in_box": _get_spec("What’s in the Box", "What's in the Box", "Package Contents"),
            "power_supply": _get_spec("Power Supply", "Adapter"),
        }

        # 5. Extract distinct chassis colors
        colors: list[str] = []
        raw_colors = structured_specs.get("color")
        if raw_colors:
            for c_part in re.split(r"[\n,;/•]+", raw_colors):
                c_clean = c_part.strip()
                if c_clean and len(c_clean) >= 3 and c_clean not in colors:
                    colors.append(c_clean)

        # 6. Extract high-res gallery images
        gallery_images: list[str] = []
        if summary.thumbnail_url:
            gallery_images.append(summary.thumbnail_url)

        img_matches = re.findall(r'["\'](//[a-z0-9.-]+\.static\.pub/[^"\']+\.(?:png|jpg|jpeg|webp))["\']', raw_html, re.I)
        for img in img_matches:
            full_img = f"https:{img}"
            if full_img not in gallery_images:
                gallery_images.append(full_img)

        # 7. Date & Generation Extraction
        all_specs_str = " ".join(all_specs.values())
        release_date, release_year = LenovoDateExtractor.extract(summary.name, all_specs_str)
        if not release_date:
            release_date = summary.release_date
        if not release_year:
            release_year = summary.release_year

        # 8. Model Variants & SKUs
        model_variants: list[str] = []
        if product_number and product_number not in model_variants:
            model_variants.append(product_number)
        if summary.model and summary.model not in model_variants:
            model_variants.append(summary.model)

        # Look for genuine MTM (Machine Type Model e.g. 82XW000NED, 21K9000AED)
        # Must be 10 chars, start with digit, end with 2-letter country code, and contain letters
        mtm_matches = re.findall(r"\b([0-9][0-9A-Za-z]{3}[0-9]{4}[A-Za-z]{2})\b", raw_html)
        for mtm in mtm_matches:
            mtm_up = mtm.upper()
            if not mtm_up.isdigit() and any(c.isalpha() for c in mtm_up) and mtm_up not in model_variants:
                model_variants.append(mtm_up)

        # Base model extraction (e.g. Yoga Pro 7i, LOQ 16, ThinkPad E16)
        clean_base = re.sub(r"\bLenovo\b", "", summary.name, flags=re.I)
        clean_base = re.sub(r"\bGen\s+\d+\b", "", clean_base, flags=re.I)
        clean_base = re.sub(r"\bAura\s+Edition\b", "", clean_base, flags=re.I)
        clean_base = re.sub(r"\b\d{1,2}(?:\.\d)?\s*(?:inch|″|\"|')\b", "", clean_base, flags=re.I)
        clean_base = re.sub(r"\b(?:Intel|AMD)\b", "", clean_base, flags=re.I)
        clean_base = re.sub(r"\([^)]*\)", "", clean_base)
        clean_base = re.sub(r"\s+", " ", clean_base).strip()

        base_model = clean_base or summary.family or "Lenovo Laptop"
        best_model = summary.model or product_number or "UNKNOWN"


        detail = LaptopDetail(
            brand=self.brand_name,
            name=summary.name,
            price=summary.price,
            price_egp=summary.price_egp,
            currency="EGP",
            family=summary.family,
            model=best_model,
            base_model=base_model,
            model_variants=model_variants,
            sku_part_number=product_number,
            product_url=summary.product_url,
            specs_url=summary.product_url,
            thumbnail_url=summary.thumbnail_url,
            gallery_images=gallery_images[:10],
            colors=colors,
            release_date=release_date,
            release_year=release_year,
            structured_specs=structured_specs,
            all_specs=all_specs,
            spec_sections=spec_sections,
            raw_markdown=doc.markdown()[:5000],
            extra_metadata={"product_number": product_number, "tables_count": len(tables)},
        )

        detail.configurations = self.extract_configurations(detail)
        return detail

    def extract_configurations(self, detail: LaptopDetail) -> list[ConfigurationItem]:
        """Expand LaptopDetail into official ConfigurationItems."""
        base_model = detail.base_model or ModelNormalizer.extract_base_model(detail.model)

        configs: list[ConfigurationItem] = []
        seen_models: set[str] = set()

        for variant in detail.model_variants:
            if variant in seen_models:
                continue
            seen_models.add(variant)
            tokens = ModelNormalizer.extract_model_tokens(variant)
            configs.append(
                ConfigurationItem(
                    model=variant,
                    model_series=tokens.get("sub_model") or detail.model,
                    base_model=base_model or tokens.get("base_model"),
                    mpn=variant if len(variant) >= 10 else detail.sku_part_number,
                    official_specs=detail.all_specs,
                    stores=[],
                )
            )

        if not configs:
            effective = detail.model or base_model or "UNKNOWN"
            tokens = ModelNormalizer.extract_model_tokens(effective)
            configs.append(
                ConfigurationItem(
                    model=effective,
                    model_series=tokens.get("sub_model") or effective,
                    base_model=base_model or tokens.get("base_model"),
                    mpn=detail.sku_part_number,
                    official_specs=detail.all_specs,
                    stores=[],
                )
            )

        return configs
