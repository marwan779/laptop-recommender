import json
import os
import sys
from pprint import pprint

sys.stdout.reconfigure(encoding="utf-8")


p_raw = os.path.expanduser("~/Downloads/compumarts_laptop_specs_raw.json")
p_dict = os.path.expanduser("~/Downloads/compumarts_laptop_spec_alias_dictionary.json")

print("="*80)
print("1. AUDITING compumarts_laptop_specs_raw.json")
print("="*80)

with open(p_raw, "r", encoding="utf-8") as f:
    raw = json.load(f)

for k in ["source", "crawl_rule", "collection_pages", "listed_unique_pdp_count", "fetched_pdp_count", "failed_pdp_count", "total_spec_rows"]:
    print(f"  {k}: {raw.get(k)}")

products = raw.get("products", [])
print(f"  Total products in raw dump: {len(products)}")

if products:
    p0 = products[0]
    print(f"\n  Sample Product [0]:")
    print(f"    URL:   {p0.get('url')}")
    print(f"    Title: {p0.get('title')}")
    print(f"    Price: {p0.get('price')}")
    specs = p0.get("specifications", p0.get("specs", {}))
    print(f"    Total spec rows: {len(specs)}")
    print("    First 10 spec key-value pairs:")
    for i, (k, v) in enumerate(list(specs.items())[:10]):
        print(f"      [{k}]: {str(v)[:60]}")

labels = raw.get("observed_spec_label_counts", {})
print(f"\n  Total unique observed spec labels: {len(labels)}")
top_labels = sorted(labels.items(), key=lambda x: x[1], reverse=True)[:25]
print("  Top 25 most frequent spec labels:")
for k, count in top_labels:
    print(f"    {k:30}: {count} occurrences")

print("\n" + "="*80)
print("2. AUDITING compumarts_laptop_spec_alias_dictionary.json")
print("="*80)

with open(p_dict, "r", encoding="utf-8") as f:
    alias = json.load(f)

for k in ["title", "generated_at_utc", "source_collection", "crawl_scope"]:
    print(f"  {k}: {alias.get(k)}")

canon = alias.get("canonical_fields", {})
print(f"\n  Total canonical fields mapped: {len(canon)}")
print("  Canonical fields list:")
for cf, details in list(canon.items()):
    aliases = details.get("aliases", details.get("observed_aliases", []))
    desc = details.get("description", "")
    print(f"    - {cf:30} (aliases count: {len(aliases)}) -> desc: {desc[:50]}")

obs_labels = alias.get("observed_labels", {})
print(f"\n  Total observed labels classified: {len(obs_labels)}")
print("  Sample observed label mappings (first 10):")
for ol, mapping in list(obs_labels.items())[:10]:
    target_cf = mapping.get("canonical_field") or mapping.get("maps_to")
    role = mapping.get("role") or mapping.get("category")
    print(f"    [{ol}] -> {target_cf} ({role})")

cov = alias.get("product_coverage", {})
print(f"\n  Product coverage entries: {len(cov)}")

unparsed = alias.get("unparsed_source_lines", [])
print(f"  Unparsed source lines: {len(unparsed)}")
