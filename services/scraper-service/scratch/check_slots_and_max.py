import json
import re

with open('pipeline_results_compumarts.json', encoding='utf-8') as f:
    items = json.load(f)

mem_slots = []
storage_slots = []
max_mem = []
max_storage = []

for idx, item in enumerate(items, 1):
    mem_raw = item['specs']['memory'].get('raw_spec', '')
    storage_raw = item['specs']['storage'].get('raw_spec', '')
    title = item.get('title', '')
    
    # Memory slots
    m_ms = re.findall(r'(?:(?:two|2)\s*(?:ddr\d\s*)?(?:so-?dimm|csodimm)\s*slots?|\b(\d+)\s*x\s*\d+\s*gb|\b(\d+)\s*(?:so-?dimm\s*)?slots?|ram,\s*number\s*of\s*slots:\s*(\d+)|memory soldered[^,\n|]+)', mem_raw, re.I)
    if m_ms:
        mem_slots.append((idx, m_ms))
        
    # Storage slots
    m_ss = re.findall(r'(?:(?:two|2)\s*m\.2\s*slots?|total\s*(\d+)x\s*m\.2\s*slots?|(\d+)\s*[xX×]\s*m\.2|(\d+)\s*m\.2\s*\(ssd\)|expansion\s*slots?:\s*[^,\n|]+)', storage_raw, re.I)
    if m_ss:
        storage_slots.append((idx, m_ss))
        
    # Max memory
    m_mm = re.findall(r'(?:(?:up\s+to\s*|max(?:imum)?\s*(?:memory|ram)?\s*[:\s]*|maximum supported system memory:\s*)(\d+)\s*(?:gb|g)\b)', mem_raw, re.I)
    if m_mm:
        max_mem.append((idx, m_mm))
        
    # Max storage
    m_mst = re.findall(r'(?:up to two drives[^,\n|]*|up to\s*(\d+)\s*tb\b|additional storage support:[^,\n|]+)', storage_raw, re.I)
    if m_mst:
        max_storage.append((idx, m_mst))

print(f'Mem slots found: {len(mem_slots)}')
print(f'Storage slots found: {len(storage_slots)}')
print(f'Max mem found: {len(max_mem)}')
print(f'Max storage found: {len(max_storage)}')

