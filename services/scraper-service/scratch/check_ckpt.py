import json
import sys
sys.path.insert(0, ".")
from collections import Counter
from pipeline.deterministic import DeterministicExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.sanitizer import TextSanitizer

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

det = DeterministicExtractor()
cpu_anchor = CPUAnchorExtractor()
sanitizer = TextSanitizer()

env_fields = Counter()
env_reasons = Counter()

# We can see what envelopes were created for each laptop
for it in items:
    # Look at the fields in specs:
    pass

print("Checkpoint lines count:")
with open("pipeline_results_compumarts.checkpoint.jsonl", "r", encoding="utf-8") as f:
    lines = [json.loads(l) for l in f if l.strip()]
print(f"Total checkpoint items: {len(lines)}")

# Let's count envelopes_count per item
env_counts = Counter([x.get("envelopes_count", 0) for x in lines])
print("Distribution of envelopes per laptop:", env_counts)
rej_counts = Counter([x.get("rejections_count", 0) for x in lines])
print("Distribution of rejections per laptop:", rej_counts)

