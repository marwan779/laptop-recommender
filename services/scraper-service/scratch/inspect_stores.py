import os
import sys
import json
import glob

store_files = [
    'scraping-results/stores/store_compumarts.json',
    'scraping-results/stores/store_sigma.json',
    'scraping-results/stores/store_elbadr.json',
    'scraping-results/stores/store_twob.json',
    'scraping-results/stores/store_tradeline.json',
    'store_btech.json',
    'store_amazon.json',
    'store_noon.json',
]

for sf in store_files:
    if os.path.exists(sf):
        try:
            with open(sf, 'r', encoding='utf-8') as f:
                d = json.load(f)
                print(f"=== {sf} ===")
                if isinstance(d, dict):
                    print("Top keys:", list(d.keys()))
                    for k, v in d.items():
                        if isinstance(v, list) and v:
                            print(f"  List '{k}': {len(v)} items. Item 0 type: {type(v[0])}")
                            if isinstance(v[0], dict):
                                print(f"    Item 0 keys: {list(v[0].keys())[:10]}")
                elif isinstance(d, list):
                    print(f"Top list: {len(d)} items. Item 0 keys: {list(d[0].keys())[:10] if d and isinstance(d[0], dict) else type(d[0])}")
        except Exception as e:
            print(f"Error {sf}: {e}")

