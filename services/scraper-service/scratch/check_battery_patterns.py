import json
import re

with open('pipeline_results_compumarts.json', encoding='utf-8') as f:
    items = json.load(f)

cells = []
fast = []
for idx, item in enumerate(items, 1):
    raw = item['specs']['power_battery'].get('raw_spec', '')
    title = item.get('title', '')
    full = f'{raw} {title}'
    
    m_cell = re.search(r'\b([2-6])\s*[- ]\s*cells?\b|battery cells?:\s*([2-6])\b', full, re.I)
    if m_cell:
        c = m_cell.group(1) or m_cell.group(2)
        cells.append((idx, c))
        
    m_fast = re.search(r'(recharge from 0-50%[^,\n|]+|fast charg\w+[^,\n|]*|supports battery fast charge[^,\n|]*|rapid charge[^,\n|]*)', full, re.I)
    if m_fast:
        fast.append((idx, m_fast.group(1).strip()))

print(f'Cells found: {len(cells)}')
for idx, c in cells:
    print(f'  #{idx}: {c} cells')

print(f'Fast charge found: {len(fast)}')
for idx, fst in fast:
    print(f'  #{idx}: {fst}')
