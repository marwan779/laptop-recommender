import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from app.engine.base import IScraperEngine, ScrapedDocument
from app.matching.normalizer import ModelNormalizer
from app.schemas.laptop import ConfigurationItem, LaptopDetail, LaptopSummary
from app.scrapers.base import BaseBrandScraper

KNOWN_HEADERS = [
    "Model", "Color", "Operating System", "Platform", "Processor", "Graphics",
    "Display", "Memory", "Storage", "Expansion Slots (includes used)", "Expansion Slots",
    "I/O Ports", "Keyboard & Touchpad", "Keyboard", "Touchpad", "Camera", "Audio",
    "Network and Communication", "Battery", "Power Supply", "Weight",
    "Dimensions (W x D x H)", "Built-in Apps", "MyASUS Features", "Microsoft Office",
    "Military Grade", "Eco Labels & Compliances", "Ecolabels & Compliances", "Security",
    "Included in the Box", "Regulatory Compliance"
]


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
        # Single year e.g. '2024'
        if re.match(r"^\d{4}$", val_str):
            return datetime(int(val_str), 1, 1)
        # ISO timestamp
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


def is_in_date_range(
    release_date: str | None,
    release_year: int | None,
    start_dt: datetime | None,
    end_dt: datetime | None,
) -> bool:
    """Check if laptop release date/year falls within [start_dt, end_dt]."""
    if start_dt is None and end_dt is None:
        return True

    # 1. Exact or ISO release date
    if release_date:
        try:
            dt = datetime.fromisoformat(release_date.split("T")[0])
            if start_dt and dt < start_dt:
                return False
            if end_dt and dt > end_dt:
                return False
            return True
        except Exception:
            pass

    # 2. Year check
    if release_year:
        if start_dt and release_year < start_dt.year:
            return False
        if end_dt and release_year > end_dt.year:
            return False
        return True

    # Default to True if completely unspecified
    return True


def parse_price_egp(price_text: str | None) -> float | None:
    """Extract numeric EGP price float from text."""
    if not price_text:
        return None
    arabic_to_eng = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    clean = price_text.translate(arabic_to_eng)
    match = re.search(r"([\d,]+(?:\.\d{2})?)", clean)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


