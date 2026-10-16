import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import re
from pipeline.deterministic import DeterministicExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.sanitizer import TextSanitizer

data = json.load(open("pipeline_results_compumarts.json", encoding="utf-8"))
san = TextSanitizer()
ext = DeterministicExtractor()
cpu_ext = CPUAnchorExtractor()

for idx in [0, 3, 4, 5, 6, 7, 8, 9, 14, 18, 19, 22, 24, 27, 28, 47, 69, 70, 71, 78]:
    d = data[idx]
    title = san.clean_text(d["title"])
    table = san.sanitize_table(d.get("source_table", {}))
    sections = {}
    spec_text_snippets = list(table.values())
    cpu_specs, cpu_context, cpu_key = cpu_ext.extract(title=title, spec_texts=spec_text_snippets)
    specs, _ = ext.extract(title=title, sanitized_table=table, sanitized_sections=sections, cpu_context=cpu_context)
    if cpu_specs:
        raw_cpu = specs.get("cpu", {}).get("raw_spec")
        specs["cpu"] = dict(cpu_specs)
        if raw_cpu:
            specs["cpu"]["raw_spec"] = raw_cpu
            m_cache = re.search(r"\b(\d+)\s*MB\s*Cache\b|Cache:\s*(\d+)\s*MB\b", raw_cpu, re.IGNORECASE)
            if m_cache:
                specs["cpu"]["cache_mb"] = int(m_cache.group(1) or m_cache.group(2))
            m_boost = re.search(r"\b(?:up\s+to|max\s+boost\s+clock|turbo\s+boost\s+up\s+to|boost\s+clock)\s*:?\s*(\d+(?:\.\d+)?)\s*GHz\b", raw_cpu, re.IGNORECASE)
            if m_boost:
                b_ghz = float(m_boost.group(1))
                specs["cpu"]["clock_boost_ghz"] = b_ghz
                if isinstance(specs["cpu"].get("performance_cores"), dict) and specs["cpu"]["performance_cores"] is not None:
                    specs["cpu"]["performance_cores"]["boost_clock_ghz"] = b_ghz

    print(f"[{idx}] model: {specs.get('identity', {}).get('laptop_model')} | mpn: {specs.get('identity', {}).get('manufacturer_part_number')} | webcam: {specs.get('audio_webcam', {}).get('webcam_resolution')} | weight: {specs.get('physical', {}).get('weight_kg')} | cpu: {specs.get('cpu', {}).get('full_name')} (boost: {specs.get('cpu', {}).get('clock_boost_ghz')}, cache: {specs.get('cpu', {}).get('cache_mb')}) | ram: {specs.get('memory', {}).get('capacity_gb')}GB | os: {specs.get('operating_system', {}).get('name')}")
