import os
import sys
import json
import re
from collections import Counter

store_files = [
    'scraping-results/stores/store_compumarts.json',
    'scraping-results/stores/store_sigma.json',
    'scraping-results/stores/store_elbadr.json',
    'scraping-results/stores/store_twob.json',
    'scraping-results/stores/store_tradeline.json',
    'store_btech.json',
    'store_amazon.json',
    'store_noon.json',
    'gliner_extractor/hybrid_results.json',
    'nuextract_sandbox/output/compumarts_all_laptops_nuextract.json',
]

def clean_text(s):
    if not s:
        return ""
    # remove special trademark / copyright symbols and multiple spaces
    s = re.sub(r'[™®]', ' ', str(s))
    return re.sub(r'\s+', ' ', s).strip()

def extract_cpu_from_text(raw_text):
    text = clean_text(raw_text)
    if not text:
        return None

    # 1. Apple Silicon: M1, M1 Pro, M1 Max, M2, M2 Pro, M2 Max, M3, M3 Pro, M3 Max, M4, M4 Pro, M4 Max, M5, etc.
    m = re.search(r'\bApple\s+(M[1-5](?:\s+(?:Pro|Max))?)\b', text, re.IGNORECASE)
    if not m:
        m = re.search(r'\b(M[1-5](?:\s+(?:Pro|Max))?)\s+chip\b', text, re.IGNORECASE)
    if not m:
        m = re.search(r'\bMacBook[^\n,]+?\b(M[1-5](?:\s+(?:Pro|Max))?)\b', text, re.IGNORECASE)
    if m:
        return f"Apple {m.group(1).upper()}"

    # 2. Qualcomm Snapdragon: Snapdragon X Elite / Plus / X1-26-100
    m = re.search(r'Snapdragon\s+X\s+(?:X1[- ]?26[- ]?10[01]|X1[EP][- ]?[0-9]{2}[- ]?100|Elite|Plus)', text, re.IGNORECASE)
    if m:
        val = m.group(0).strip()
        if '26' in val:
            return "Qualcomm Snapdragon X X1-26-100"
        elif 'elite' in val.lower():
            return "Qualcomm Snapdragon X Elite"
        elif 'plus' in val.lower():
            return "Qualcomm Snapdragon X Plus"
        return f"Qualcomm {val}"

    # 3. AMD Ryzen AI MAX+ / MAX (Strix Halo): Ryzen AI MAX+ 395, Ryzen AI MAX 390
    m = re.search(r'Ryzen\s+AI\s+MAX(?:\+)?\s+([0-9]{3})', text, re.IGNORECASE)
    if m:
        plus = "+" if "+" in text else ""
        return f"AMD Ryzen AI Max{plus} {m.group(1)}"

    # 4. AMD Ryzen AI 300/400 series: Ryzen AI 9 HX 370, Ryzen AI 9 365, Ryzen AI 7 PRO 350
    m = re.search(r'Ryzen\s+AI\s+([3579])?(?:\s+PRO)?(?:\s+HX)?\s+([0-9]{3})', text, re.IGNORECASE)
    if m:
        tier = m.group(1) or ""
        sku = m.group(2)
        pro = " PRO" if "pro" in text.lower() else ""
        hx = " HX" if "hx" in text.lower() else ""
        tier_str = f" {tier}" if tier else ""
        return f"AMD Ryzen AI{tier_str}{pro}{hx} {sku}".replace("  ", " ")

    # 5. AMD Ryzen 100 / 200 / 7000 / 8000 / 9000:
    m = re.search(r'Ryzen\s+([3579])(?:\s+PRO)?[- ]([0-9]{2,4}[A-Za-z0-9]*)', text, re.IGNORECASE)
    if m:
        tier = m.group(1)
        sku = m.group(2).upper()
        pro = " PRO" if "pro" in text.lower() else ""
        return f"AMD Ryzen {tier}{pro} {sku}"

    # 6. Intel Core Ultra: Core Ultra 9 275HX, Core Ultra 7 Processor 355, Core Ultra 7-255U
    m = re.search(r'(?:Intel\s+)?Core\s+Ultra\s+(?:X)?([3579])(?:\s+Processor)?[- ]([0-9]{3,4}[A-Za-z]*)', text, re.IGNORECASE)
    if m:
        return f"Intel Core Ultra {m.group(1)} {m.group(2).upper()}"

    # 7. Intel Core (Series 1 & 2): Core 9-270H, Core 7-240H, Core 5-210H, Core 7 150U, Core 5 120U
    m = re.search(r'(?:Intel\s+)?Core\s+([3579])(?:\s+Processor)?[- ]([0-9]{3}[A-Za-z]*)', text, re.IGNORECASE)
    if m and 'ultra' not in text.lower():
        return f"Intel Core {m.group(1)} {m.group(2).upper()}"

    # 8. Intel Core i3/i5/i7/i9: i7-13620H, i7-14700HX, i5 12450HX, i3-1215U, i7-13645HX
    m = re.search(r'(?:Intel\s+)?(?:Core\s+)?(i[3579])[- ]([0-9]{4,5}[A-Za-z0-9]*)', text, re.IGNORECASE)
    if m:
        return f"Intel Core {m.group(1).lower()}-{m.group(2).upper()}"

    # 9. Intel N-series / Celeron / Pentium
    m = re.search(r'(?:Intel\s+)?(?:Processor\s+)?\b(N[0-9]{2,3}|U300)\b', text, re.IGNORECASE)
    if m:
        return f"Intel {m.group(1).upper()}"

    m = re.search(r'(?:Intel\s+)?(Celeron|Pentium(?:\s+Gold)?)[- ]([A-Za-z0-9]+)', text, re.IGNORECASE)
    if m:
        return f"Intel {m.group(1).title()} {m.group(2).upper()}"

    # 10. AMD Athlon
    m = re.search(r'Athlon\s+(?:Silver|Gold)?[- ]([0-9]{4}[A-Za-z]*)', text, re.IGNORECASE)
    if m:
        return f"AMD Athlon {m.group(1).upper()}"

    return None

