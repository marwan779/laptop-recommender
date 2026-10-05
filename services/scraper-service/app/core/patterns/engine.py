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

        # 1.2 Parse Next.js App Router RSC Stream Payloads
        cls._extract_nextjs_rsc_payload(soup, dom_specs, raw_desc_parts)

        # 1.5 Parse Dynamic Raw Specs Attributes
        known_data_attrs = getattr(pattern_cfg, "learned_data_attributes", ["data-raw-spec"])
        for attr in known_data_attrs:
            for elem in soup.find_all(attrs={attr: True}):
                raw_attr = elem.get(attr, "")
                if raw_attr and len(raw_attr.strip()) > 10:
                    cls._parse_raw_spec_attribute(raw_attr, dom_specs)
                    if raw_attr not in raw_desc_parts:
                        raw_desc_parts.append(raw_attr)

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

        # 4. Tier 1 Quality Check on Raw DOM Specs
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
        has_tier1_specs = len(dom_specs) >= 2 and has_dom_hardware_spec

        pattern_learned = False
        learned_pattern_type: str | None = None

        # ---------------------------------------------------------------------
        # Tier 2: Autonomous Pattern Discovery Engine
        # Runs when registered selectors / known attributes yield < 2 hardware specs
        # ---------------------------------------------------------------------
        if not has_tier1_specs:
            discovery_result = cls._run_autonomous_discovery(
                soup=soup,
                dom_specs=dom_specs,
                raw_desc_parts=raw_desc_parts,
                pattern_cfg=pattern_cfg,
                store_key=store_key,
            )
            if discovery_result:
                pattern_learned = True
                learned_pattern_type = discovery_result
                print(
                    f"[{pattern_cfg.name}] [Adaptive Learning] Discovered and registered "
                    f"new pattern '{discovery_result}' for store '{store_key}'!"
                )

        # Re-evaluate quality gate after discovery
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
        if "Warranty" not in dom_specs and "Warranty" in title_specs:
            dom_specs["Warranty"] = title_specs["Warranty"]
        if "Certification" not in dom_specs and "Certification" in title_specs:
            dom_specs["Certification"] = title_specs["Certification"]
        if "Cores" not in dom_specs and "Cores" in title_specs:
            dom_specs["Cores"] = title_specs["Cores"]

        final_specs: dict[str, str] = {}
        specs_extraction_source = "dom"
        specs_fallback_reason: str | None = None
        is_anomaly = False
        anomaly_reason: str | None = None

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
                is_anomaly = True
                anomaly_reason = f"Store '{store_key}' PDP has neither text specs nor flyer images across all discovery tiers"
                print(
                    f"[{pattern_cfg.name}] [Pattern Anomaly] Store '{store_key}' on '{title[:50]}' "
                    f"failed all DOM discovery tiers. Fallback to title."
                )

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
            pattern_learned=pattern_learned,
            learned_pattern_type=learned_pattern_type,
            is_anomaly=is_anomaly,
            anomaly_reason=anomaly_reason,
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

    @classmethod
    def _extract_nextjs_rsc_payload(
        cls,
        soup: BeautifulSoup,
        specs_dict: dict[str, str],
        raw_desc_parts: list[str],
    ) -> bool:
        """Extract specifications and description from Next.js App Router RSC streamed chunks."""
        found = False
        chunks: list[str] = []
        for s in soup.find_all("script"):
            txt = s.string or s.get_text() or ""
            if "self.__next_f.push" in txt:
                matches = re.findall(r'self\.__next_f\.push\((\[1,\s*".*?"\])\)', txt)
                for m in matches:
                    try:
                        parsed = json.loads(m)
                        if isinstance(parsed, list) and len(parsed) >= 2 and isinstance(parsed[1], str):
                            chunks.append(parsed[1])
                    except Exception:
                        pass

        if not chunks:
            return False

        rsc_text = "".join(chunks)
        spec_start = rsc_text.find('"specifications":[')
        if spec_start != -1:
            start = spec_start + len('"specifications":')
            bracket_count = 0
            end = -1
            for i in range(start, len(rsc_text)):
                if rsc_text[i] == "[":
                    bracket_count += 1
                elif rsc_text[i] == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end = i + 1
                        break
            if end != -1:
                try:
                    raw_specs = json.loads(rsc_text[start:end])
                    if isinstance(raw_specs, list):
                        for item in raw_specs:
                            if isinstance(item, dict):
                                k = str(item.get("name", "")).strip()
                                v = str(item.get("value", "")).strip()
                                if k and v and len(k) < 60 and len(v) < 600:
                                    specs_dict[k] = v
                                    found = True
                except Exception:
                    pass

        desc_match = re.search(r'"description":\s*("(?:\\.|[^"\\])*")', rsc_text)
        if desc_match:
            try:
                d = json.loads(desc_match.group(1))
                if d and isinstance(d, str) and d.strip() and d.strip().lower() != "page not found":
                    if d.strip() not in raw_desc_parts:
                        raw_desc_parts.append(d.strip())
            except Exception:
                pass

        return found

    @staticmethod
    def _parse_raw_spec_attribute(raw_text: str, specs_dict: dict[str, str]) -> None:
        """Parse raw serialized specifications (e.g. CompuMarts data-raw-spec attributes)."""
        if not raw_text or not raw_text.strip():
            return
        text = html_lib.unescape(raw_text).replace("\xa0", " ").replace("\r", "")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return

        # 1. Check if predominantly tab-delimited
        tab_lines = [l for l in lines if "\t" in l]
        if len(tab_lines) >= len(lines) * 0.35:
            for l in lines:
                if "\t" in l:
                    parts = l.split("\t", 1)
                    k = parts[0].strip().rstrip(":")
                    v = parts[1].strip()
                    if k and v and len(k) < 60 and len(v) < 600:
                        if k.lower() not in ("category", "specification", "specification details", "specifications"):
                            specs_dict[k] = v
            return

        # 2. Check if delimited by colons or dashes
        delim_lines = [l for l in lines if any(d in l for d in [":", "—", "–", " - "])]
        if len(delim_lines) >= len(lines) * 0.6:
            for l in lines:
                for d in [":", "—", "–", " - "]:
                    if d in l:
                        k, v = l.split(d, 1)
                        k, v = k.strip().rstrip(":"), v.strip()
                        if k and v and len(k) < 60 and len(v) < 600:
                            if k.lower() not in ("category", "specification", "specification details", "specifications"):
                                specs_dict[k] = v
                            break
            return

        # 3. Alternating lines: Key, Value, Key, Value
        start_idx = 0
        if len(lines) > 1 and lines[0].lower() in ("category", "specification", "specification details", "specifications"):
            start_idx = 1
            if len(lines) > 2 and lines[1].lower() in ("specification details", "specifications", "value"):
                start_idx = 2

        i = start_idx
        while i < len(lines):
            k = lines[i].rstrip(":").strip()
            v = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if k and v and len(k) < 60 and len(v) < 600:
                if k.lower() not in ("category", "specification details", "specification", "specifications"):
                    specs_dict[k] = v
            i += 2

    @classmethod
    def _run_autonomous_discovery(
        cls,
        soup: BeautifulSoup,
        dom_specs: dict[str, str],
        raw_desc_parts: list[str],
        pattern_cfg: StorePatternConfig,
        store_key: str,
    ) -> str | None:
        """Autonomous discovery pipeline that searches the full DOM when registered patterns miss."""
        # 1. Discover unindexed data-* attributes containing serialized specs
        data_attr_result = cls._discover_data_attributes(soup, dom_specs, raw_desc_parts, pattern_cfg, store_key)
        if data_attr_result:
            return data_attr_result

        # 2. Discover unregistered global HTML tables with hardware keys
        table_result = cls._discover_unregistered_tables(soup, dom_specs, raw_desc_parts, pattern_cfg, store_key)
        if table_result:
            return table_result

        # 3. Discover collapsible disclosure / tab panels (<details>, .accordion, etc.)
        panel_result = cls._discover_collapsible_panels(soup, dom_specs, raw_desc_parts, pattern_cfg, store_key)
        if panel_result:
            return panel_result

        # 4. Discover inline script payloads (window.__renderSpecTable, JSON spec blobs)
        script_result = cls._discover_script_payloads(soup, dom_specs, raw_desc_parts, store_key)
        if script_result:
            return script_result

        return None

    @classmethod
    def _discover_data_attributes(
        cls,
        soup: BeautifulSoup,
        dom_specs: dict[str, str],
        raw_desc_parts: list[str],
        pattern_cfg: StorePatternConfig,
        store_key: str,
    ) -> str | None:
        """Discover any data-* attribute across the DOM containing hardware specifications."""
        known_attrs = set(getattr(pattern_cfg, "learned_data_attributes", ["data-raw-spec"]))
        for elem in soup.find_all(True):
            for attr, val in list(elem.attrs.items()):
                if attr.startswith("data-") and attr not in known_attrs and isinstance(val, str) and len(val) > 20:
                    val_lower = val.lower()
                    hw_hits = sum(
                        1
                        for hw in [
                            "processor", "cpu", "memory", "ram", "storage", "ssd",
                            "graphics", "gpu", "display", "screen", "resolution", "part no"
                        ]
                        if hw in val_lower
                    )
                    if hw_hits >= 2:
                        initial_len = len(dom_specs)
                        cls._parse_raw_spec_attribute(val, dom_specs)
                        if len(dom_specs) > initial_len:
                            if val not in raw_desc_parts:
                                raw_desc_parts.append(val)
                            PatternRegistry.learn_attribute(store_key, attr)
                            return f"data_attribute:{attr}"
        return None

    @classmethod
    def _discover_unregistered_tables(
        cls,
        soup: BeautifulSoup,
        dom_specs: dict[str, str],
        raw_desc_parts: list[str],
        pattern_cfg: StorePatternConfig,
        store_key: str,
    ) -> str | None:
        """Discover HTML tables anywhere on the page that contain hardware specification rows."""
        for table in soup.find_all("table"):
            table_specs: dict[str, str] = {}
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    k = cells[0].get_text(separator=" ", strip=True)
                    v = cells[1].get_text(separator=" ", strip=True)
                    k_clean = re.sub(r"[:\*]+$", "", k).strip()
                    v_clean = html_lib.unescape(v).replace("\xa0", " ").strip()
                    if (
                        k_clean
                        and v_clean
                        and len(k_clean) < 60
                        and len(v_clean) < 600
                        and k_clean.lower() not in ("category", "specification", "specification details", "specifications")
                    ):
                        table_specs[k_clean] = v_clean

            has_hw = sum(
                1
                for k in table_specs
                if any(hw in k.lower() for hw in ["processor", "cpu", "memory", "ram", "storage", "ssd", "graphics", "gpu", "display", "screen", "part no"])
            )
            if has_hw >= 2:
                dom_specs.update(table_specs)
                desc = table.get_text("\n", strip=True)
                if desc and desc not in raw_desc_parts:
                    raw_desc_parts.append(desc)
                deduced_selector = cls._deduce_element_selector(table)
                PatternRegistry.learn_selector(store_key, deduced_selector)
                return f"unregistered_table:{deduced_selector}"
        return None

    @classmethod
    def _discover_collapsible_panels(
        cls,
        soup: BeautifulSoup,
        dom_specs: dict[str, str],
        raw_desc_parts: list[str],
        pattern_cfg: StorePatternConfig,
        store_key: str,
    ) -> str | None:
        """Discover specifications inside <details>, accordion panels, or hidden tab wrappers."""
        for panel in soup.select("details, .accordion, .disclosure, .tab-content, .tab-pane, [data-tab-content]"):
            panel_specs: dict[str, str] = {}
            for li in panel.select("li, p, tr"):
                txt = li.get_text(" ", strip=True)
                cls._parse_delimited_text(txt, pattern_cfg.delimiters, panel_specs)

            has_hw = sum(
                1
                for k in panel_specs
                if any(hw in k.lower() for hw in ["processor", "cpu", "memory", "ram", "storage", "ssd", "graphics", "gpu", "display", "screen"])
            )
            if has_hw >= 2:
                dom_specs.update(panel_specs)
                desc = panel.get_text("\n", strip=True)
                if desc and desc not in raw_desc_parts:
                    raw_desc_parts.append(desc)
                deduced_selector = cls._deduce_element_selector(panel)
                PatternRegistry.learn_selector(store_key, deduced_selector)
                return f"collapsible_panel:{deduced_selector}"
        return None

    @classmethod
    def _discover_script_payloads(
        cls,
        soup: BeautifulSoup,
        dom_specs: dict[str, str],
        raw_desc_parts: list[str],
        store_key: str,
    ) -> str | None:
        """Discover specification strings or JSON objects embedded in <script> tags."""
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text() or ""
            if not script_text or len(script_text) < 30:
                continue

            # Check Next.js App Router RSC push stream
            if "self.__next_f.push" in script_text and "specifications" in script_text:
                init_len = len(dom_specs)
                cls._extract_nextjs_rsc_payload(soup, dom_specs, raw_desc_parts)
                if len(dom_specs) > init_len:
                    return "script_payload:nextjs_rsc"

            # Check window.__renderSpecTable signature
            m_spec = re.search(r'window\.__renderSpecTable\s*\([^,]+,\s*"([^"]+)"', script_text)
            if m_spec:
                try:
                    raw_payload = m_spec.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                except Exception:
                    raw_payload = m_spec.group(1)
                initial_len = len(dom_specs)
                cls._parse_raw_spec_attribute(raw_payload, dom_specs)
                if len(dom_specs) > initial_len:
                    if raw_payload not in raw_desc_parts:
                        raw_desc_parts.append(raw_payload)
                    return "script_payload:window.__renderSpecTable"

            # Check for JSON objects with hardware keys
            if any(term in script_text for term in ['"processor":', '"Processor":', '"Graphics":', '"graphics":']):
                m_json = re.search(r'(\{[\s\S]*?"(?:Processor|processor|Graphics|graphics)"[\s\S]*?\})', script_text)
                if m_json:
                    try:
                        data = json.loads(m_json.group(1))
                        if isinstance(data, dict):
                            added = 0
                            for k, v in data.items():
                                if isinstance(v, str) and 1 < len(k) < 60 and len(v) < 600:
                                    dom_specs[k] = v
                                    added += 1
                            if added >= 2:
                                return "script_payload:embedded_json"
                    except Exception:
                        pass
        return None

    @staticmethod
    def _deduce_element_selector(elem) -> str:
        """Generate a clean CSS selector for a discovered element."""
        classes = elem.get("class", [])
        if classes:
            valid_cls = [c for c in classes if not c.startswith("js-") and len(c) > 2]
            if valid_cls:
                return f"{elem.name}.{'.'.join(valid_cls)}"

        elem_id = elem.get("id")
        if elem_id and len(elem_id) < 40 and not any(c.isdigit() for c in elem_id[:3]):
            return f"#{elem_id}"

        parent = elem.parent
        if parent and parent.name not in ["html", "body", "[document]"]:
            parent_classes = parent.get("class", [])
            if parent_classes:
                valid_pcls = [c for c in parent_classes if len(c) > 2]
                if valid_pcls:
                    return f".{valid_pcls[0]} {elem.name}"

        return elem.name
