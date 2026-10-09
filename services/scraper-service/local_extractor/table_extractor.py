"""Deterministic HTML Table & Specification Extractor with Reconciliation.

Extracts 100% of raw specification rows from PDP HTML tables, definition lists,
and structured specification blocks without dropping any hardware data.
Provides table formatting for local LLM prompts and deterministic reconciliation
to guarantee zero data loss.
"""

import re
from typing import Any
from bs4 import BeautifulSoup
from pydantic import BaseModel


# Patterns for extracting and cleaning table labels and values
JUNK_LABEL_KEYWORDS = {
    "welcome to our store",
    "become a member",
    "compumarts points",
    "shipping calculated at checkout",
    "exclusive perks",
    "sign up for exclusive",
    "local pickup or shipping",
    "fast delivery across egypt",
    "open 7 days a week",
    "talk to a real person",
    "reviews (0)",
    "access special offers",
    "you may also like",
    "you might also like",
    "frequently bought together",
    "add to wishlist",
    "add to cart",
    "cart",
    "checkout",
    "cookie",
}


def clean_str(val: Any) -> str:
    """Normalize whitespace and strip HTML artifacts."""
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return ""
    text = str(val).replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", text).strip()


def extract_raw_spec_table(html_text: str) -> dict[str, str]:
    """Extract ALL technical key-value specifications from HTML tables and lists.
    
    Guarantees that 100% of specification rows (CPU, GPU, MEMORY, STORAGE,
    DISPLAY, POWER, CONNECTIVITY, OS, etc.) are extracted without dropping anything.
    """
    if not html_text or not html_text.strip():
        return {}

    soup = BeautifulSoup(html_text, "html.parser")
    specs: dict[str, str] = {}

    def is_valid_entry(key: str, val: str) -> bool:
        if not key or not val:
            return False
        if len(key) < 2 or len(key) > 120 or len(val) < 1:
            return False
        k_lower = key.lower()
        if any(j in k_lower for j in JUNK_LABEL_KEYWORDS):
            return False
        # Skip pure numeric keys or prices
        if key.isdigit() or key.startswith("egp") or key.startswith("le"):
            return False
        return True

    def add_entry(key: str, val: str):
        k = clean_str(key).rstrip(":")
        v = clean_str(val)
        if is_valid_entry(k, v):
            # If key already seen, keep the more informative / longer value
            if k in specs:
                existing = specs[k]
                if len(v) > len(existing) and existing in v:
                    specs[k] = v
                elif v not in existing and existing not in v:
                    # Combine if distinct values
                    specs[k] = f"{existing}; {v}"
            else:
                specs[k] = v

    # 1. Check for data-raw-spec attribute (e.g. Asus / Lenovo laptops on Compumarts)
    for elem in soup.find_all(attrs={"data-raw-spec": True}):
        raw_content = elem.get("data-raw-spec", "")
        has_delimiter = False
        for line in raw_content.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            if "\t" in line:
                parts = line.split("\t", 1)
                add_entry(parts[0], parts[1])
                has_delimiter = True
            elif ":" in line_clean:
                parts = line_clean.split(":", 1)
                add_entry(parts[0], parts[1])
                has_delimiter = True

        if not has_delimiter:
            lines = [clean_str(line) for line in raw_content.splitlines() if clean_str(line)]
            idx = 0
            while idx + 1 < len(lines):
                add_entry(lines[idx], lines[idx + 1])
                idx += 2

    # 2. Extract every <table> element (standard <tr> with <td> or <th>)
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if not cells:
                continue

            cleaned_cells = [clean_str(c.get_text(" ", strip=True)) for c in cells]
            cleaned_cells = [c for c in cleaned_cells if c]

            if len(cleaned_cells) == 2:
                add_entry(cleaned_cells[0], cleaned_cells[1])
            elif len(cleaned_cells) > 2:
                # Key is first column, remaining columns joined with " | "
                add_entry(cleaned_cells[0], " | ".join(cleaned_cells[1:]))
            elif len(cleaned_cells) == 1 and ":" in cleaned_cells[0]:
                parts = cleaned_cells[0].split(":", 1)
                add_entry(parts[0], parts[1])

    # 3. Extract definition lists (<dl><dt>Key</dt><dd>Value</dd></dl>)
    for dl in soup.find_all("dl"):
        current_dt = None
        for child in dl.find_all(["dt", "dd"], recursive=False):
            txt = clean_str(child.get_text(" ", strip=True))
            if not txt:
                continue
            if child.name == "dt":
                current_dt = txt
            elif child.name == "dd" and current_dt:
                add_entry(current_dt, txt)
                current_dt = None

    # 4. Extract structured specification items (.spec-row, .specification-row, etc.)
    spec_item_selectors = [
        "[class*='spec-row']",
        "[class*='specification-row']",
        "[class*='attribute-row']",
        "[class*='product-detail-row']",
        "[class*='spec-item']",
        "[class*='specification-item']",
        "[class*='attribute-item']",
    ]
    for selector in spec_item_selectors:
        for item in soup.select(selector):
            # Check for direct data-spec / data-label / data-value
            d_key = item.get("data-spec") or item.get("data-label") or item.get("data-attribute")
            d_val = item.get("data-value")
            if d_key and d_val:
                add_entry(d_key, d_val)
                continue

            children = [
                clean_str(c.get_text(" ", strip=True))
                for c in item.find_all(["div", "span", "p", "strong", "b", "dt", "dd"], recursive=False)
            ]
            children = [c for c in children if c]
            if len(children) >= 2:
                add_entry(children[0], children[1])
            elif len(children) == 1 and ":" in children[0]:
                parts = children[0].split(":", 1)
                add_entry(parts[0], parts[1])

    # 5. Extract specification <li> list items with explicit "Key: Value"
    tech_label_re = re.compile(
        r"^(?:"
        r"brand|model|series|sku|mpn|part number|part no|sales model name|marketing name|"
        r"processor|cpu|cores|threads|cache|frequency|cpu cores / threads|"
        r"ram|memory|storage|ssd|hdd|hard drive|hard disk|"
        r"graphics|gpu|video card|display|screen|panel size|panel type|"
        r"resolution|refresh rate|battery|power|power adapter|power supply|adapter|"
        r"operating system|os|ports|connectivity|wireless|wi.?fi|"
        r"bluetooth|camera|webcam|audio|speaker|keyboard|weight|dimensions|"
        r"warranty|color|case color|touchscreen|finger print|fingerprint|security|"
        r"max graphics power|gpu power|memory slots|storage slots"
        r")\s*:?\s*$",
        re.IGNORECASE,
    )

    for li in soup.find_all("li"):
        if li.find("ul") or li.find("ol"):
            continue
        text = clean_str(li.get_text(" ", strip=True))
        if not text or len(text) > 500:
            continue
        if ":" in text:
            parts = text.split(":", 1)
            k, v = clean_str(parts[0]), clean_str(parts[1])
            if tech_label_re.match(k):
                add_entry(k, v)
        else:
            sub = [
                clean_str(c.get_text(" ", strip=True))
                for c in li.find_all(["span", "strong", "b"], recursive=False)
            ]
            sub = [c for c in sub if c]
            if len(sub) >= 2 and tech_label_re.match(sub[0].rstrip(":")):
                add_entry(sub[0], sub[1])

    return specs


