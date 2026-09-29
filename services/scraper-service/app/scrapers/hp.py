import html
import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

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


def clean_spec_text(raw_text: str | None) -> str:
    """Clean spec string by stripping footnote markers, non-breaking spaces, and excess whitespace."""
    if not raw_text:
        return ""
    text = raw_text
    # Remove footnote markers like (*), *, [1], etc.
    text = re.sub(r"\(\s*\*\s*\)", "", text)
    text = re.sub(r"\s+\*+", "", text)
    text = text.replace("\xa0", " ")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class HpDateExtractor:
    """Infers release date and generation year for HP laptops based on hardware architecture and sub-brand conventions."""

    HARDWARE_YEAR_MAP = [
        # NVIDIA GeForce RTX 50-series (Blackwell) - 2025
        (re.compile(r"\b(?:RTX\s*5090|RTX\s*5080|RTX\s*5070\s*Ti|RTX\s*5070|RTX\s*5060|RTX\s*5050)\b", re.I), 2025, "2025-01-01"),
        # Intel Core Ultra Series 2 (Lunar Lake / Arrow Lake) - Late 2024 / 2025
        (re.compile(r"\b(?:Ultra\s+[579]\s+2\d{2}[A-Za-z]?|288V|268V|258V|256V|228V|226V|Lunar\s+Lake)\b", re.I), 2024, "2024-09-01"),
        # AMD Strix Point (Ryzen AI 300) - Mid 2024 / 2025
        (re.compile(r"\b(?:Ryzen\s+AI\s+9|HX\s+375|HX\s+370|AI\s+9\s+365|Strix\s+Point)\b", re.I), 2024, "2024-07-01"),
        # Qualcomm Snapdragon X Elite / Plus - Mid 2024
        (re.compile(r"\b(?:Snapdragon\s+X\s+Elite|Snapdragon\s+X\s+Plus|Snapdragon\s+X)\b", re.I), 2024, "2024-06-01"),
        # Intel Core Ultra Series 1 (Meteor Lake) - Early 2024
        (re.compile(r"\b(?:Ultra\s+[579]\s+1\d{2}[A-Za-z]?|185H|165H|155H|135H|125H|Meteor\s+Lake)\b", re.I), 2024, "2024-01-01"),
        # AMD Hawk Point (Ryzen 8000) - Early 2024
        (re.compile(r"\b(?:Ryzen\s+[579]\s+8\d{3}|8945HS|8845HS|8645HS|Hawk\s+Point)\b", re.I), 2024, "2024-01-01"),
        # Intel 14th Gen HX / Refresh - 2024
        (re.compile(r"\b(?:14900HX|14700HX|14650HX|14th\s+Gen)\b", re.I), 2024, "2024-01-01"),
        # Intel 13th Gen (Raptor Lake) - 2023
        (re.compile(r"\b(?:13900H|13700H|13500H|1335U|1315U|13th\s+Gen|Raptor\s+Lake)\b", re.I), 2023, "2023-01-01"),
        # AMD Phoenix (Ryzen 7000) - 2023
        (re.compile(r"\b(?:Ryzen\s+[579]\s+7\d{3}|7940HS|7840HS|7735HS|7535HS)\b", re.I), 2023, "2023-01-01"),
        # Intel 12th Gen (Alder Lake) - 2022
        (re.compile(r"\b(?:12900H|12700H|12500H|1235U|1215U|12th\s+Gen|Alder\s+Lake)\b", re.I), 2022, "2022-01-01"),
    ]

    MODEL_GEN_MAP = [
        # HP OmniBook series (HP's 2024/2025 AI PC brand relaunch)
        (re.compile(r"\bOmniBook\b", re.I), 2024, "2024-06-01"),
        # EliteBook G1i / G2i (Intel AI Core Ultra generations)
        (re.compile(r"\bEliteBook.*?\bG2i\b", re.I), 2025, "2025-01-01"),
        (re.compile(r"\bEliteBook.*?\bG1i\b", re.I), 2024, "2024-09-01"),
        (re.compile(r"\bEliteBook.*?\bG10\b", re.I), 2023, "2023-04-01"),
        (re.compile(r"\bEliteBook.*?\bG9\b", re.I), 2022, "2022-04-01"),
        # ProBook G11 / G10 / G9
        (re.compile(r"\bProBook.*?\bG11\b", re.I), 2024, "2024-04-01"),
        (re.compile(r"\bProBook.*?\bG10\b", re.I), 2023, "2023-04-01"),
        (re.compile(r"\bProBook.*?\bG9\b", re.I), 2022, "2022-04-01"),
    ]

    @classmethod
    def extract(cls, name: str, specs_text: str = "") -> tuple[str | None, int | None]:
        combined = f"{name} {specs_text}".lower()

        # 1. Hardware processor / GPU regex (highest precision)
        for pattern, yr, dt in cls.HARDWARE_YEAR_MAP:
            if pattern.search(specs_text) or pattern.search(name):
                return dt, yr

        # 2. HP model generation patterns
        for pattern, yr, dt in cls.MODEL_GEN_MAP:
            if pattern.search(name):
                return dt, yr

        return None, None


