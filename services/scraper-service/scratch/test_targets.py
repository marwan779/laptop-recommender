import json

data = json.load(open('pipeline_results_compumarts.json', encoding='utf-8'))
targets = ['lenovo-yoga-7', 'asus-vivobook-16-x1605va', 'hp-victus-15-fa2787nr', 'msi-thin-15-b13ve']

for i, x in enumerate(data):
    if any(t in x['url'] for t in targets):
        print(f"[{i}] {x['title']}")
        print(f"  URL: {x['url']}")
        print(f"  RAM slots: {x['specs']['memory'].get('slot_count')} (is_soldered={x['specs']['memory'].get('is_soldered')})")
        print(f"  RAM raw: {x['source_table'].get('RAM') or x['source_table'].get('Memory') or x['source_table'].get('Ram Slots')}")
        print(f"  Storage slots: {x['specs']['storage'].get('slot_count')}, form_factor: {x['specs']['storage'].get('form_factor')}")
        print(f"  Storage raw: {x['source_table'].get('Hard Drive') or x['source_table'].get('Storage') or x['source_table'].get('Expansion Slots')}")
        print(f"  Display gamut: {x['specs']['display'].get('color_gamut')}")
        print(f"  Display raw: {x['source_table'].get('Display')}")
        print(f"  Chassis Colors raw: {x['source_table'].get('Colors') or x['source_table'].get('Color')}")
        print("-" * 50)

