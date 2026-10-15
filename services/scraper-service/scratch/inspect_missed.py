import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import re

with open('scratch/egyptian_market_cpus.json', 'r', encoding='utf-8') as f:
    extracted_cpus = json.load(f)['cpus']

from scratch.extract_market_cpus import store_files, extract_cpu_from_text

missed = []
for sf in store_files:
    try:
        with open(sf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        items = data.get('products', []) if isinstance(data, dict) else data
        for item in items:
            title = item.get('title') or item.get('name') or ''
            specs = item.get('specs') or {}
            raw = specs.get('Processor') or specs.get('CPU') or specs.get('processor') or specs.get('cpu') or ''
            cpu = extract_cpu_from_text(str(raw)) or extract_cpu_from_text(title)
            if not cpu:
                missed.append({'file': sf, 'title': title, 'raw': str(raw)})
    except Exception as e:
        pass

print(f"Total unextracted items: {len(missed)}")
# Group by title prefix or inspect
for m in missed[:25]:
    print(f"Store: {m['file']} | Title: {m['title'][:60]} | Raw: {m['raw'][:60]}")
