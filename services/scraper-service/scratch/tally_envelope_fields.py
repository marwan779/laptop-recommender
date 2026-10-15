import json
import sys
sys.path.insert(0, ".")
from collections import Counter
from app.stores.compumarts import CompumartsStoreScraper
from pipeline.orchestrator import LaptopExtractionPipeline, RawScrapedProduct
from pipeline.deterministic import DeterministicExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor

scraper = CompumartsStoreScraper()
products = scraper.scrape_catalog(level=2)

pipeline = LaptopExtractionPipeline()
env_counter = Counter()
rejection_counter = Counter()

for prod in products:
    raw_prod = RawScrapedProduct(
        url=prod.product_url,
        store="compumarts",
        title=prod.title,
        raw_html="",
        raw_tables={"specs": prod.specs or {}},
        raw_sections={"Description": prod.raw_description or ""},
        price=prod.price_egp,
    )
    # Run deterministic + CPU anchor
    sanitized_title = pipeline.sanitizer.clean_text(raw_prod.title)
    sanitized_table = pipeline.sanitizer.sanitize_table(raw_prod.raw_tables.get("specs", {}))
    sanitized_sections = pipeline.sanitizer.sanitize_sections(raw_prod.raw_sections)

    spec_text_snippets = list(sanitized_table.values()) + list(sanitized_sections.values())
    cpu_specs, cpu_context, cpu_key = pipeline.cpu_anchor.extract(
        title=sanitized_title,
        spec_texts=spec_text_snippets,
    )

    specs, envelopes = pipeline.deterministic.extract(
        title=sanitized_title,
        sanitized_table=sanitized_table,
        sanitized_sections=sanitized_sections,
        cpu_context=cpu_context,
    )

    for env in envelopes:
        env_counter[env.field_path] += 1

print("\n=== Exact Breakdown of the 79 Envelopes ===")
for field_path, cnt in env_counter.most_common():
    print(f"  {field_path:35s}: {cnt}")
print(f"Total Envelopes: {sum(env_counter.values())}")

