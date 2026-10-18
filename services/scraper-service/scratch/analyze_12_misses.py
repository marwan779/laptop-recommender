import json
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

raw_cat = json.load(open('pipeline_results_compumarts.json', encoding='utf-8'))
audited_cat = json.load(open('pipeline_results_compumarts_audited.json', encoding='utf-8'))

targets = [
    ("Acer Aspire Go 16", ["identity.manufacturer_part_number", "identity.retailer_sku"]),
    ("Zenbook A14", ["physical.depth_mm", "physical.height_mm"]),
    ("Legion Pro 7i", ["storage.max_supported_gb"]),
    ("Vivobook 15 X1504VA", ["physical.depth_mm", "physical.height_mm"]),
    ("Zenbook 14 OLED UM3406GA", ["physical.depth_mm", "physical.height_mm"]),
    ("TUF Gaming F16", ["storage.max_supported_gb"]),
    ("Legion 5 15IAX10", ["storage.form_factor"]),
    ("AORUS MASTER 18", ["display.panel_type", "display.size_inches"]),
    ("MSI Thin 15 B13VE", ["storage.slot_count", "storage.form_factor"]),
    ("Vector 17 HX", ["storage.slot_count"]),
    ("LOQ 15IRX10", ["storage.max_supported_gb"]),
    ("LOQ 15IRX9", ["storage.slot_count"]),
]

for name, fpaths in targets:
    matched = []
    for idx, (raw_item, aud_item) in enumerate(zip(raw_cat, audited_cat)):
        t = aud_item.get('title', '')
        u = aud_item.get('url', '')
        if name.lower() in t.lower() or name.lower() in u.lower():
            matched.append((idx, raw_item, aud_item))
    print(f"=== TARGET: {name} ===")
    for idx, raw_item, aud_item in matched:
        print(f"Index [{idx}]: {aud_item['title']}")
        print(f"  URL: {aud_item['url']}")
        for fpath in fpaths:
            cat, sub = fpath.split('.')
            raw_val = raw_item['specs'].get(cat, {}).get(sub)
            aud_val = aud_item['specs'].get(cat, {}).get(sub)
            print(f"  Field {fpath}: before audit={raw_val!r} -> after audit={aud_val!r}")
        print("  Source table relevant entries:")
        for k, v in aud_item.get('source_table', {}).items():
            if any(w in k.lower() for w in ['dimension', 'storage', 'hard', 'drive', 'slot', 'part', 'sku', 'screen', 'panel', 'display', 'max']):
                print(f"    {k}: {v}")
    print()