all_laptops = []
cpu_counts = Counter()
store_coverage = Counter()
unextracted = []

for sf in store_files:
    if not os.path.exists(sf):
        continue
    with open(sf, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    items = []
    if isinstance(data, dict):
        items = data.get('products', []) or data.get('laptops', []) or data.get('results', [])
    elif isinstance(data, list):
        items = data

    store_name = os.path.basename(sf).replace('.json', '')
    
    for item in items:
        title = item.get('title') or item.get('name') or item.get('product_name') or ''
        specs = item.get('specs') or {}
        
        raw_cpu = ""
        if isinstance(specs, dict):
            raw_cpu = specs.get('Processor') or specs.get('CPU') or specs.get('processor') or specs.get('cpu') or ''
            if isinstance(raw_cpu, dict):
                raw_cpu = str(raw_cpu.get('model') or raw_cpu.get('raw') or '')
        elif isinstance(specs, list):
            raw_cpu = " ".join(str(x) for x in specs)

        cpu = extract_cpu_from_text(str(raw_cpu)) or extract_cpu_from_text(title)

        if cpu:
            cpu_counts[cpu] += 1
            store_coverage[store_name] += 1
            all_laptops.append({'store': store_name, 'title': title, 'cpu': cpu, 'raw_cpu': str(raw_cpu)})
        else:
            unextracted.append({'store': store_name, 'title': title, 'raw_cpu': str(raw_cpu)})

print(f"Total laptops processed: {len(all_laptops) + len(unextracted)}")
print(f"Laptops with extracted CPU: {len(all_laptops)}")
print(f"Laptops where CPU regex missed: {len(unextracted)}")
print(f"Total UNIQUE CPU models found in Egyptian stores: {len(cpu_counts)}")

print("\n--- Breakdown by Manufacturer ---")
by_mfg = Counter()
for cpu in cpu_counts:
    mfg = cpu.split()[0]
    by_mfg[mfg] += 1
for mfg, count in by_mfg.items():
    print(f"  {mfg}: {count} unique SKUs")

output_data = {
    'total_laptops': len(all_laptops) + len(unextracted),
    'extracted_count': len(all_laptops),
    'unique_cpus_count': len(cpu_counts),
    'cpus': sorted(list(cpu_counts.keys())),
    'cpu_frequencies': dict(cpu_counts.most_common()),
}

with open('scratch/egyptian_market_cpus.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2)

print("\nSaved full list to scratch/egyptian_market_cpus.json")
