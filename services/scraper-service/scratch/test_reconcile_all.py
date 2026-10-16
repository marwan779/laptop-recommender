import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import copy
import re

from pipeline.deterministic import DeterministicExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.sanitizer import TextSanitizer

with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    items = json.load(f)

san = TextSanitizer()
ext = DeterministicExtractor()
cpu_ext = CPUAnchorExtractor()

updated_items = copy.deepcopy(items)

for idx, item in enumerate(updated_items):
    title = san.clean_text(item["title"])
    table = san.sanitize_table(item.get("source_table", {}))
    
    # Preserve SKU and Part Number from raw spec if present
    id_raw = item.get("specs", {}).get("identity", {}).get("raw_spec", "")
    m_pn = re.search(r"\bPart Number:\s*([^|]+)", id_raw)
    if m_pn and "Part Number" not in table:
        table["Part Number"] = m_pn.group(1).strip()
    m_sku = re.search(r"\bSKU:\s*([^|]+)", id_raw)
    if m_sku and "SKU" not in table:
        table["SKU"] = m_sku.group(1).strip()

    # CPU Anchor extraction
    spec_text_snippets = list(table.values())
    cpu_specs, cpu_context, cpu_key = cpu_ext.extract(title=title, spec_texts=spec_text_snippets)
    
    # Deterministic extraction
    specs, _ = ext.extract(title=title, sanitized_table=table, sanitized_sections={}, cpu_context=cpu_context)
    
    # Merge CPU anchor specs + align with raw_spec if declared
    if cpu_specs:
        raw_cpu = specs.get("cpu", {}).get("raw_spec")
        specs["cpu"] = copy.deepcopy(cpu_specs)
        if raw_cpu:
            specs["cpu"]["raw_spec"] = raw_cpu
            m_cache = re.search(r"\b(\d+)\s*MB\s*Cache\b|Cache:\s*(\d+)\s*MB\b", raw_cpu, re.IGNORECASE)
            if m_cache:
                specs["cpu"]["cache_mb"] = int(m_cache.group(1) or m_cache.group(2))
            m_boost = re.search(
                r"\b(?:up\s+to|max\s+boost\s+clock|turbo\s+boost\s+up\s+to|boost\s+clock)\s*:?\s*(\d+(?:\.\d+)?)\s*GHz\b",
                raw_cpu,
                re.IGNORECASE,
            )
            if m_boost:
                b_ghz = float(m_boost.group(1))
                specs["cpu"]["clock_boost_ghz"] = b_ghz
                if isinstance(specs["cpu"].get("performance_cores"), dict) and specs["cpu"]["performance_cores"] is not None:
                    specs["cpu"]["performance_cores"]["boost_clock_ghz"] = b_ghz
    
    # Keep existing raw_specs for each group so that provenance is 100% maintained
    for group_name, group_data in item.get("specs", {}).items():
        if isinstance(group_data, dict) and "raw_spec" in group_data:
            if group_name in specs and isinstance(specs[group_name], dict):
                specs[group_name]["raw_spec"] = group_data["raw_spec"]
    
    item["specs"] = specs
    if cpu_key:
        item["cpu_key"] = cpu_key

# Now run verification of the 71 contradictions on updated_items:
from scratch.verify_71_contradictions import CHECKS

detected = 0
for idx, field, test_fn, desc in CHECKS:
    rec = updated_items[idx]
    specs = rec.get("specs", {})
    if test_fn(specs, specs):
        detected += 1
        print(f"FAILED: [{idx}] {field}: {desc}")

print(f"\nRemaining Contradictions: {detected} / {len(CHECKS)}")