class AsusDateExtractor:
    """Extracts and infers release date and generation year for ASUS laptops."""

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
        # Intel 14th Gen HX - 2024
        (re.compile(r"\b(?:14900HX|14700HX|14650HX|14th\s+Gen)\b", re.I), 2024, "2024-01-01"),
        # Intel 13th Gen (Raptor Lake) - 2023
        (re.compile(r"\b(?:13980HX|13900H|13700H|13500H|1335U|13th\s+Gen|Raptor\s+Lake)\b", re.I), 2023, "2023-01-01"),
        # AMD Phoenix (Ryzen 7000) - 2023
        (re.compile(r"\b(?:Ryzen\s+[579]\s+7\d{3}|7940HS|7840HS|7735HS|7535HS)\b", re.I), 2023, "2023-01-01"),
        # Intel 12th Gen (Alder Lake) - 2022
        (re.compile(r"\b(?:12900H|12700H|12500H|12th\s+Gen|Alder\s+Lake)\b", re.I), 2022, "2022-01-01"),
        # AMD Rembrandt (Ryzen 6000) - 2022
        (re.compile(r"\b(?:Ryzen\s+[579]\s+6\d{3}|6900HX|6800H|Rembrandt)\b", re.I), 2022, "2022-01-01"),
        # Intel 11th Gen (Tiger Lake) - 2021
        (re.compile(r"\b(?:11900H|11800H|11370H|11th\s+Gen|Tiger\s+Lake)\b", re.I), 2021, "2021-01-01"),
        # AMD Cezanne (Ryzen 5000) - 2021
        (re.compile(r"\b(?:Ryzen\s+[579]\s+5\d{3}|5900HX|5800H|Cezanne)\b", re.I), 2021, "2021-01-01"),
    ]

    MODEL_YEAR_MAP = [
        (re.compile(r"\b(?:S3407|S5452|S5652|H7607|H7407|UX3405|FA507N|GA403|GU605|G614J)\b", re.I), 2024),
        (re.compile(r"\b(?:UX3404|FA507X|G614|GU604|GA402X|S5504)\b", re.I), 2023),
        (re.compile(r"\b(?:UX3402|FA507R|G533Z|GA402R|S5402)\b", re.I), 2022),
    ]

    @classmethod
    def extract_from_doc(
        cls,
        doc: ScrapedDocument,
        text_corpus: str = "",
        all_specs: dict[str, str] | None = None,
    ) -> tuple[str | None, int | None, int | None]:
        """Extract (release_date, release_year, copyright_year)."""
        release_date = None
        release_year = None
        copyright_year = None

        # 1. HTML Meta tags
        for prop in ("article:published_time", "og:updated_time", "release_date", "date", "pubdate"):
            val = doc.get_meta(prop)
            if val:
                match = re.search(r"(\d{4}-\d{2}-\d{2})", val)
                if match:
                    release_date = match.group(1)
                    release_year = int(release_date.split("-")[0])
                    break

        # 2. JSON-LD scripts
        if not release_date:
            json_lds = doc.get_json_ld()
            for item in json_lds:
                for key in ("datePublished", "dateModified", "releaseDate"):
                    val = item.get(key)
                    if isinstance(val, str):
                        match = re.search(r"(\d{4}-\d{2}-\d{2})", val)
                        if match:
                            release_date = match.group(1)
                            release_year = int(release_date.split("-")[0])
                            break
                if release_date:
                    break

        # 3. Copyright year from footer
        combined_text = f"{text_corpus} {doc.html or ''}"
        match_copy = re.search(r"(?:©|copyright)\s*(?:20\d{2}\s*[-–]\s*)?(20\d{2})", combined_text, re.I)
        if match_copy:
            copyright_year = int(match_copy.group(1))

        # 4. Hardware processor generation
        spec_text = " ".join((all_specs or {}).values())
        search_target = f"{text_corpus} {spec_text}"

        if not release_year:
            for pattern, yr, approx_date in cls.HARDWARE_YEAR_MAP:
                if pattern.search(search_target):
                    release_year = yr
                    if not release_date:
                        release_date = approx_date
                    break

        # 5. Chassis model code generation
        if not release_year:
            for pattern, yr in cls.MODEL_YEAR_MAP:
                if pattern.search(search_target):
                    release_year = yr
                    if not release_date:
                        release_date = f"{yr}-01-01"
                    break

        # 6. Fallback to copyright year
        if not release_year and copyright_year:
            release_year = copyright_year
            if not release_date:
                release_date = f"{copyright_year}-01-01"

        return release_date, release_year, copyright_year