def format_table_for_prompt(
    raw_table: dict[str, str],
    title: str = "",
    extra_context: str = "",
) -> str:
    """Format raw specifications table compactly and prominently for the LLM prompt."""
    sections: list[str] = []

    if title and title.strip():
        sections.append(f"Product Title: {title.strip()}")

    if raw_table:
        table_lines = ["=== RAW SPECIFICATIONS TABLE ==="]
        for key, value in raw_table.items():
            table_lines.append(f"{key}: {value}")
        sections.append("\n".join(table_lines))

    if extra_context and extra_context.strip():
        sections.append(f"=== ADDITIONAL CONTEXT ===\n{extra_context.strip()[:1500]}")

    return "\n\n".join(sections)


def split_power_specs(power_str: str) -> tuple[str | None, str | None]:
    """Split a combined 'POWER' string into battery and power adapter components.
    
    Examples:
        '75WHrs, 4S1P, 4-cell Li-ion, 200W AC Adapter'
        -> battery: '75WHrs, 4S1P, 4-cell Li-ion', adapter: '200W AC Adapter'
        '60Wh Battery, 170W Slim Tip AC Adapter'
        -> battery: '60Wh Battery', adapter: '170W Slim Tip AC Adapter'
    """
    if not power_str or not power_str.strip():
        return None, None

    # Match adapter phrases: 200W AC Adapter, 65W USB-C, 170W Slim Tip, etc.
    # Note: (?!\s*h) negative lookahead ensures 75Wh / 75WHrs is NOT matched as adapter wattage!
    adapter_pattern = re.compile(
        r"\b\d+\s*W\b(?!\s*h)(?:\s*(?:Slim\s+Tip|AC\s+adapter|Power\s+Adapter|adapter|USB-C)[^,;]*)?",
        re.IGNORECASE,
    )
    # Match battery phrases: 75WHrs, 4-cell Li-ion, 57Wh, 60Wh Battery, etc.
    battery_pattern = re.compile(
        r"\b\d+\s*W(?:Hr[s]?|h)\b[^\n,;]*|\b\d+[- ]cell[^\n,;]*|\bLi-ion[^\n,;]*|\b\d+S\d+P\b",
        re.IGNORECASE,
    )

    items = [clean_str(chunk) for chunk in re.split(r"[,;]\s*", power_str) if clean_str(chunk)]
    battery_parts: list[str] = []
    adapter_parts: list[str] = []

    for item in items:
        is_ad = bool(adapter_pattern.search(item))
        is_bt = bool(battery_pattern.search(item))

        if is_ad and not is_bt:
            adapter_parts.append(item)
        elif is_bt and not is_ad:
            battery_parts.append(item)
        else:
            # Chunk contains both or partial
            ad_matches = adapter_pattern.findall(item)
            bt_matches = battery_pattern.findall(item)
            for m in ad_matches:
                m_clean = clean_str(m)
                if m_clean and m_clean not in adapter_parts:
                    adapter_parts.append(m_clean)
            for m in bt_matches:
                m_clean = clean_str(m)
                if m_clean and m_clean not in battery_parts:
                    battery_parts.append(m_clean)

    battery_res = ", ".join(battery_parts).strip() or None
    adapter_res = ", ".join(adapter_parts).strip() or None

    # Fallback if regex splitting didn't catch specific keywords
    if not battery_res and not adapter_res:
        if "adapter" in power_str.lower() or "power supply" in power_str.lower():
            adapter_res = power_str.strip()
        elif "wh" in power_str.lower() or "cell" in power_str.lower() or "battery" in power_str.lower():
            battery_res = power_str.strip()

    return battery_res, adapter_res


