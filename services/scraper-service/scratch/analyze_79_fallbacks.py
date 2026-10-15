import json
import sys
sys.path.insert(0, ".")
from collections import Counter

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

print(f"Total laptops: {len(items)}")

# 1. Inspect the 3 Gate 2 rejections
rejected_items = [it for it in items if it.get("rejections_count", 0) > 0]
print(f"\n=== Laptops with Gate 2 Rejections ({len(rejected_items)}) ===")
for it in rejected_items:
    print(f"URL: {it['url']}")
    print(f"Title: {it['title']}")
    print(f"Rejections count: {it.get('rejections_count')}")

# 2. Inspect the 79 envelopes:
# Let's see: which laptops had envelopes_count > 0?
items_with_envelopes = [it for it in items if it.get("envelopes_count", 0) > 0]
print(f"\n=== Laptops with Envelopes ({len(items_with_envelopes)}) ===")
print(f"Total envelopes across items: {sum(it.get('envelopes_count', 0) for it in items)}")

# Let's inspect the checkpoint file to see if we can get exact details or re-run
# Actually, let's write a small script that re-runs the pipeline on the 3 rejected items to print their exact rejection records!
from app.stores.compumarts import CompumartsStoreScraper
from pipeline.orchestrator import LaptopExtractionPipeline
from pipeline.ai_fallback.gliner_onnx import GLiNERONNXFallbackExtractor

pipeline = LaptopExtractionPipeline(ai_fallback=GLiNERONNXFallbackExtractor(lazy_load=False))

print("\n--- Detailed Inspection of the 3 Rejections ---")
for it in rejected_items:
    res = pipeline.extract_from_url(it["url"])
    print(f"\nLaptop: {it['title'][:60]}")
    print("Rejections:")
    for rej in res.validation_rejections:
        print(" ", rej)
    print("Envelopes:")
    for env in res.envelopes_generated:
        print(" ", env.field_path, "-> reason:", env.failure_reason)
    print("AI Results:")
    for ai in res.ai_results:
        print(" ", ai.field_path, "-> extracted:", ai.extracted_value, f"(raw_span='{ai.raw_span}')")

