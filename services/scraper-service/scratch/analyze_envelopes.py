import json
from collections import Counter
from app.stores.compumarts import CompumartsStoreScraper
from pipeline.orchestrator import LaptopExtractionPipeline, RawScrapedProduct
from pipeline.ai_fallback.gliner_onnx import GLiNERONNXFallbackExtractor

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

# Find items where rejections_count > 0 or envelopes_count > 0
rejected_items = [it for it in items if it.get("rejections_count", 0) > 0]
print(f"Items with Gate 2 rejections: {len(rejected_items)}")

# Let's see which fields generated envelopes across all 130 laptops
# We can re-run pipeline.deterministic on the raw table of each item
from pipeline.deterministic import DeterministicExtractor
from pipeline.sanitizer import TextSanitizer

det = DeterministicExtractor()
sanitizer = TextSanitizer()

field_envelope_counts = Counter()
rejection_reasons = Counter()

# Let's inspect 5 laptops with rejections to see exact rejections
pipeline = LaptopExtractionPipeline(ai_fallback=GLiNERONNXFallbackExtractor(lazy_load=False))

rejection_details = []
for it in rejected_items[:5]:
    # We can fetch or reconstruct raw product
    raw_prod = RawScrapedProduct(
        url=it["url"],
        store="compumarts",
        title=it["title"],
        raw_html="",
        raw_tables={},  # Let's see if we have raw tables or need to fetch
    )

print("Sample rejected laptop URLs:")
for it in rejected_items[:5]:
    print(" -", it["title"][:60], "-> Rejections:", it["rejections_count"])

