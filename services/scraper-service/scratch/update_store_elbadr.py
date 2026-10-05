import sys
sys.path.insert(0, '.')
import json
from app.core.patterns.title_extractor import TitleSpecExtractor
from app.core.normalizer import ModelNormalizer

with open('scraping-results/stores/store_elbadr.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

products = data['products']
changed_count = 0

for p in products:
    old_base_model = p.get('base_model')
    old_specs = dict(p.get('specs', {}))
    
    # 1. Update specs if title_fallback
    if p.get('specs_extraction_source') == 'title_fallback':
        new_extracted = TitleSpecExtractor.extract(p['title'])
        preserved = {k: v for k, v in old_specs.items() if k in ['Stock', 'Model', 'SKU', 'MPN', 'UPC']}
        combined = {**preserved, **new_extracted}
        p['specs'] = combined
    
    # 2. Re-evaluate model tokens
    combined_text = f"{p['title']} {p.get('mpn') or ''} {p.get('retailer_sku') or ''} {p.get('specs', {}).get('Model') or ''} {' '.join(str(v) for v in p.get('specs', {}).values())}"
    tokens = ModelNormalizer.extract_model_tokens(combined_text)
    
    new_base_model = tokens.get('base_model')
    if new_base_model != old_base_model or p['specs'] != old_specs:
        changed_count += 1
        p['base_model'] = new_base_model
        p['sub_model'] = tokens.get('sub_model')

print(f"Updated {changed_count} products out of {len(products)}.")

with open('scraping-results/stores/store_elbadr.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Saved updated store_elbadr.json successfully.")