def extract_structured_specs(all_specs: dict[str, str]) -> dict[str, str | None]:
    """Map all raw specification headers into standardized hardware fields."""
    def _find_field(*candidates: str) -> str | None:
        for c in candidates:
            c_lower = c.strip().lower()
            for k, v in all_specs.items():
                k_clean = k.strip().lower()
                if k_clean == c_lower or c_lower in k_clean:
                    val = v.strip()
                    if val:
                        return val
        return None

    return {
        "processor": _find_field("Processor", "CPU", "Platform"),
        "operating_system": _find_field("Operating System", "OS"),
        "graphics": _find_field("Graphics", "GPU", "Video Card"),
        "display": _find_field("Display", "Screen", "Panel"),
        "memory": _find_field("Memory", "RAM"),
        "storage": _find_field("Storage", "Hard Drive", "SSD"),
        "expansion_slots": _find_field("Expansion Slots (includes used)", "Expansion Slots"),
        "io_ports": _find_field("I/O Ports", "Ports", "Interfaces"),
        "keyboard_touchpad": _find_field("Keyboard & Touchpad", "Keyboard", "Touchpad"),
        "camera": _find_field("Camera", "Webcam"),
        "audio": _find_field("Audio", "Sound", "Speakers"),
        "network_communication": _find_field("Network and Communication", "Wireless", "Network"),
        "battery": _find_field("Battery"),
        "power_supply": _find_field("Power Supply", "Adapter", "Charger"),
        "weight": _find_field("Weight"),
        "dimensions": _find_field("Dimensions (W x D x H)", "Dimensions"),
        "color": _find_field("Color", "Chassis Color"),
        "security": _find_field("Security", "Fingerprint"),
        "military_grade": _find_field("Military Grade"),
        "included_in_box": _find_field("Included in the Box", "Package Contents"),
        "ecolabels": _find_field("Eco Labels & Compliances", "Ecolabels & Compliances", "Eco Labels"),
    }


def extract_colors(color_spec_text: str | None) -> list[str]:
    """Parse distinct chassis colors from color specification string."""
    if not color_spec_text:
        return []
    colors: list[str] = []
    parts = re.split(r"[\n,/]+", color_spec_text)
    for p in parts:
        clean = p.strip()
        if clean and len(clean) >= 3 and clean not in colors:
            colors.append(clean)
    return colors


