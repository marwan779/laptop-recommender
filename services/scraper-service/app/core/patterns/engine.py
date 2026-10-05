import html as html_lib
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from app.core.patterns.models import SpecExtractionResult, StorePatternConfig
from app.core.patterns.registry import PatternRegistry
from app.core.patterns.title_extractor import TitleSpecExtractor


class PatternEngine:
    """Universal pattern-driven extraction engine that processes PDP HTML using registered store profiles.

    Enriches extracted data with spec-source metadata and OCR readiness flags.
    """

    @classmethod
    def extract_specs(
        cls,
        soup: BeautifulSoup,
        title: str,
        store_key: str,
        base_url: str = "",
        price_val: float | None = None,
        price_str: str | None = None,
        config: StorePatternConfig | None = None,
    ) -> SpecExtractionResult:
        """Extract specifications, product stats, raw description, and OCR metadata from PDP HTML."""
        pattern_cfg = config or PatternRegistry.get(store_key)

        dom_specs: dict[str, str] = {}
        raw_desc_parts: list[str] = []
        mpn: str | None = None
        model_code: str | None = None

        # Clean out promotional modals or dialogs that contain unrelated coupons/promo specs
        for modal in soup.select(".modal, .modal__content, [role='dialog'], #modal-promos"):
            modal.decompose()

        # 1. Product Stats & Schema.org JSON-LD Extraction
        if pattern_cfg.stats_selector:
            stats_items = soup.select(pattern_cfg.stats_selector)
            for li in stats_items:
                txt = li.get_text(" ", strip=True)
                if ":" in txt:
                    k, v = txt.split(":", 1)
                    k_clean = k.strip().lower()
                    v_clean = v.strip()
                    if not v_clean:
                        continue
                    if "mpn" in k_clean:
                        mpn = v_clean
                    elif "model" in k_clean:
                        model_code = v_clean
                    elif "upc" in k_clean and not mpn:
                        mpn = v_clean
                    if len(k.strip()) < 35 and len(v_clean) < 100:
                        dom_specs[k.strip()] = v_clean

        # Schema.org JSON-LD Product fallback for MPN/SKU, fallback price, and description
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, dict) and data.get("@type") == "Product":
                    sku_val = data.get("sku") or data.get("mpn")
                    if sku_val and not mpn:
                        mpn = str(sku_val).strip()
                    if not raw_desc_parts and data.get("description"):
                        raw_desc_parts.append(str(data["description"]).strip())
                    if price_val is None:
                        offers = data.get("offers", {})
                        if isinstance(offers, dict) and offers.get("price"):
                            try:
                                price_val = float(str(offers["price"]))
                                price_str = f"{price_val:,.0f} EGP"
                            except Exception:
                                pass
                    break
            except Exception:
                pass

        # 2. Iterate All Content Blocks/Containers Matching Registry
        if pattern_cfg.container_selectors:
            selector_str = ", ".join(pattern_cfg.container_selectors)
            candidate_blocks = soup.select(selector_str)

            for block in candidate_blocks:
                block_text = block.get_text(" ", strip=True)

                # Skip reviews or auth prompt blocks
                if any(x in block_text for x in ["Write a review", "Please login", "login or register"]):
                    continue

                # Skip image-only blocks if configured
                if pattern_cfg.skip_empty_image_blocks and len(block_text) < pattern_cfg.min_block_text_length:
                    continue

                # A. Parse List Items (ul/li, .qwen-markdown-list li, etc.)
                for li in block.select("li"):
                    txt = li.get_text(" ", strip=True)
                    cls._parse_delimited_text(txt, pattern_cfg.delimiters, dom_specs)

                # B. Parse Paragraphs and Divs
                for p in block.select("p, div.qwen-markdown-paragraph, tr"):
                    txt = p.get_text(" ", strip=True)
                    if not cls._parse_delimited_text(txt, pattern_cfg.delimiters, dom_specs):
                        for prefix in [
                            "Model Name",
                            "Model Number",
                            "Color",
                            "Operating System",
                            "Processor",
                            "Graphics",
                        ]:
                            if txt.startswith(prefix) and len(txt) > len(prefix) + 2:
                                val = txt[len(prefix) :].strip()
                                if 1 < len(val) < 150:
                                    dom_specs[prefix] = val

                # C. Parse HTML Tables (table tr with >= 2 cells)
                for row in block.select("table tr"):
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        k = cells[0].get_text(separator=" ", strip=True)
                        v = cells[1].get_text(separator=" ", strip=True)
                        k = re.sub(r"[:\*]+$", "", k).strip()
                        v = html_lib.unescape(v).replace("\xa0", " ").strip()
                        if (
                            k
                            and v
                            and len(k) < 60
                            and len(v) < 600
                            and k.lower() not in ("category", "specification", "specification details", "specifications")
                        ):
                            dom_specs[k] = v

                # D. Parse Headings with Sibling Lists/Paragraphs (h2, h3, h4 followed by ul, ol, p, div)
                for h in block.select("h2, h3, h4"):
                    h_text = h.get_text(" ", strip=True).rstrip(":")
                    if 2 < len(h_text) < 40 and not any(h_text.lower().startswith(x) for x in ["about", "review", "related", "write a"]):
                        sibling = h.find_next_sibling()
                        if sibling and sibling.name in ["ul", "ol", "p", "div"]:
                            sib_text = sibling.get_text(" ", strip=True)
                            if 1 < len(sib_text) < 400:
                                dom_specs[h_text] = sib_text

                # E. Parse Raw Text Lines with Section Tracking (for plain text / <br> separated specs)
                current_section: str | None = None
                lines = [l.strip() for l in block.get_text("\n", strip=True).split("\n") if l.strip()]
                for idx, line_clean in enumerate(lines):
                    # Check if line acts as a section header
                    clean_lower = line_clean.lower().strip(":")
                    if any(
                        clean_lower.startswith(sec)
                        for sec in [
                            "processor", "cpu", "graphics", "gpu", "memory", "ram",
                            "storage", "display", "screen", "battery", "power", "audio",
                            "operating system", "ports", "connectivity", "physical"
                        ]
                    ) and len(line_clean) < 40 and ":" not in line_clean:
                        current_section = line_clean.strip(":")
                        # Lookahead: If next line has no colon and looks like hardware value, capture it
                        if idx + 1 < len(lines):
                            next_l = lines[idx + 1]
                            if ":" not in next_l and 3 < len(next_l) < 120:
                                if any(x in clean_lower for x in ["processor", "cpu"]) and any(x in next_l.lower() for x in ["intel", "amd", "core", "ryzen", "celeron", "athlon"]):
                                    dom_specs["Processor"] = next_l
                                elif any(x in clean_lower for x in ["graphics", "gpu"]) and any(x in next_l.lower() for x in ["nvidia", "geforce", "rtx", "gtx", "radeon", "intel", "arc", "iris"]):
                                    dom_specs["Graphics"] = next_l
                        continue

                    cls._parse_delimited_text(line_clean, pattern_cfg.delimiters, dom_specs, current_section=current_section)

                # F. Raw Description Accumulation
                desc_chunk = block.get_text("\n", strip=True)
                if desc_chunk and len(desc_chunk) >= pattern_cfg.min_block_text_length:
                    if desc_chunk not in raw_desc_parts:
                        raw_desc_parts.append(desc_chunk)

        # 3. Flyer Image Detection
        has_specs_image = False
        specs_image_url: str | None = None

        if pattern_cfg.flyer_image_selectors:
            flyer_sel_str = ", ".join(pattern_cfg.flyer_image_selectors)
            for img in soup.select(flyer_sel_str):
                src = img.get("src") or img.get("data-src")
                if not src:
                    continue
                src_lower = src.lower()
                if any(ext in src_lower for ext in [".jpg", ".jpeg", ".png", ".webp"]) and not any(
                    x in src_lower for x in ["star", "icon", "badge", "avatar", "payment", "logo"]
                ):
                    has_specs_image = True
                    specs_image_url = urljoin(base_url, src) if base_url else src
                    break

        # 4. Quality Gate on Raw DOM Specs
        has_dom_hardware_spec = any(
            any(
                hw in k.lower()
                for hw in [
                    "cpu",
                    "processor",
                    "ram",
                    "memory",
                    "gpu",
                    "graphics",
                    "storage",
                    "drive",
                    "display",
                    "screen",
                    "model name",
                ]
            )
            for k in dom_specs
        )
        has_text_specs = len(dom_specs) >= 2 and has_dom_hardware_spec

        # 5. Hybrid Core Hardware Enrichment Pass
        # Extract title specifications as safety net
        title_specs = TitleSpecExtractor.extract(title, specs_image_url=specs_image_url)
        slots = TitleSpecExtractor.detect_core_slots(dom_specs)

        # Storage capacity enrichment from raw description if lost or missing
        if not slots["storage"] and raw_desc_parts:
            full_desc = " ".join(raw_desc_parts)
            st_m = re.search(r"Storage\s+(?:Capacity\s*)?[:\s]+(\d{3,4}\s*GB|\d\s*TB(?:\s*PCIe|\s*SSD|\s*NVMe)?)", full_desc, re.I)
            if not st_m:
                st_m = re.search(r"\b(\d{1,2}\s*TB|\d{3,4}\s*GB)\s*(?:PCIe\s*(?:\d\.\d\s*)?SSD|NVMe\s*SSD|SSD|HDD)\b", full_desc, re.I)
            if st_m:
                dom_specs["Storage"] = st_m.group(0).strip()
                slots["storage"] = dom_specs["Storage"]

        # Display enrichment from raw description if lost or missing
        if not slots["display"] and raw_desc_parts:
            full_desc = " ".join(raw_desc_parts)
            disp_m = re.search(r"Display:\s*(\d{2}(?:\.\d)?-inch[^\n\r]+)", full_desc, re.I)
            if not disp_m:
                disp_m = re.search(r"\b(\d{2}(?:\.\d)?-inch\s*(?:WQXGA|WUXGA|FHD\+?|QHD\+?|OLED|IPS)[^\n\r]*)", full_desc, re.I)
            if disp_m:
                dom_specs["Display"] = disp_m.group(1).strip()
                slots["display"] = dom_specs["Display"]

        # Backfill any missing core slots from Title
        if not slots["cpu"] and "Processor" in title_specs:
            dom_specs["Processor"] = title_specs["Processor"]
        if not slots["ram"] and "Memory" in title_specs:
            dom_specs["Memory"] = title_specs["Memory"]
        if not slots["storage"] and "Storage" in title_specs:
            dom_specs["Storage"] = title_specs["Storage"]
        if not slots["gpu"] and "Graphics" in title_specs:
            dom_specs["Graphics"] = title_specs["Graphics"]
        if not slots["display"] and "Display" in title_specs:
            dom_specs["Display"] = title_specs["Display"]
        if "Operating System" not in dom_specs and "Operating System" in title_specs:
            dom_specs["Operating System"] = title_specs["Operating System"]

        final_specs: dict[str, str] = {}
        specs_extraction_source = "dom"
        specs_fallback_reason: str | None = None

        if has_text_specs:
            final_specs = dom_specs
            specs_extraction_source = "dom"
            specs_fallback_reason = None
        else:
            final_specs = {**dom_specs, **title_specs}
            has_text_specs = False
            specs_extraction_source = "title_fallback"
            if has_specs_image:
                specs_fallback_reason = "No text specs found in PDP; image flyer only"
            else:
                specs_fallback_reason = "No text specs found in PDP"

        raw_desc = "\n\n".join(raw_desc_parts) if raw_desc_parts else None

        return SpecExtractionResult(
            specs=final_specs,
            raw_description=raw_desc,
            mpn=mpn,
            model_code=model_code,
            price_val=price_val,
            price_str=price_str,
            has_text_specs=has_text_specs,
            specs_extraction_source=specs_extraction_source,
            specs_fallback_reason=specs_fallback_reason,
            has_specs_image=has_specs_image,
            specs_image_url=specs_image_url,
        )

    @staticmethod
    def _parse_delimited_text(
        txt: str,
        delimiters: list[str],
        specs_dict: dict[str, str],
        current_section: str | None = None,
    ) -> bool:
        """Helper to split a line by delimiters into Key: Value if valid, with collision prevention."""
        for delim in delimiters:
            search_delim = " - " if delim == "-" else delim
            if search_delim in txt:
                k, v = txt.split(search_delim, 1)
                k_clean = k.strip()
                v_clean = v.strip()
                if (
                    k_clean
                    and v_clean
                    and 1 < len(k_clean) < 50
                    and len(v_clean) < 250
                    and not any(k_clean.startswith(x) for x in ["Note", "Important", "Click", "http", "www"])
                    and not re.match(r"^[\d\.,\s]+$", k_clean)
                ):
                    target_key = k_clean
                    k_lower = k_clean.lower()

                    # Prevent destructive overwriting of generic keys (e.g. Capacity, Type, Model)
                    if current_section and k_lower in ("capacity", "type", "speed", "slots", "installed", "interface", "form factor", "size"):
                        target_key = f"{current_section} {k_clean}"
                    elif k_clean in specs_dict and specs_dict[k_clean] != v_clean:
                        if k_lower == "capacity":
                            existing_val = specs_dict[k_clean].lower()
                            new_val = v_clean.lower()
                            if ("wh" in existing_val and any(s in new_val for s in ["gb", "tb", "ssd", "nvme"])) or ("wh" in new_val and any(s in existing_val for s in ["gb", "tb", "ssd", "nvme"])):
                                if "wh" in existing_val:
                                    specs_dict["Battery Capacity"] = specs_dict.pop(k_clean)
                                    specs_dict["Storage Capacity"] = v_clean
                                    return True
                                else:
                                    specs_dict["Storage Capacity"] = specs_dict.pop(k_clean)
                                    specs_dict["Battery Capacity"] = v_clean
                                    return True
                        target_key = f"{current_section} {k_clean}" if current_section else f"{k_clean} ({v_clean[:15]})"

                    specs_dict[target_key] = v_clean
                    return True
        return False
