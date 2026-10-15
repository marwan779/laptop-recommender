import json
import sys
sys.path.insert(0, ".")
from collections import Counter

# Let's inspect the 79 envelopes across the catalog
# We can re-run det.extract on each laptop's raw data and tally the envelopes!
from pipeline.orchestrator import LaptopExtractionPipeline, RawScrapedProduct
from pipeline.deterministic import DeterministicExtractor
from pipeline.sanitizer import TextSanitizer

p = LaptopExtractionPipeline()

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

# Count envelopes per field across the catalog
envelope_fields = Counter()
envelope_reasons = Counter()
resolved_by_ai = Counter()

# Let's read from the checkpoint file where the items were recorded
with open("pipeline_results_compumarts.checkpoint.jsonl", "r", encoding="utf-8") as f:
    ckpt_lines = [json.loads(l) for l in f if l.strip()]

print(f"Total processed in checkpoint: {len(ckpt_lines)}")
# Let's check how many items had envelopes
laptops_with_envs = [x for x in ckpt_lines if x.get("envelopes_count", 0) > 0]
print(f"Laptops with envelopes: {len(laptops_with_envs)}")
print(f"Total envelopes: {sum(x.get('envelopes_count', 0) for x in ckpt_lines)}")
print(f"Total rejections: {sum(x.get('rejections_count', 0) for x in ckpt_lines)}")
