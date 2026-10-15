import json
import sys
sys.path.insert(0, ".")
from collections import Counter

# Let's inspect all items in pipeline_results_compumarts.json and re-run on all 130 items using our pipeline
# to get the exact aggregate breakdown of envelopes and rejections!
from app.stores.compumarts import CompumartsStoreScraper
from pipeline.orchestrator import LaptopExtractionPipeline, RawScrapedProduct
from pipeline.deterministic import DeterministicExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

print(f"Total laptops: {len(items)}")

# We can analyze the fields that are None vs populated in items:
unpopulated_fields = Counter()
for it in items:
    specs = it.get("specs", {})
    for cat, cat_dict in specs.items():
        if isinstance(cat_dict, dict):
            for k, v in cat_dict.items():
                if v is None:
                    unpopulated_fields[f"{cat}.{k}"] += 1

print("\n=== Most common unpopulated fields in final output ===")
for k, cnt in unpopulated_fields.most_common(12):
    print(f"  {k:35s}: {cnt} / {len(items)}")
