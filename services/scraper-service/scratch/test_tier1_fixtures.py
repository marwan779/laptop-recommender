import sys
sys.path.insert(0, ".")
import json
from gliner_extractor.compumarts_extractor import CompumartsExtractor

extractor = CompumartsExtractor()

with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

mem_conflicts = []
stg_conflicts = []
results = {}

for idx_str, item in data.items():
    title = item.get('title', '')
    specs = item.get('specs', {})
    meta = item.get('metadata', {})
    struct, _ = extractor.extract(specs, title=title, metadata=meta)
    results[idx_str] = struct
    for c in struct.get('extraction_meta', {}).get('conflicts', []):
        if c.get('field') == 'memory.capacity_gb':
            mem_conflicts.append((idx_str, c))
        elif c.get('field') == 'storage.capacity_gb':
            stg_conflicts.append((idx_str, c))

print(f"Total memory conflicts across all {len(data)} laptops: {len(mem_conflicts)}")
for idx_str, c in mem_conflicts:
    print(f"  idx {idx_str}: title={c['title_value']}, table={c['table_value']}, chosen={c['chosen']}, reason={c['reason']}")

print(f"Total storage conflicts across all {len(data)} laptops: {len(stg_conflicts)}")
for idx_str, c in stg_conflicts:
    print(f"  idx {idx_str}: title={c['title_value']}, table={c['table_value']}, chosen={c['chosen']}, reason={c['reason']}")

# Check specific cases
print("\nSpecific idx results:")
print("idx 35 RAM capacity:", results['35']['memory']['capacity_gb'])
print("idx 1 CPU cores/threads:", results['1']['cpu']['cores'], results['1']['cpu']['threads'])
print("idx 44 display aspect ratio:", results['44']['display']['aspect_ratio'])
print("idx 51 GPU vram:", results['51']['gpu']['vram_gb'])
print("idx 85 storage form factor:", results['85']['storage']['form_factor'])
print("idx 17 max RAM:", results['17']['memory']['max_supported_gb'])
print("idx 29 max RAM / adapter:", results['29']['memory']['max_supported_gb'], results['29']['power_battery']['power_adapter_w'])
print("idx 63 adapter:", results['63']['power_battery']['power_adapter_w'])
print("idx 77 CPU:", results['77']['cpu']['model'], results['77']['cpu']['cores'], results['77']['cpu']['threads'])
print("idx 48 CPU:", results['48']['cpu']['model'], results['48']['cpu']['cores'], results['48']['cpu']['threads'])
