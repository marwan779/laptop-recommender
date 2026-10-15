import json
import re

with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def extract_title_ram(title: str) -> int | None:
    if not title:
        return None
    # 1. Remove screen size spans like 16-inch, 16", 15.6", 14-inch
    clean = re.sub(r'\b\d+(\.\d+)?\s*(?:-inch|["″\']|inch)\b', ' ', title, flags=re.I)
    
    # 2. Remove GPU spans with optional VRAM (ensuring we don't strip if followed by DDR/LPDDR/RAM/Memory)
    clean = re.sub(
        r'\b(?:GeForce\s*)?(?:RTX|GTX|RX|Arc)\s+[0-9A-Za-z]+(?:\s*(?:Ti|Super))?(?:\s*Laptop\s+GPU)?(?:\s*\d{1,2}\s*GB(?!\s*(?:DDR|LPDDR|RAM|Memory|SO-DIMM))(?:\s*GDDR\d*X?)?)?',
        ' ',
        clean,
        flags=re.I
    )
    # Remove any remaining \d+GB GDDR...
    clean = re.sub(r'\b\d{1,2}\s*GB\s*GDDR\d*X?\b', ' ', clean, flags=re.I)
    
    # 3. Match explicit RAM: \d+\s*GB followed by DDR|LPDDR|RAM|Memory|on board
    m_exp = re.search(r'\b([48]|12|16|24|32|48|64|96|128)\s*(?:GB|G)\s*(?:RAM|DDR[45]?|LPDDR[45]?X?|Memory|on board)\b', clean, re.I)
    if m_exp:
        return int(m_exp.group(1))
        
    # 4. Single remaining \d+GB not followed by SSD|NVMe|HDD|TB|ROM
    candidates = re.findall(r'\b([48]|12|16|24|32|48|64|96|128)\s*(?:GB|G)\b(?!\s*(?:SSD|NVMe|PCIe|HDD|TB|ROM))', clean, re.I)
    if len(candidates) == 1:
        return int(candidates[0])
    return None

def extract_title_storage(title: str) -> int | None:
    if not title:
        return None
    # Exclude \d+GB LPDDR/DDR/RAM/Memory
    clean = re.sub(r'\b\d+\s*(?:GB|G)\s*(?:DDR[45]?|LPDDR[45]?X?|RAM|Memory|on board)\b', ' ', title, flags=re.I)
    # Also exclude GPU VRAM
    clean = re.sub(r'\b\d{1,2}\s*GB\s*GDDR\d*X?\b', ' ', clean, flags=re.I)
    
    # Now find storage: TB first or GB followed by SSD|NVMe|HDD|storage
    m_tb = re.search(r'\b([1248])\s*TB\b(?:\s*(?:SSD|NVMe|HDD|Storage|PCIe))?', clean, re.I)
    m_gb_ssd = re.search(r'\b(128|256|512|1024|2048)\s*(?:GB|G)\s*(?:SSD|NVMe|HDD|PCIe|Storage|EMMC)\b', clean, re.I)
    
    if m_tb:
        return int(m_tb.group(1)) * 1024
    if m_gb_ssd:
        return int(m_gb_ssd.group(1))
        
    # Fallback to single remaining storage-like size
    m_any = re.search(r'\b(128|256|512|1024|2048)\s*(?:GB|G)\b', clean, re.I)
    if m_any:
        return int(m_any.group(1))
    return None

print('Testing on dataset...')
ram_conflicts = []
storage_conflicts = []

for idx, item in data.items():
    t = item.get('title', '')
    struct = item.get('structured', {})
    table_ram = struct.get('memory', {}).get('capacity_gb')
    table_st = struct.get('storage', {}).get('capacity_gb')
    
    t_ram = extract_title_ram(t)
    t_st = extract_title_storage(t)
    
    if t_ram and table_ram and t_ram != table_ram:
        ram_conflicts.append((idx, t_ram, table_ram))
    if t_st and table_st and t_st != table_st:
        storage_conflicts.append((idx, t_st, table_st))

print(f'Total RAM conflicts: {len(ram_conflicts)}')
for rc in ram_conflicts:
    print('RAM conflict:', rc[0], 'Title RAM:', rc[1], 'Table RAM:', rc[2])

print(f'Total Storage conflicts: {len(storage_conflicts)}')
for sc in storage_conflicts:
    print('Storage conflict:', sc[0], 'Title St:', sc[1], 'Table St:', sc[2])

