import json
from collections import Counter

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

print(f"Total laptops in output: {len(items)}")

# 1. Missing CPU
missing_cpu = [x for x in items if not x.get("cpu_key")]
print(f"\n=== 1. Missing CPU ({len(missing_cpu)}) ===")
for m in missing_cpu:
    print(f"Title: {m.get('title')}")
    print(f"URL: {m.get('url')}")

# 2. Check checkpoint file for envelopes and rejections details
ckpt_file = "pipeline_results_compumarts.checkpoint.jsonl"
print("\n=== 2. Checkpoint Details ===")
envelopes_by_laptop = []
for it in items:
    env_cnt = it.get("envelopes_count", 0)
    rej_cnt = it.get("rejections_count", 0)
    if env_cnt > 0:
        envelopes_by_laptop.append((it["title"][:50], env_cnt, rej_cnt))

print(f"Laptops that generated at least 1 envelope: {len(envelopes_by_laptop)} / {len(items)}")
print(f"Sample laptops with envelopes: {envelopes_by_laptop[:5]}")