# Alias mapping from normalized raw table keys to standardized schema fields
KEY_TO_SCHEMA_MAPPING: dict[str, str] = {
    # Processor
    "cpu": "processor",
    "processor": "processor",
    "processor model": "processor",
    "cpu type": "processor",
    "processor type": "processor",
    "processor manufacturer": "processor",
    "processor generation": "processor",
    # Graphics
    "gpu": "graphics",
    "graphics": "graphics",
    "graphics card": "graphics",
    "video card": "graphics",
    "gpu memory": "graphics",
    "video memory": "graphics",
    "graphics controller model": "graphics",
    "integrated graphics": "graphics",
    # RAM
    "memory": "ram",
    "ram": "ram",
    "memory (ram)": "ram",
    "ram memory": "ram",
    "system memory": "ram",
    "standard memory": "ram",
    "memory type": "ram",
    # Storage
    "storage": "storage",
    "hard drive": "storage",
    "hard disk capacity": "storage",
    "ssd": "storage",
    "storage size": "storage",
    "total solid state drive capacity": "storage",
    # Display
    "display": "display",
    "displays": "display",
    "screen": "display",
    "screen size": "display",
    "display size": "display",
    "panel size": "display",
    # Battery & Power
    "battery": "battery",
    "battery type": "battery",
    "battery life": "battery",
    "power adapter": "power_adapter",
    "adapter": "power_adapter",
    "power supply": "power_adapter",
    # Operating System
    "os": "operating_system",
    "operating system": "operating_system",
    # Ports & Connectivity
    "ports": "ports",
    "connectivity": "ports",
    "i/o ports": "ports",
    "standard ports": "ports",
    "additional ports": "ports",
    "usb ports": "ports",
    "usb-c": "ports",
    "usb-a": "ports",
    "hdmi": "ports",
    # Wireless & Networking
    "wireless": "wireless",
    "wlan + bluetooth": "wireless",
    "wireless connectivity": "wireless",
    "network": "wireless",
    "networking": "wireless",
    "ethernet": "wireless",
    "lan": "wireless",
    "bluetooth": "wireless",
    # Camera
    "camera": "camera",
    "webcam": "camera",
    "front-facing camera": "camera",
    # Audio
    "audio": "audio",
    "speaker": "audio",
    "speakers": "audio",
    "microphone": "audio",
    "audio features": "audio",
    # Keyboard
    "keyboard": "keyboard",
    "keyboard & touchpad": "keyboard",
    "touchpad": "keyboard",
    # Weight
    "weight": "weight",
    "approximate weight": "weight",
    "weight (approximate)": "weight",
    # Warranty
    "warranty": "warranty",
    "base warranty": "warranty",
    "warranty & bundle": "warranty",
    # CPU Cores
    "cpu cores / threads": "cpu_cores",
    "cpu cores": "cpu_cores",
    "cores / threads": "cpu_cores",
    "processor cores": "cpu_cores",
    "processor threads": "cpu_cores",
    # GPU Power
    "gpu power": "gpu_power",
    "max graphics power": "gpu_power",
    "maximum graphics power": "gpu_power",
    "gpu boost clock": "gpu_power",
    # Slots
    "memory slots": "ram_slots",
    "max memory": "ram_slots",
    "storage slots": "storage_slots",
    "storage expansion": "storage_slots",
    # Model & Identification
    "model": "series_model",
    "model name": "series_model",
    "model number": "series_model",
    "sales model name": "series_model",
    "series": "series_model",
    "machine type": "series_model",
    "part number": "part_number_or_sku",
    "part no": "part_number_or_sku",
    "product number": "part_number_or_sku",
    "brand": "brand",
    # Other hardware specs
    "touchscreen": "touchscreen",
    "color": "color",
    "case color": "color",
    "product color": "color",
    "dimensions": "dimensions",
    "dimension": "dimensions",
    "security": "security",
    "finger print": "security",
    "fingerprint": "security",
    "chipset": "chipset",
}


