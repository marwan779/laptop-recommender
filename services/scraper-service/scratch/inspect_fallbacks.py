import sys
sys.path.insert(0, '.')
import json
from app.core.patterns.title_extractor import TitleSpecExtractor
from app.core.normalizer import ModelNormalizer

data = json.load(open('scraping-results/stores/store_elbadr.json', encoding='utf-8'))
products = data['products']
fallback_count = 0
for p in products:
    if p.get('specs_extraction_source') == 'title_fallback':
        fallback_count += 1
        new_specs = TitleSpecExtractor.extract(p['title'])
        preserved = {k: v for k, v in p.get('specs', {}).items() if k in ['Stock', 'Model', 'SKU', 'MPN', 'UPC']}
        combined_specs = {**preserved, **new_specs}
        desc_line = f"{p['title']} {combined_specs.get('Model', '')} " + " ".join(str(v) for v in combined_specs.values())
        tokens = ModelNormalizer.extract_model_tokens(desc_line)
        print('TITLE:', p['title'][:65])
        print('  Old Base Model:', p.get('base_model'), '--> New Base Model:', tokens.get('base_model'))
        print('  Old Specs:', p.get('specs'))
        print('  New Specs:', combined_specs)
        print('-' * 60)
print(f'Total fallback products: {fallback_count}')