class HpBrandScraper(BaseBrandScraper):
    """Official brand scraper for HP Middle East catalog with deep Level 2 specification extraction."""

    PAGE_SIZE = 48
    CATALOG_BASE_URL = "https://www.hp.com/emea_middle_east-en/products/laptops/view-all-laptops-and-2-in-1s.html?is_channeladvisor=yes"
    SEARCH_API_TEMPLATE = (
        "https://www.hp.com/emea_middle_east-en/products/laptops/view-all-laptops-and-2-in-1s/"
        "jcr:content/root/search-wrapper/plp_grid.search-results.start.{start}.end.{end}.search.noValue.noFilters.html"
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
    def brand_name(self) -> str:
        return "HP"

    @property
    def catalog_url(self) -> str:
        return self.CATALOG_BASE_URL

    def _determine_family(self, text: str, url: str) -> str:
        combined = f"{text} {url}".lower()
        if "omnibook" in combined:
            return "OmniBook"
        elif "omen max" in combined or "omen" in combined or "hyperx" in combined:
            return "OMEN"
        elif "victus" in combined:
            return "Victus"
        elif "elitebook" in combined:
            return "EliteBook"
        elif "probook" in combined:
            return "ProBook"
        elif "spectre" in combined:
            return "Spectre"
        elif "envy" in combined:
            return "Envy"
        elif "pavilion" in combined:
            return "Pavilion"
        elif "dragonfly" in combined:
            return "Dragonfly"
        elif "zbook" in combined:
            return "ZBook"
        elif "essential" in combined or "hp laptop" in combined:
            return "HP Essential"
        return "HP Laptop"

    def _extract_model(self, title: str, sku: str | None) -> str:
        """Extract a canonical model identifier from commercial title and SKU."""
        clean_title = ModelNormalizer.clean_noisy_title(title)
        clean_title = clean_spec_text(clean_title)
        if sku:
            return f"{clean_title} ({sku})" if sku not in clean_title else clean_title

        # Search for SKU in parentheses at the end, e.g. "HP Laptop 15-fd0279ne (C8BS4EA)"
        m = re.search(r"\(([A-Z0-9]{5,10})\)", title)
        if m:
            found_sku = m.group(1)
            return f"{clean_title} ({found_sku})" if found_sku not in clean_title else clean_title

        return clean_title

    def _matches_watermark(self, identifier: str, until_model: str | list[str] | None) -> bool:
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

    def get_laptop_summaries(
        self,
        limit: int | None = None,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
    ) -> list[LaptopSummary]:
        """Level 1: Crawl the HP Middle East catalog search endpoint and extract summaries.

        Supports watermark stopping via `until_model` and page limit ceilings.
        """
        summaries: list[LaptopSummary] = []
        page = 0
        watermark_hit = False

        max_pages_display = str(max_pages) if max_pages is not None else "Unlimited (All Pages)"
        print(f"[HP Scraper] Starting Level 1 catalog crawl (max_pages={max_pages_display}, limit={limit or 'All'})")

        while (max_pages is None or page < max_pages) and not watermark_hit:
            start = page * self.PAGE_SIZE
            end = start + self.PAGE_SIZE - 1
            url = self.SEARCH_API_TEMPLATE.format(start=start, end=end)

            try:
                r = self._session.get(url, headers=self._headers, impersonate="chrome120", timeout=25.0)
            except Exception as e:
                print(f"[HP Scraper] Error fetching catalog page {page} [{start}-{end}]: {e}")
                break

            if r.status_code != 200:
                print(f"[HP Scraper] Catalog page {page} returned status {r.status_code}. Stopping.")
                break

            soup = BeautifulSoup(r.text, "html.parser")
            api_products = soup.find("api-products")
            is_last = (api_products.get("data-is-last") == "true") if api_products else False
            tiles = soup.find_all("script", type="text/product-tile")

            if not tiles:
                print(f"[HP Scraper] No product tiles found on page {page}. Stopping.")
                break

            for tile in tiles:
                tile_soup = BeautifulSoup(tile.string or "", "html.parser")
                prod_elem = tile_soup.find("hppc-product-tile")
                pid = prod_elem.get("data-product-id") if prod_elem else None
                sku = prod_elem.get("data-sku") if prod_elem else None

                link_elem = tile_soup.find("a", href=True)
                if not link_elem:
                    continue

                raw_title = link_elem.get("data-gtm-value") or link_elem.get_text(strip=True)
                href = link_elem.get("href", "")
                product_url = urljoin("https://www.hp.com", href)
                specs_url = f"https://www.hp.com/emea_middle_east-en/products/laptops/product-details/product-specifications/{pid}" if pid else None

                # Extract thumbnail and date from tile ImageObject if available
                thumbnail_url = None
                date_published = None
                for s in tile_soup.find_all("script", type="application/ld+json"):
                    try:
                        ld_data = json.loads(s.string)
                        if ld_data.get("@type") == "ImageObject":
                            thumbnail_url = ld_data.get("contentUrl")
                            date_published = ld_data.get("datePublished")
                            break
                    except Exception:
                        pass

                family = self._determine_family(raw_title, product_url)
                model_name = self._extract_model(raw_title, sku)

                # Watermark check
                identifiers = [raw_title, model_name, sku, pid, href]
                if any(self._matches_watermark(ident, until_model) for ident in identifiers if ident):
                    print(f"[HP Scraper] Watermark matched '{until_model}' at laptop '{raw_title}'. Halting Level 1 crawl.")
                    watermark_hit = True
                    break

                summary = LaptopSummary(
                    brand="HP",
                    name=raw_title,
                    price=None,
                    price_egp=None,
                    currency="USD",
                    family=family,
                    model=model_name,
                    product_url=product_url,
                    specs_url=specs_url,
                    store_url=product_url,
                    thumbnail_url=thumbnail_url,
                    release_date=date_published,
                    release_year=int(date_published.split("-")[0]) if (date_published and date_published.count("-") >= 1) else None,
                )
                summaries.append(summary)

                if limit and len(summaries) >= limit:
                    break

            print(f"[HP Scraper] Page {page} [{start}-{end}]: Processed {len(tiles)} tiles (Total accumulated: {len(summaries)})")

            if is_last or watermark_hit or (limit and len(summaries) >= limit):
                break

            page += 1

        print(f"[HP Scraper] Level 1 crawl finished. Extracted {len(summaries)} laptop summaries.")
        return summaries

    def _fetch_page(self, url: str) -> str:
        """Fetch page HTML using ScraplingEngine or curl_cffi Session."""
        if self.engine:
            try:
                doc = self.engine.fetch(url)
                if doc and doc.html and len(doc.html) > 500:
                    return doc.html
            except Exception:
                pass
        # Fallback to direct curl_cffi session
        r = self._session.get(url, headers=self._headers, impersonate="chrome120", timeout=25.0)
        return r.text if r.status_code == 200 else ""

    def get_laptop_detail(self, summary: LaptopSummary) -> LaptopDetail | None:
        """Level 2: Fetch deep specifications from PDP and technical specifications page."""
        all_specs: dict[str, str] = {}
        spec_sections: dict[str, dict[str, str]] = {}
        gallery_images: list[str] = []
        release_date = summary.release_date
        release_year = summary.release_year
        tagline = ""
        sku_part_number = None

        # ---------------------------------------------------------------------
        # 1. Fetch Product Detail Page (PDP) for JSON-LD & Gallery Assets
        # ---------------------------------------------------------------------
        pdp_html = self._fetch_page(summary.product_url)
        if pdp_html:
            pdp_soup = BeautifulSoup(pdp_html, "html.parser")

            # Parse Product JSON-LD
            for s in pdp_soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(s.string)
                    if data.get("@type") == "Product":
                        sku_part_number = data.get("sku") or sku_part_number
                        pdp_date = data.get("releaseDate")
                        if pdp_date:
                            release_date = pdp_date
                            try:
                                release_year = int(pdp_date.split("-")[0])
                            except Exception:
                                pass
                        imgs = data.get("image", [])
                        if isinstance(imgs, list):
                            gallery_images.extend([img for img in imgs if isinstance(img, str)])
                        elif isinstance(imgs, str):
                            gallery_images.append(imgs)
                        tagline = clean_spec_text(data.get("description", ""))
                        break
                except Exception:
                    pass

            # Fallback: extract short specs from PDP if available
            short_specs_el = pdp_soup.find(class_=re.compile(r"c-product-details__short-specs"))
            if short_specs_el:
                all_specs["Overview Specs"] = clean_spec_text(short_specs_el.get_text())

            for it in pdp_soup.find_all(class_="c-product-specs__item"):
                txt = clean_spec_text(it.get_text(separator=" ", strip=True))
                if ":" in txt:
                    k, v = txt.split(":", 1)
                    k_clean, v_clean = clean_spec_text(k), clean_spec_text(v)
                    if k_clean and v_clean:
                        all_specs[k_clean] = v_clean

        # ---------------------------------------------------------------------
        # 2. Fetch Full Tech Specs Page
        # ---------------------------------------------------------------------
        specs_url = summary.specs_url
        if not specs_url and summary.product_url:
            m_id = re.search(r"/(\d+)$", summary.product_url)
            if m_id:
                specs_url = (
                    f"https://www.hp.com/emea_middle_east-en/products/laptops/"
                    f"product-details/product-specifications/{m_id.group(1)}"
                )

        if specs_url:
            specs_html = self._fetch_page(specs_url)
            if specs_html:
                specs_soup = BeautifulSoup(specs_html, "html.parser")
                table = specs_soup.find("table", class_="c-product-all-details-table__table")
                if table:
                    for row in table.find_all("tr"):
                        cells = row.find_all(["td", "th"])
                        if len(cells) == 2:
                            k = clean_spec_text(cells[0].get_text())
                            v = clean_spec_text(cells[1].get_text())
                            if k and v:
                                all_specs[k] = v

        if not all_specs:
            print(f"[HP Scraper] Could not fetch specs for '{summary.name}'.")
            self.record_skipped(
                name=summary.name,
                url=specs_url or summary.product_url,
                reason="Could not fetch specs from PDP or specs page",
                stage="level2_specs",
            )
            return None

        # ---------------------------------------------------------------------
        # 3. Categorize into Spec Sections
        # ---------------------------------------------------------------------
        section_mapping = {
            "Processor & Chipset": ["processor", "processor family", "chipset"],
            "Graphics & Display": [
                "graphics", "display", "touchscreen", "screen-to-body ratio",
                "color gamut", "brightness", "flicker-free"
            ],
            "Memory & Storage": ["memory", "internal storage", "storage capacity", "memory size", "expansion slots"],
            "Design & Dimensions": ["product color", "dimensions (w x d x h)", "weight", "sustainability specifications"],
            "Battery & Power": ["battery type", "battery recharge time", "power supply type"],
            "Connectivity & Ports": ["wireless", "network interface", "ports"],
            "Peripherals & Media": ["keyboard", "camera", "audio", "pointing device", "input devices"],
            "Security & Software": [
                "security management", "software included",
                "software - productivity & finance", "cloud service", "manufacturer warranty"
            ],
        }

        for sec_name, sec_keys in section_mapping.items():
            sec_dict: dict[str, str] = {}
            for k, v in all_specs.items():
                k_lower = k.lower()
                if any(sk in k_lower for sk in sec_keys):
                    sec_dict[k] = v
            if sec_dict:
                spec_sections[sec_name] = sec_dict

        # ---------------------------------------------------------------------
        # 4. Extract Canonical Structured Hardware Fields
        # ---------------------------------------------------------------------
        def _get_spec_val(keys: list[str]) -> str | None:
            for k, v in all_specs.items():
                k_lower = k.lower()
                if any(target in k_lower for target in keys):
                    return v
            return None

        processor = _get_spec_val(["processor", "cpu"])
        graphics = _get_spec_val(["graphics", "gpu"])
        memory = _get_spec_val(["memory", "memory size", "ram"])
        storage = _get_spec_val(["internal storage", "storage capacity", "ssd"])
        display = _get_spec_val(["display", "screen"])
        weight = _get_spec_val(["weight"])
        battery = _get_spec_val(["battery type", "battery"])
        ports = _get_spec_val(["ports"])
        os_spec = _get_spec_val(["operating system", "os"])
        wireless = _get_spec_val(["wireless", "wi-fi"])
        camera = _get_spec_val(["camera", "webcam"])
        audio = _get_spec_val(["audio", "sound"])
        colors = all_specs.get("Product color") or all_specs.get("Color")
        if not colors:
            for k, v in all_specs.items():
                if "product color" in k.lower() and "gamut" not in k.lower():
                    colors = v
                    break

        dimensions = _get_spec_val(["dimensions"])

        # Display sub-attributes
        display_size = None
        resolution = None
        refresh_rate = None
        panel_type = None
        brightness = _get_spec_val(["brightness"])

        if display:
            # Prioritize inches (e.g. 14", 16", 13.3", 15.6")
            m_inch = re.search(r'(\d+(?:\.\d+)?)\s*(?:\"|\s*inch)', display, re.I)
            if m_inch:
                display_size = f'{m_inch.group(1)}"'
            else:
                m_cm = re.search(r'(\d+(?:\.\d+)?)\s*cm', display, re.I)
                if m_cm:
                    cm_val = float(m_cm.group(1))
                    inch_val = round(cm_val / 2.54, 1)
                    display_size = f'{int(inch_val) if inch_val.is_integer() else inch_val}"'

            m_dim = re.search(r'(\d{3,4}\s*x\s*\d{3,4})', display)
            m_std = re.search(r'\b(WQXGA|WUXGA|FHD\+?|QHD\+?|UHD|4K|2\.8K|3K)\b', display, re.I)
            if m_dim and m_std:
                resolution = f"{m_std.group(1).upper()} ({m_dim.group(1).replace(' ', '')})"
            elif m_dim:
                resolution = m_dim.group(1).replace(' ', '')
            elif m_std:
                resolution = m_std.group(1).upper()

            m_hz = re.search(r'(\d{2,3}(?:-\d{2,3})?\s*Hz)', display, re.I)
            if m_hz:
                refresh_rate = m_hz.group(1).strip()

            if "oled" in display.lower():
                panel_type = "OLED"
            elif "ips" in display.lower():
                panel_type = "IPS"

        structured_specs: dict[str, str | None] = {
            "processor": processor,
            "gpu": graphics,
            "ram": memory,
            "storage": storage,
            "display_size": display_size,
            "resolution": resolution,
            "refresh_rate": refresh_rate,
            "panel_type": panel_type,
            "brightness": brightness,
            "weight": weight,
            "dimensions": dimensions,
            "battery": battery,
            "ports": ports,
            "os": os_spec,
            "wireless": wireless,
            "camera": camera,
            "audio": audio,
            "colors": colors,
        }

        # ---------------------------------------------------------------------
        # 5. Date Inference & Verification
        # ---------------------------------------------------------------------
        specs_combined_text = " ".join(all_specs.values())
        if not release_date:
            inferred_date, inferred_year = HpDateExtractor.extract(summary.name, specs_combined_text)
            if inferred_date:
                release_date = inferred_date
                release_year = inferred_year

        # ---------------------------------------------------------------------
        # 6. Build Configurations
        # ---------------------------------------------------------------------
        config_item = ConfigurationItem(
            model=summary.model or summary.name,
            model_series=summary.family or "HP Laptop",
            base_model=summary.model,
            mpn=sku_part_number or summary.model,
            processor=processor,
            ram=memory,
            storage=storage,
            gpu=graphics,
            display=display,
            color=colors,
            official_specs=all_specs,
            stores=[],
        )

        return LaptopDetail(
            brand="HP",
            name=summary.name,
            price=summary.price,
            price_egp=summary.price_egp,
            currency=summary.currency,
            family=summary.family,
            model=summary.model,
            product_url=summary.product_url,
            specs_url=specs_url,
            store_url=summary.store_url,
            thumbnail_url=summary.thumbnail_url or (gallery_images[0] if gallery_images else None),
            release_date=release_date,
            release_year=release_year,
            base_model=summary.model,
            model_variants=[],
            sku_part_number=sku_part_number,
            copyright_year=release_year,
            gallery_images=gallery_images,
            colors=[colors] if colors else [],
            structured_specs=structured_specs,
            all_specs=all_specs,
            spec_sections=spec_sections,
            configurations=[config_item],
            raw_markdown=tagline,
            extra_metadata={
                "tagline": tagline,
                "specs_table_rows_count": len(all_specs),
            },
        )