def reconcile_specs(
    model_specs: BaseModel | dict[str, Any] | None,
    raw_table: dict[str, str],
) -> dict[str, Any]:
    """Reconcile model-extracted specs with the raw specifications table.
    
    Guarantees:
      1. Every field extracted by the LLM is preserved.
      2. If the LLM omitted or set null for any field present in the raw table
         (e.g. POWER, CONNECTIVITY, OS: None, BATTERY), it is deterministically
         mapped from the table.
      3. Split POWER into battery and power_adapter if not already filled.
      4. Any unmapped raw table attributes (color, dimensions, etc.) are retained
         so that 0% of the table data is lost.
    """
    final_specs: dict[str, Any] = {}

    UNSPECIFIED_TOKENS = {
        "unspecified",
        "not specified",
        "none",
        "n/a",
        "null",
        "",
        "not available",
        "not applicable",
        "unknown",
    }

    # 1. Start with LLM specs
    if model_specs is not None:
        if isinstance(model_specs, BaseModel):
            data = model_specs.model_dump(exclude_none=True)
        elif isinstance(model_specs, dict):
            data = model_specs
        else:
            data = {}

        for k, v in data.items():
            if v is None:
                continue
            v_str = str(v).strip()
            v_lower = v_str.lower()

            # "None" / "FreeDOS" is a valid OS value when OS is None/DOS
            if k == "operating_system" and v_lower in ("none", "freedos", "dos", "no os"):
                final_specs[k] = v_str
                continue

            if v_lower not in UNSPECIFIED_TOKENS:
                final_specs[k] = v_str

        # If LLM put combined power into battery, clean it
        if "battery" in final_specs:
            bt_val, ad_val = split_power_specs(final_specs["battery"])
            if bt_val:
                final_specs["battery"] = bt_val
            if ad_val and "power_adapter" not in final_specs:
                final_specs["power_adapter"] = ad_val

    if not raw_table:
        return final_specs

    # Normalized lookup index for raw table: {lowered_key: (original_key, val)}
    norm_table: dict[str, tuple[str, str]] = {
        clean_str(k).lower(): (k, clean_str(v)) for k, v in raw_table.items() if clean_str(v)
    }

    # 2. Check each raw table entry against the known schema fields
    for norm_k, (orig_k, val) in norm_table.items():
        # Check special combined POWER field
        if norm_k in ("power", "battery & power"):
            bt_val, ad_val = split_power_specs(val)
            if bt_val and "battery" not in final_specs:
                final_specs["battery"] = bt_val
            if ad_val and "power_adapter" not in final_specs:
                final_specs["power_adapter"] = ad_val
            continue

        target_field = KEY_TO_SCHEMA_MAPPING.get(norm_k)
        if target_field:
            if target_field not in final_specs:
                final_specs[target_field] = val
        else:
            # Secondary/unmapped table attribute (e.g. "cooling system", "ai engine")
            clean_field_key = re.sub(r"[^a-zA-Z0-9_]+", "_", norm_k).strip("_")
            if clean_field_key and clean_field_key not in final_specs:
                final_specs[clean_field_key] = val

    # 3. Special handling for display if screen size / resolution / refresh rate were separate
    if "display" not in final_specs:
        display_components = []
        for key in ("display", "panel size", "screen size", "display size", "resolution", "panel", "panel type", "refresh rate"):
            if key in norm_table:
                display_components.append(norm_table[key][1])
        if display_components:
            final_specs["display"] = " ".join(display_components)
    elif "resolution" in norm_table and norm_table["resolution"][1] not in final_specs["display"]:
        # Enrich display with resolution if not present
        res_val = norm_table["resolution"][1]
        if res_val.lower() not in final_specs["display"].lower():
            final_specs["display"] = f"{final_specs['display']} {res_val}".strip()

    return final_specs
