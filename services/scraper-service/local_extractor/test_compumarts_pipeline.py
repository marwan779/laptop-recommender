"""Full Level 1 and Level 2 CompuMarts Pipeline Test with Scrapling & Local LLM Extraction.

Extracts ALL technical hardware data from PDP (tables, spec lists, and descriptions),
filters out marketing noise, and passes pure technical context to the Local Model (Qwen 2.5).

Usage:
    # 1. Run Level 2 on the first 5 laptops:
    python local_extractor/test_compumarts_pipeline.py --level 2 --limit 5

    # 2. Run Full Level 2 on ALL in-stock laptops:
    python local_extractor/test_compumarts_pipeline.py --level 2

    # 3. Run Full Level 1 (fast catalog crawl):
    python local_extractor/test_compumarts_pipeline.py --level 1
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Any
# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bs4 import BeautifulSoup
from app.core.patterns.models import SpecExtractionResult
from app.engine.scrapling_engine import ScraplingEngine
from app.stores.compumarts import CompumartsStoreScraper, CompumartsSpecResult
from local_extractor import (
    LocalModelExtractor,
    extract_raw_spec_table,
    format_table_for_prompt,
    reconcile_specs,
)



def extract_all_technical_data(
    html_text: str,
) -> tuple[str, str | None]:
    """Extract technical specifications from varied product-page HTML layouts.

    Returns:
        A tuple containing:
        - Clean, deduplicated technical text for the LLM.
        - Raw extracted description text for downstream metadata.

    Supports:
        - HTML tables and comparison grids.
        - Definition lists (dt/dd).
        - Lists containing specification labels and values.
        - Generic specification rows and label/value pairs.
        - Product descriptions, details, and accordion sections.
        - Product JSON-LD, including additionalProperty values.
        - Product metadata and embedded structured attributes.

    This is a best-effort extractor, not a guarantee that every
    possible store layout or dynamically loaded specification is covered.
    """
    import json
    import re
    from collections.abc import Mapping

    from bs4 import BeautifulSoup, Tag

    if not html_text or not html_text.strip():
        return "", None

    soup = BeautifulSoup(html_text, "html.parser")

    # Keep a separate record of JSON-LD before removing script elements.
    # Some product pages put useful specifications here instead of in HTML.
    structured_lines: list[str] = []
    json_descriptions: list[str] = []

    def clean_text(value: Any) -> str:
        """Normalize whitespace while preserving the text itself."""
        if value is None:
            return ""

        if isinstance(value, (dict, list)):
            return ""

        return re.sub(r"\s+", " ", str(value)).strip()

    def add_line(target: list[str], label: Any, value: Any = None) -> None:
        """Add a normalized line, optionally formatted as label: value."""
        key = clean_text(label)
        val = clean_text(value) if value is not None else ""

        if not key and not val:
            return

        if key and val:
            # Avoid producing "Processor: Processor: Core i7".
            if val.casefold().startswith(f"{key}:".casefold()):
                line = val
            else:
                line = f"{key}: {val}"
        else:
            line = key or val

        if len(line) > 1:
            target.append(line)

    def walk_product_json(data: Any) -> None:
        """Extract useful technical properties from Product JSON-LD."""
        if isinstance(data, list):
            for item in data:
                walk_product_json(item)
            return

        if not isinstance(data, Mapping):
            return

        # JSON-LD commonly wraps a product inside @graph.
        if isinstance(data.get("@graph"), list):
            walk_product_json(data["@graph"])

        product_type = data.get("@type", "")
        if isinstance(product_type, list):
            product_types = {str(item).casefold() for item in product_type}
        else:
            product_types = {str(product_type).casefold()}

        # Only extract full product details from Product nodes.
        if "product" not in product_types:
            return

        description = clean_text(data.get("description"))
        if description:
            json_descriptions.append(description)

        # Useful fields from Product JSON-LD.
        for field_name in (
            "name",
            "model",
            "sku",
            "mpn",
            "gtin",
            "category",
            "color",
            "weight",
            "width",
            "height",
            "depth",
            "material",
        ):
            value = data.get(field_name)
            if value is not None and not isinstance(value, (dict, list)):
                add_line(structured_lines, field_name, value)

        # Some products expose their technical specifications here.
        properties = data.get("additionalProperty", [])
        if isinstance(properties, Mapping):
            properties = [properties]

        if isinstance(properties, list):
            for prop in properties:
                if not isinstance(prop, Mapping):
                    continue

                name = prop.get("name") or prop.get("propertyID")
                value = prop.get("value")

                if name and value is not None:
                    add_line(structured_lines, name, value)

        # Preserve useful manufacturer or brand information.
        brand = data.get("brand")
        if isinstance(brand, Mapping):
            brand = brand.get("name")
        if brand:
            add_line(structured_lines, "Brand", brand)

        # A description may be the only place where the page exposes
        # hardware details. Keep it as a separate source.
        if description:
            add_line(structured_lines, "Product description", description)

    for script in soup.select('script[type="application/ld+json"]'):
        raw_json = script.string or script.get_text(strip=True)

        if not raw_json:
            continue

        try:
            walk_product_json(json.loads(raw_json))
        except (json.JSONDecodeError, TypeError, ValueError):
            # Malformed JSON-LD should not prevent HTML extraction.
            continue

    # Metadata sometimes contains product descriptions even when the
    # visible product description is hidden in an accordion.
    metadata_lines: list[str] = []

    for meta in soup.select("meta[name], meta[property]"):
        name = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).strip().casefold()

        content = clean_text(meta.get("content"))
        if not content:
            continue

        if name in {
            "og:description",
            "description",
            "product:description",
            "twitter:description",
        }:
            add_line(metadata_lines, "Meta description", content)

    # Remove elements that generally do not contain product specifications.
    # Do this only after collecting JSON-LD and metadata.
    junk_selectors = [
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "nav",
        "header",
        "footer",
        "form",
        "button",
        "input",
        "select",
        "textarea",
        "[hidden]",
        '[aria-hidden="true"]',
        ".announcement-bar",
        "#shopify-section-announcement-bar",
        ".shopify-section-header",
        "#shopify-section-header",
        "#shopify-section-footer",
        ".popup",
        ".modal",
        ".cart-drawer",
        ".product-recommendations",
        ".related-products",
        ".recently-viewed",
        ".reviews",
        ".review-widget",
        ".social-sharing",
        ".breadcrumb",
        ".breadcrumbs",
        ".cookie-banner",
        ".cookie-consent",
    ]

    for element in soup.select(", ".join(junk_selectors)):
        element.decompose()

    technical_lines: list[str] = []
    description_lines: list[str] = []

    # Match likely specification-related CSS classes and attributes.
    # This deliberately does not depend on one store's class names.
    spec_pattern = re.compile(
        r"spec|technical|attribute|product.?detail|"
        r"feature|property|parameter|characteristic|"
        r"product.?info|description|accordion|disclosure",
        re.IGNORECASE,
    )

    label_pattern = re.compile(
        r"^(?:"
        r"brand|model|series|sku|mpn|part number|"
        r"processor|cpu|cores|threads|cache|frequency|"
        r"ram|memory|storage|ssd|hdd|hard drive|"
        r"graphics|gpu|video card|display|screen|"
        r"resolution|refresh rate|battery|power adapter|"
        r"operating system|os|ports|wireless|wi.?fi|"
        r"bluetooth|camera|audio|keyboard|weight|"
        r"dimensions|warranty|certifications|"
        r"connectivity|panel type|brightness|"
        r"color gamut|touchscreen|memory slots|"
        r"storage slots|graphics memory|"
        r"maximum graphics power|"
        r"processor model|processor generation|"
        r"screen size|battery capacity"
        r")\s*:?\s*$",
        re.IGNORECASE,
    )

    def element_text(element: Tag) -> str:
        return clean_text(element.get_text(" ", strip=True))

    def add_description_block(element: Tag) -> None:
        """Collect readable lines from a likely product content section."""
        for line in element.get_text("\n", strip=True).splitlines():
            line = clean_text(line)
            if len(line) < 2:
                continue

            # Remove obvious store-specific marketing noise.
            lowered = line.casefold()
            if any(
                phrase in lowered
                for phrase in (
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
                )
            ):
                continue

            description_lines.append(line)

    # 1. Extract every table, not just tables inside known spec containers.
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [
                element_text(cell)
                for cell in row.find_all(["th", "td"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]

            if len(cells) >= 2:
                # Keep all columns, since some specification tables have
                # multiple values or model comparisons in the same row.
                add_line(
                    technical_lines,
                    cells[0],
                    " | ".join(cells[1:]),
                )
            elif len(cells) == 1:
                add_line(technical_lines, cells[0])

    # 2. Extract definition lists such as:
    # <dl><dt>Processor</dt><dd>Core i7...</dd></dl>
    for definition_list in soup.find_all("dl"):
        current_term = None

        for child in definition_list.find_all(
            ["dt", "dd"],
            recursive=False,
        ):
            value = element_text(child)
            if not value:
                continue

            if child.name == "dt":
                current_term = value
            elif current_term:
                add_line(technical_lines, current_term, value)
                current_term = None
            else:
                add_line(technical_lines, value)

    # 3. Extract common label/value pairs.
    # Examples:
    # <div><span>Processor</span><span>Core i7...</span></div>
    # <div><strong>RAM:</strong><span>16GB DDR5</span></div>
    # <div class="spec-row"><div>Storage</div><div>1TB SSD</div></div>
    pair_selectors = [
        "[itemprop]",
        "[data-spec]",
        "[data-attribute]",
        "[data-label]",
        "[data-value]",
        "[class*='spec-row']",
        "[class*='specification-row']",
        "[class*='attribute-row']",
        "[class*='product-detail-row']",
        "[class*='feature-row']",
        "[class*='spec-item']",
        "[class*='specification-item']",
        "[class*='attribute-item']",
        "[class*='product-detail-item']",
        "[class*='specification']",
        "[class*='specifications']",
        "[class*='product-attribute']",
        "[class*='product-property']",
    ]

    seen_pair_nodes: set[int] = set()

    for selector in pair_selectors:
        for element in soup.select(selector):
            if id(element) in seen_pair_nodes:
                continue
            seen_pair_nodes.add(id(element))

            # Extract explicit data attributes first. These often preserve
            # a key/value relationship even when visible labels are absent.
            data_label = (
                element.get("data-spec")
                or element.get("data-attribute")
                or element.get("data-label")
                or element.get("itemprop")
            )
            data_value = element.get("data-value")

            if data_label and data_value:
                add_line(technical_lines, data_label, data_value)
                continue

            # Don't treat a large container containing many specs as one pair.
            children = [
                child
                for child in element.find_all(
                    ["div", "span", "p", "li", "strong", "b", "dt", "dd"],
                    recursive=False,
                )
                if element_text(child)
            ]

            # For deeper wrappers, inspect immediate meaningful descendants.
            if len(children) < 2:
                children = [
                    child
                    for child in element.find_all(
                        ["div", "span", "p", "li", "strong", "b", "dt", "dd"],
                    )
                    if element_text(child)
                    and not any(
                        ancestor is not element
                        and ancestor in child.parents
                        and ancestor.name in {"table", "dl"}
                        for ancestor in []
                    )
                ]

                # Keep only the shallowest text-bearing candidates to avoid
                # emitting every nested span as a separate specification.
                shallow_children = []
                for child in children:
                    if not any(
                        parent in children
                        for parent in child.parents
                        if parent is not element
                    ):
                        shallow_children.append(child)

                if len(shallow_children) >= 2:
                    children = shallow_children

            if len(children) >= 2:
                label = element_text(children[0])
                value = element_text(children[1])

                if (
                    label
                    and value
                    and len(label) <= 100
                    and len(value) <= 500
                    and (
                        label_pattern.match(label.rstrip(":"))
                        or spec_pattern.search(" ".join(element.get("class", [])))
                        or element.get("data-spec")
                        or element.get("data-attribute")
                    )
                ):
                    add_line(technical_lines, label.rstrip(":"), value)

    # 4. Extract list-based specifications, including simple "Label: Value"
    # entries and two-part list items.
    for item in soup.find_all("li"):
        # Ignore list items that contain nested lists; those often represent
        # navigation or category menus rather than one specification.
        if item.find("ul") or item.find("ol"):
            continue

        text = element_text(item)
        if not text or len(text) > 700:
            continue

        if ":" in text:
            label, value = text.split(":", 1)
            label = clean_text(label)
            value = clean_text(value)

            if (
                label
                and value
                and len(label) <= 100
                and label_pattern.match(label)
            ):
                add_line(technical_lines, label, value)
                continue

        direct_children = [
            child
            for child in item.find_all(
                ["span", "strong", "b", "div"],
                recursive=False,
            )
            if element_text(child)
        ]

        if len(direct_children) >= 2:
            label = element_text(direct_children[0])
            value = element_text(direct_children[1])

            if (
                label_pattern.match(label.rstrip(":"))
                or spec_pattern.search(" ".join(item.get("class", [])))
            ):
                add_line(technical_lines, label.rstrip(":"), value)

    # 5. Collect likely product description/specification containers.
    # Known Compumarts selectors remain supported, but are no longer the
    # only containers we inspect.
    content_selectors = [
        ".pdesc-wrap",
        ".dark-spec-wrapper",
        ".disclosure__content.product-description",
        ".product-description",
        ".product-details__block",
        "[itemprop='description']",
        "#description",
        "#product-description",
        "#specifications",
        "#technical-specifications",
        ".description",
        ".product-description-content",
        ".product-details",
        ".product-specifications",
        ".technical-specifications",
        ".product__description",
        ".product__accordion",
        ".accordion",
        "details",
    ]

    seen_description_nodes: set[int] = set()

    for selector in content_selectors:
        for container in soup.select(selector):
            if id(container) in seen_description_nodes:
                continue
            seen_description_nodes.add(id(container))

            # Avoid copying the entire product page into the description.
            text = element_text(container)
            if len(text) > 20000:
                continue

            add_description_block(container)

    # 6. Also inspect a product-specific region when available.
    # This helps when a store uses an unfamiliar class for its specifications.
    product_root = soup.select_one(
        "[itemtype*='Product'], "
        ".product__info-container, "
        ".product-single, "
        ".product-detail, "
        ".product-page, "
        "main#MainContent, "
        "main"
    )

    if product_root:
        # Extract remaining simple "Label: Value" lines from the product area.
        # This supplements structured extraction rather than replacing it.
        for line in product_root.get_text("\n", strip=True).splitlines():
            line = clean_text(line)

            if not line or len(line) > 700 or ":" not in line:
                continue

            label, value = line.split(":", 1)
            label = clean_text(label)
            value = clean_text(value)

            if (
                label
                and value
                and len(label) <= 100
                and label_pattern.match(label)
            ):
                add_line(technical_lines, label, value)

    # 7. Merge sources prioritizing technical table specifications first:
    all_lines = (
        technical_lines
        + structured_lines
        + metadata_lines
        + description_lines
    )

    # Deduplicate exact repeated lines, preserving first-seen order.
    # Don't deduplicate by value alone: "RAM: 16GB" and "Storage: 16GB"
    # are different facts and must both survive.
    seen_lines: set[str] = set()
    unique_lines: list[str] = []

    for line in all_lines:
        normalized = re.sub(r"\s+", " ", line).strip().casefold()

        if normalized and normalized not in seen_lines:
            seen_lines.add(normalized)
            unique_lines.append(line)

    # Include JSON-LD descriptions as useful fallback text if the HTML
    # description container was empty or missing.
    if not description_lines and json_descriptions:
        for description in json_descriptions:
            if description.casefold() not in seen_lines:
                unique_lines.append(f"Product description: {description}")
                seen_lines.add(description.casefold())

    technical_text = "\n".join(unique_lines)

    # Return a readable description for the existing metadata pipeline.
    raw_lines = description_lines or json_descriptions
    raw_description = "\n".join(raw_lines[:100]) if raw_lines else None

    return technical_text, raw_description


class LocalLLMCompumartsScraper(CompumartsStoreScraper):
    """Production CompuMarts Scraper powered by Scrapling and Local Model Extraction."""

    def __init__(self, scraper_only: bool = False):
        super().__init__(engine=ScraplingEngine())
        self.scraper_only = scraper_only
        self.extractor = LocalModelExtractor()

    def extract_scraper_specs(self, product_url: str, title: str = "") -> CompumartsSpecResult:
        """Fetch CompuMarts PDP and return ONLY the raw scraper specifications table without calling the LLM."""
        html_text = self._fetch_html(product_url)
        if not html_text:
            empty_res = SpecExtractionResult(
                has_text_specs=False,
                specs_extraction_source="none",
                specs_fallback_reason="Failed to fetch PDP HTML",
            )
            return CompumartsSpecResult({}, None, None, None, None, None, empty_res)

        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Parse Schema.org Product JSON-LD for SKU, Price, Availability
        sku: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        in_stock: bool | None = None
        json_desc: str | None = None

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, list):
                    data = data[0]
                if isinstance(data, dict) and data.get("@type") == "Product":
                    sku = data.get("sku") or data.get("mpn")
                    offers = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    if isinstance(offers, dict):
                        raw_p = offers.get("price")
                        if raw_p:
                            price_val, price_str = self.parse_egp_price(str(raw_p))
                        avail = offers.get("availability", "")
                        if "InStock" in avail:
                            in_stock = True
                        elif "OutOfStock" in avail:
                            in_stock = False
                    json_desc = data.get("description")
                    break
            except Exception:
                pass

        if in_stock is None:
            sold_out_elem = soup.select_one(".product-label--sold-out, .sold-out, [data-sold-out]")
            in_stock = not (sold_out_elem or "sold out" in soup.get_text().lower())

        # 2. Extract ALL raw specification table rows directly from PDP HTML
        raw_table = extract_raw_spec_table(html_text)

        # Also collect clean raw description
        _, raw_desc = extract_all_technical_data(html_text)

        spec_res = SpecExtractionResult(
            specs=raw_table,
            raw_description=(raw_desc or json_desc)[:1500] if (raw_desc or json_desc) else None,
            has_text_specs=bool(raw_table),
            specs_extraction_source="scraper_raw_table",
            specs_fallback_reason=None if raw_table else "No specification table found in PDP",
            price_val=price_val,
            price_str=price_str,
            sku=sku,
            in_stock=in_stock,
        )

        return CompumartsSpecResult(
            raw_table,
            raw_desc or json_desc,
            price_val,
            price_str,
            sku,
            in_stock,
            spec_res,
        )

    def _extract_product_specs(self, product_url: str, title: str = "") -> CompumartsSpecResult:
        """Fetch CompuMarts PDP, extract ALL technical data, and optionally feed it to the Local Model."""
        if self.scraper_only:
            return self.extract_scraper_specs(product_url, title=title)

        html_text = self._fetch_html(product_url)
        if not html_text:
            empty_res = SpecExtractionResult(
                has_text_specs=False,
                specs_extraction_source="none",
                specs_fallback_reason="Failed to fetch PDP HTML",
            )
            return CompumartsSpecResult({}, None, None, None, None, None, empty_res)

        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Parse Schema.org Product JSON-LD for SKU, Price, Availability
        sku: str | None = None
        price_val: float | None = None
        price_str: str | None = None
        in_stock: bool | None = None
        json_desc: str | None = None

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, list):
                    data = data[0]
                if isinstance(data, dict) and data.get("@type") == "Product":
                    sku = data.get("sku") or data.get("mpn")
                    offers = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    if isinstance(offers, dict):
                        raw_p = offers.get("price")
                        if raw_p:
                            price_val, price_str = self.parse_egp_price(str(raw_p))
                        avail = offers.get("availability", "")
                        if "InStock" in avail:
                            in_stock = True
                        elif "OutOfStock" in avail:
                            in_stock = False
                    json_desc = data.get("description")
                    break
            except Exception:
                pass

        if in_stock is None:
            sold_out_elem = soup.select_one(".product-label--sold-out, .sold-out, [data-sold-out]")
            in_stock = not (sold_out_elem or "sold out" in soup.get_text().lower())

        # 2. Extract ALL raw specification table rows (without dropping anything)
        raw_table = extract_raw_spec_table(html_text)

        # Also get any raw descriptions from the page
        _, raw_desc = extract_all_technical_data(html_text)

        # 3. Format prompt with the clean specifications table right at the top
        prompt_content = format_table_for_prompt(raw_table, title=title, extra_context=raw_desc or "")

        # 4. Extract structured specifications with the Local Model
        extracted_specs, latency, err = self.extractor.extract(prompt_content)

        # 5. Reconcile model output with raw table to ensure zero fields are dropped
        specs_dict = reconcile_specs(extracted_specs, raw_table)

        spec_res = SpecExtractionResult(
            specs=specs_dict,
            raw_description=(raw_desc or json_desc or prompt_content)[:1500] if (raw_desc or json_desc or prompt_content) else None,
            has_text_specs=bool(specs_dict),
            specs_extraction_source="hybrid_table_llm" if extracted_specs else "deterministic_table",
            specs_fallback_reason=None if specs_dict else err,
            price_val=price_val,
            price_str=price_str,
            sku=sku,
            in_stock=in_stock,
        )

        return CompumartsSpecResult(
            specs_dict,
            raw_desc or json_desc,
            price_val,
            price_str,
            sku,
            in_stock,
            spec_res,
        )


def main():
    parser = argparse.ArgumentParser(description="Full Level 1 and 2 CompuMarts Scraper with Scrapling & Local LLM")
    parser.add_argument("--level", type=int, choices=[1, 2], default=2, help="Scraping Level (1: Catalog summary, 2: Deep PDP)")
    parser.add_argument("--scraper-only", action="store_true", help="Return ONLY raw scraper results directly from PDP tables (no LLM call)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of laptops to scrape (omit for full catalog)")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of category pages to crawl")
    parser.add_argument("--output", type=str, default=None, help="Custom output JSON filename")
    args = parser.parse_args()

    mode_label = "PURE SCRAPER ONLY (NO LLM)" if args.scraper_only else "ALL TECHNICAL DATA + LOCAL LLM"
    print("=" * 80)
    print(f"🚀 COMPUMARTS PIPELINE ({mode_label}) - LEVEL {args.level}")
    print(f"   Limit: {args.limit or 'All Laptops'} | Max Pages: {args.max_pages or 'All Pages'}")
    print("=" * 80)

    scraper = LocalLLMCompumartsScraper(scraper_only=args.scraper_only)

    if args.level == 2 and not args.scraper_only:
        health = scraper.extractor.check_health()
        if health.get("status") != "ok":
            print(f"❌ Local LLM is offline at {scraper.extractor.base_url}.")
            print("   Please ensure Ollama is running, or use --scraper-only to skip the LLM.")
            return
        print(f"✅ Local LLM Online: {health.get('backend')} ({health.get('models')})\n")

    start_time = time.perf_counter()
    products = scraper.scrape_catalog(
        level=args.level,
        max_pages=args.max_pages,
        limit=args.limit,
    )
    duration = time.perf_counter() - start_time

    if args.output:
        output_filename = args.output
    elif args.scraper_only:
        output_filename = "compumarts_scraper_results.json"
    else:
        output_filename = f"compumarts_level{args.level}_results.json"

    output_path = os.path.join(os.path.dirname(__file__), output_filename)

    serializable = [p.model_dump() for p in products]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 LEVEL {args.level} COMPLETE: Ingested {len(products)} products in {duration:.1f}s")
    print(f"   Output saved to: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