class AsusBrandScraper(BaseBrandScraper):
    """Brand scraper for ASUS Egypt laptop catalog supporting Level 1 and Level 2 modes."""

    @property
    def brand_name(self) -> str:
        return "ASUS"

    @property
    def catalog_url(self) -> str:
        return "https://www.asus.com/eg-en/store/laptops/"

    def _determine_family(self, text: str, url: str) -> str | None:
        combined = f"{text} {url}".lower()
        if "zenbook" in combined:
            return "Zenbook"
        elif "rog" in combined or "republic of gamers" in combined:
            return "ROG"
        elif "tuf" in combined:
            return "TUF Gaming"
        elif "vivobook" in combined:
            return "Vivobook"
        elif "proart" in combined:
            return "ProArt"
        elif "expertbook" in combined:
            return "ExpertBook"
        elif "chromebook" in combined:
            return "Chromebook"
        return "ASUS Laptop"

    def _extract_model_code(self, name: str, url: str) -> str | None:
        slug_parts = url.strip("/").split("/")[-1].split("-")
        for part in reversed(slug_parts):
            if re.match(r"^[a-zA-Z]{1,3}\d{3,5}[a-zA-Z]{0,3}$", part):
                return part.upper()

        match = re.search(r"\b([A-Z]{1,3}\d{3,5}[A-Z]{0,3})\b", name)
        if match:
            return match.group(1)
        return None

    def get_laptop_summaries(
        self,
        limit: int | None = None,
        until_model: str | list[str] | None = None,
        max_pages: int = 5,
    ) -> list[LaptopSummary]:
        """Level 1: Fetch listing cards from ASUS catalog with watermark-based incremental stopping."""
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
                # Check model code equality/containment (e.g. S5452, S3407)
                if model_clean and (ptr_clean == model_clean or ptr_clean in model_clean or model_clean in ptr_clean):
                    return True
                # Check full name equality/containment (e.g. ASUS Vivobook S14 (S5452))
                if ptr_clean in name_clean or name_clean in ptr_clean:
                    return True
                # Check URL path containment (e.g. vivobook-s-14-s3407)
                if ptr_clean in url_clean:
                    return True
            return False

        summaries: list[LaptopSummary] = []
        seen_urls: set[str] = set()
        reached_watermark = False

        excluded_slugs = {
            "all-products", "all-series", "for-home", "for-work", "for-students",
            "for-gaming", "for-creators", "business", "store", "support",
        }

        watermark_msg = f" (Watermark: {', '.join(pointers)})" if pointers else " (Full catalog)"
        print(f"[ASUS Scraper] Starting Level 1 catalog scan{watermark_msg} up to {max_pages} page(s)...")

        for page_idx in range(1, max_pages + 1):
            if reached_watermark:
                break
            if limit and len(summaries) >= limit:
                break

            target_url = self.catalog_url if page_idx == 1 else f"{self.catalog_url}?page={page_idx}"
            print(f"[ASUS Scraper] Fetching catalog page {page_idx}/{max_pages}: {target_url}...")

            doc = self.engine.fetch(target_url, stealth=True, network_idle=True, disable_resources=True)
            raw_page = doc.raw

            product_cards = []
            if hasattr(raw_page, "css"):
                product_cards = raw_page.css(
                    "div[class*=\"productCardContainer\"], div[class*=\"store_content_product\"], "
                    "div[class*=\"ProductCard\"], div[class*=\"productCard\"], "
                    "div[class*=\"ProductItem\"], div[class*=\"productItem\"], "
                    "div[class*=\"ProductTile\"], article"
                )

            cards_added_this_page = 0

            if product_cards:
                for card in product_cards:
                    link_el = card.css("a[href*=\"/laptops/\"]")
                    if not link_el:
                        continue
                    href = link_el[0].attrib.get("href", "")
                    full_url = urljoin(self.catalog_url, href)

                    clean_path = urlparse(full_url).path.strip("/").split("/")
                    if not clean_path or clean_path[-1] in excluded_slugs or "compare" in full_url:
                        continue

                    if full_url in seen_urls:
                        continue

                    name = ""
                    for heading in card.css("h1, h2, h3, h4, h5, [class*='title'], [class*='Title'], [class*='heading'], [class*='Heading'], [class*='Name']"):
                        h_text = heading.text.strip()
                        if h_text and len(h_text) > 3 and "filter" not in h_text.lower():
                            name = h_text
                            break

                    if not name and hasattr(link_el[0], "text"):
                        name = link_el[0].text.strip()

                    if not name or len(name) < 3:
                        name = clean_path[-1].replace("-", " ").title()

                    family = self._determine_family(name, full_url)
                    model = self._extract_model_code(name, full_url)

                    # Check Watermark Pointer
                    if pointers and matches_pointer(name, model, full_url):
                        print(f"  [+] Reached Watermark pointer matching '{name}' ({model or full_url})! Halting Level 1 scan.")
                        reached_watermark = True
                        break

                    price = None
                    for el in card.css("[class*='price'], [class*='Price'], div, span"):
                        txt = el.text.strip()
                        if "EGP" in txt:
                            price = txt
                            break
                    if not price:
                        price_el = card.css("[class*=\"price\"], [class*=\"Price\"]")
                        if price_el:
                            price = price_el[0].text.strip()

                    price_num = parse_price_egp(price)

                    img_url = None
                    img_el = card.css("img[src]")
                    if img_el:
                        img_url = urljoin(self.catalog_url, img_el[0].attrib.get("src", ""))

                    store_url = None
                    for a in card.css("a[href*='store.asus.com']"):
                        s_href = a.attrib.get("href")
                        if s_href:
                            store_url = s_href
                            break

                    specs_url = full_url.rstrip("/") + "/techspec/"

                    prelim_year = None
                    if model:
                        for pattern, yr in AsusDateExtractor.MODEL_YEAR_MAP:
                            if pattern.search(model):
                                prelim_year = yr
                                break

                    seen_urls.add(full_url)
                    cards_added_this_page += 1
                    summaries.append(
                        LaptopSummary(
                            brand=self.brand_name,
                            name=name,
                            price=price,
                            price_egp=price_num,
                            currency="EGP",
                            family=family,
                            model=model,
                            product_url=full_url,
                            specs_url=specs_url,
                            store_url=store_url,
                            thumbnail_url=img_url,
                            release_year=prelim_year,
                        )
                    )
                    if limit and len(summaries) >= limit:
                        break

            # Fallback if no cards found via CSS classes on page 1
            if not product_cards and page_idx == 1:
                all_links = []
                if hasattr(raw_page, "css"):
                    all_links = raw_page.css("a")
                for link in all_links:
                    href = getattr(link, "attrib", {}).get("href", "")
                    if "/laptops/" in href and not any(f"/{exc}/" in href or href.endswith(f"/{exc}/") or href.endswith(f"/{exc}") for exc in excluded_slugs):
                        full_url = urljoin(self.catalog_url, href)
                        clean_path = urlparse(full_url).path.strip("/").split("/")
                        if len(clean_path) >= 4 and full_url not in seen_urls and "compare" not in full_url:
                            raw_text = getattr(link, "text", "").strip()
                            name = raw_text if len(raw_text) > 4 else clean_path[-1].replace("-", " ").title()
                            family = self._determine_family(name, full_url)
                            model = self._extract_model_code(name, full_url)

                            if pointers and matches_pointer(name, model, full_url):
                                print(f"  [+] Reached Watermark pointer matching '{name}'! Halting Level 1 scan.")
                                reached_watermark = True
                                break

                            seen_urls.add(full_url)
                            cards_added_this_page += 1
                            specs_url = full_url.rstrip("/") + "/techspec/"

                            prelim_year = None
                            if model:
                                for pattern, yr in AsusDateExtractor.MODEL_YEAR_MAP:
                                    if pattern.search(model):
                                        prelim_year = yr
                                        break

                            summaries.append(
                                LaptopSummary(
                                    brand=self.brand_name,
                                    name=name,
                                    price=None,
                                    price_egp=None,
                                    currency="EGP",
                                    family=family,
                                    model=model,
                                    product_url=full_url,
                                    specs_url=specs_url,
                                    release_year=prelim_year,
                                )
                            )
                            if limit and len(summaries) >= limit:
                                break

            # If no new cards were discovered on this page, stop paginating
            if cards_added_this_page == 0:
                print(f"[ASUS Scraper] No additional laptop cards found on page {page_idx}. Ending catalog pagination.")
                break

        print(f"[ASUS Scraper] Level 1 complete: Found {len(summaries)} laptop(s).")
        return summaries

    def _parse_specs_from_markdown(self, markdown_text: str) -> dict[str, str]:
        lines = [l.strip() for l in markdown_text.splitlines() if l.strip()]
        specs: dict[str, str] = {}
        current_header = None
        current_val: list[str] = []

        start_idx = 0
        for idx, l in enumerate(lines):
            if l in KNOWN_HEADERS:
                start_idx = idx
                break

        for l in lines[start_idx:]:
            if (
                l.startswith("Laptops")
                or l.startswith("Shop and Learn")
                or l.startswith("About ASUS")
                or "ASUSTeK" in l
                or "products certified by" in l.lower()
            ):
                break

            if l in KNOWN_HEADERS:
                if current_header and current_val:
                    specs[current_header] = " \n ".join(current_val)
                current_header = l
                current_val = []
            elif current_header:
                if not l.startswith("!["):
                    current_val.append(l)

        if current_header and current_val:
            specs[current_header] = " \n ".join(current_val)

        return specs

    def get_laptop_detail(
        self,
        summary: LaptopSummary,
    ) -> LaptopDetail | None:
        """Level 2: Deep specifications crawl, date extraction, and physical configurations."""
        target_url = summary.specs_url or summary.product_url
        print(f"[ASUS Scraper] Level 2 Crawl: Fetching full specs for '{summary.name}' from {target_url}...")

        doc = self.engine.fetch(target_url, stealth=True, network_idle=True, disable_resources=True)
        raw_markdown = doc.markdown()

        # Check for empty catalog placeholder indicators
        if re.search(r"viewing\s+\d+\s*-\s*0\s+of\s+0", raw_markdown, re.IGNORECASE):
            print(f"[ASUS Scraper] [!] '{summary.name}' has 0 configurations published on ASUS Egypt (Placeholder). Skipping.")
            return None

        all_specs = self._parse_specs_from_markdown(raw_markdown)

        # Fallback to overview page if specs page was empty
        if not all_specs and summary.specs_url and target_url != summary.product_url:
            print(f"[ASUS Scraper] Specs page empty, falling back to overview: {summary.product_url}...")
            doc = self.engine.fetch(summary.product_url, stealth=True, network_idle=True, disable_resources=True)
            raw_markdown = doc.markdown()
            all_specs = self._parse_specs_from_markdown(raw_markdown)

        # Verify essential hardware specs exist
        core_keys = {"processor", "platform", "operating system", "display", "memory", "storage"}
        has_core_spec = any(k.strip().lower() in core_keys for k in all_specs.keys())

        if not has_core_spec:
            print(f"[ASUS Scraper] [!] '{summary.name}' has no core hardware specifications (Placeholder). Skipping.")
            return None

        # 1. Date Extraction (metadata preserved in detail model)
        release_date, release_year, copyright_year = AsusDateExtractor.extract_from_doc(
            doc=doc,
            text_corpus=f"{summary.name} {raw_markdown}",
            all_specs=all_specs,
        )

        # 2. Extract full model codes and sub-model SKU variants
        base_model = summary.model
        found_variants: set[str] = set()

        if "Model" in all_specs:
            model_val = all_specs["Model"]
            for part in re.split(r"[\n,\s/]+", model_val):
                part_clean = part.strip()
                if re.match(r"^[A-Za-z]{1,4}\d{3,5}[A-Za-z0-9-]*$", part_clean) and len(part_clean) >= 4:
                    found_variants.add(part_clean.upper())

        prefix = base_model if base_model else ""
        sku_matches = re.findall(
            r"\b([A-Za-z]{1,4}\d{3,5}[A-Za-z0-9]{1,4}-[A-Za-z0-9]{4,8})\b",
            raw_markdown,
        )
        for m in sku_matches:
            if not prefix or prefix.upper() in m.upper():
                found_variants.add(m.upper())

        sub_matches = re.findall(
            r"\b([A-Za-z]{1,4}\d{3,5}[A-Za-z]{1,4})\b",
            raw_markdown,
        )
        for m in sub_matches:
            if not prefix or prefix.upper() in m.upper():
                found_variants.add(m.upper())

        if base_model:
            found_variants.add(base_model.upper())

        sorted_variants = sorted(list(found_variants), key=len, reverse=True)
        best_model = sorted_variants[0] if sorted_variants else base_model

        # 3. Price & Store link
        price_match = re.search(r"([\d,]+(?:\.\d{2})?\s*EGP)", raw_markdown, re.IGNORECASE)
        extracted_price = price_match.group(1).strip() if price_match else summary.price
        price_num = parse_price_egp(extracted_price) or summary.price_egp

        store_match = re.search(r"https?://(?:[a-zA-Z0-9.-]+\.)?store\.asus\.com/[^\s\)\"]+", raw_markdown)
        store_url = store_match.group(0) if store_match else summary.store_url

        sku_part_number = None
        if store_url:
            sku_match = re.search(r"([0-9a-zA-Z]{6,10}-[0-9a-zA-Z]{5,8})", store_url)
            if sku_match:
                sku_part_number = sku_match.group(1).upper()

        # 4. Structured specifications
        structured_specs = extract_structured_specs(all_specs)

        # 5. Colors
        colors = extract_colors(all_specs.get("Color"))

        # 6. Gallery Images
        gallery_images: list[str] = []
        if hasattr(doc.raw, "css"):
            for img in doc.raw.css("img[src]"):
                src = img.attrib.get("src", "")
                if any(ext in src.lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
                    if not any(ign in src.lower() for ign in ("icon", "logo", "flag", "badge", "svg")):
                        full_img = urljoin(summary.product_url, src)
                        if full_img not in gallery_images:
                            gallery_images.append(full_img)

        spec_sections = {"Specifications": all_specs}
        print(
            f"[ASUS Scraper] Level 2 complete for '{summary.name}': "
            f"Model: {best_model}, Year: {release_year or 'N/A'}, "
            f"Specs: {len(all_specs)} fields, Variants: {len(sorted_variants)}"
        )

        detail = LaptopDetail(
            brand=summary.brand,
            name=summary.name,
            price=extracted_price,
            price_egp=price_num,
            currency="EGP",
            family=summary.family,
            base_model=base_model,
            model=best_model,
            model_variants=sorted_variants,
            sku_part_number=sku_part_number,
            release_date=release_date,
            release_year=release_year,
            copyright_year=copyright_year,
            gallery_images=gallery_images[:10],
            colors=colors,
            structured_specs=structured_specs,
            product_url=summary.product_url,
            specs_url=summary.specs_url,
            store_url=store_url,
            thumbnail_url=summary.thumbnail_url,
            scraped_at=summary.scraped_at,
            all_specs=all_specs,
            spec_sections=spec_sections,
            raw_markdown=raw_markdown,
            extra_metadata={"model_variants": sorted_variants},
        )

        # 7. Extract distinct physical configurations
        detail.configurations = self.extract_configurations(detail)
        return detail

    def extract_configurations(self, detail: LaptopDetail) -> list[ConfigurationItem]:
        """Expand a LaptopDetail into distinct official ConfigurationItems."""
        base_model = detail.base_model or ModelNormalizer.extract_base_model(detail.model)

        full_skus: list[str] = []
        sub_models: list[str] = []
        covered_sub_models: set[str] = set()

        for variant in detail.model_variants:
            tokens = ModelNormalizer.extract_model_tokens(variant)
            if tokens.get("full_sku"):
                sku = tokens["full_sku"]
                if sku not in full_skus:
                    full_skus.append(sku)
                if tokens.get("sub_model"):
                    covered_sub_models.add(tokens["sub_model"].upper())
            elif tokens.get("sub_model"):
                sub = tokens["sub_model"]
                if base_model and sub.upper() != base_model.upper() and sub.upper() not in sub_models:
                    sub_models.append(sub.upper())

        configs: list[ConfigurationItem] = []

        # 1. Full SKUs
        for sku in full_skus:
            tokens = ModelNormalizer.extract_model_tokens(sku)
            sub_series = tokens.get("sub_model")
            configs.append(
                ConfigurationItem(
                    model=sku,
                    model_series=sub_series,
                    base_model=base_model or tokens.get("base_model"),
                    mpn=detail.sku_part_number if len(full_skus) == 1 else None,
                    official_specs=detail.all_specs,
                    stores=[],
                )
            )

        # 2. Uncovered sub-model series
        for sub in sub_models:
            if sub not in covered_sub_models:
                configs.append(
                    ConfigurationItem(
                        model=sub,
                        model_series=sub,
                        base_model=base_model,
                        mpn=detail.sku_part_number if not configs else None,
                        official_specs=detail.all_specs,
                        stores=[],
                    )
                )

        # 3. Fallback
        if not configs:
            effective_model = detail.model or base_model or "UNKNOWN"
            tokens = ModelNormalizer.extract_model_tokens(effective_model)
            configs.append(
                ConfigurationItem(
                    model=effective_model,
                    model_series=tokens.get("sub_model") or effective_model,
                    base_model=base_model or tokens.get("base_model"),
                    mpn=detail.sku_part_number,
                    official_specs=detail.all_specs,
                    stores=[],
                )
            )

        return configs
