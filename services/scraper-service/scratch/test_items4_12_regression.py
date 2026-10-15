import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    fixtures = json.load(f)

from gliner_extractor.compumarts_extractor import CompumartsExtractor

extractor = CompumartsExtractor()

passed = 0
failed = 0
results = {}

for idx_str, item in fixtures.items():
    idx = int(idx_str)
    title = item['title']
    specs = item.get('specs', {})
    meta = item.get('metadata', {})
    
    structured, envs = extractor.extract(specs, title, meta)
    results[idx] = structured

# Assertions for prompt Round 2 items 4-12
print("=== Verifying Specific Fixture Expectations ===")

# idx 1: threads null or 16 (never 7); panel IPS
item1 = results[1]
print("idx 1:", "threads=", item1['cpu']['threads'], "panel=", item1['display']['panel_type'])
assert item1['cpu']['threads'] != 7, f"idx 1 threads was {item1['cpu']['threads']}"

# idx 3: OS No OS
item3 = results[3]
print("idx 3 OS:", item3['operating_system']['name'])

# idx 5: Wh 41, summary not bare 41
item5 = results[5]
print("idx 5:", "Wh=", item5['power_battery']['battery_capacity_wh'], "summary=", item5['power_battery']['summary'])

# idx 6: storage slot_count not 4
item6 = results[6]
print("idx 6 storage slot_count:", item6['storage']['slot_count'])

# idx 10: OS No OS
item10 = results[10]
print("idx 10 OS:", item10['operating_system']['name'])

# idx 12: threads from lookup (155H -> 22)
item12 = results[12]
print("idx 12:", "model=", item12['cpu']['model'], "cores=", item12['cpu']['cores'], "threads=", item12['cpu']['threads'])

# idx 16: retailer_sku
item16 = results[16]
print("idx 16:", "mpn=", item16['identity']['manufacturer_part_number'], "ret_sku=", item16['identity'].get('retailer_sku'))

# idx 17: OMEN 16 casing, ports cleaned
item17 = results[17]
print("idx 17:", "family=", item17['identity']['laptop_family'], "ports=", item17['connectivity']['ports'][:1])

# idx 19: retailer_sku
item19 = results[19]
print("idx 19:", "mpn=", item19['identity']['manufacturer_part_number'], "ret_sku=", item19['identity'].get('retailer_sku'))

# idx 30: Snapdragon X / X1-26-100
item30 = results[30]
print("idx 30:", "mfg=", item30['cpu']['manufacturer'], "line=", item30['cpu']['line'], "model=", item30['cpu']['model'])

# idx 31: Windows 11 Home
item31 = results[31]
print("idx 31 OS:", item31['operating_system']['name'])

# idx 34: GeForce RTX 5060, ethernet 2.5G
item34 = results[34]
print("idx 34:", "gpu=", item34['gpu']['model'], "eth_spd=", item34['connectivity'].get('ethernet_speed'))

# idx 35: 5G ethernet
item35 = results[35]
print("idx 35 eth_spd:", item35['connectivity'].get('ethernet_speed'))

# idx 43: model 155U, resolution 1920 x 1200
item43 = results[43]
print("idx 43:", "cpu_model=", item43['cpu']['model'], "res=", item43['display']['resolution'])

# idx 44: aspect_ratio 16:9
item44 = results[44]
print("idx 44 aspect_ratio:", item44['display']['aspect_ratio'])

# idx 48: ASUS MPN with zero
item48 = results[48]
print("idx 48 MPN:", item48['identity']['manufacturer_part_number'])

# idx 51: RTX 5060 VRAM 8
item51 = results[51]
print("idx 51 GPU:", item51['gpu']['model'], "VRAM=", item51['gpu']['vram_gb'])

# idx 56: retailer_sku TBC..., MPN from title 9S7-15Q342-895
item56 = results[56]
print("idx 56:", "mpn=", item56['identity']['manufacturer_part_number'], "ret_sku=", item56['identity'].get('retailer_sku'))

# idx 58: model 13420H
item58 = results[58]
print("idx 58 model:", item58['cpu']['model'])

# idx 59: model 13900H, full_name
item59 = results[59]
print("idx 59:", "model=", item59['cpu']['model'], "fn=", item59['cpu']['full_name'])

# idx 62: touchscreen True
item62 = results[62]
print("idx 62 touch:", item62['display']['touchscreen'])

# idx 68: threads not 24 (270H -> 20), is_bundle True
item68 = results[68]
print("idx 68:", "threads=", item68['cpu']['threads'], "is_bundle=", item68['identity'].get('is_bundle'), "model=", item68['identity']['laptop_model'])

# idx 71: source_mismatch True
item71 = results[71]
print("idx 71 source_mismatch:", item71['extraction_meta'].get('source_mismatch'))

# idx 76: battery Wh null
item76 = results[76]
print("idx 76 battery Wh:", item76['power_battery']['battery_capacity_wh'])

# idx 77: 240H threads 16
item77 = results[77]
print("idx 77:", "threads=", item77['cpu']['threads'], "cores=", item77['cpu']['cores'])

# idx 79: laptop_model not CPU
item79 = results[79]
print("idx 79 laptop_model:", item79['identity']['laptop_model'])

# idx 83: source_mismatch True
item83 = results[83]
print("idx 83 source_mismatch:", item83['extraction_meta'].get('source_mismatch'), "size=", item83['display']['size_inches'])

# idx 85: form_factor null
item85 = results[85]
print("idx 85 form_factor:", item85['storage']['form_factor'])

# idx 87: panel Mini-LED
item87 = results[87]
print("idx 87 panel:", item87['display']['panel_type'])

# idx 94: MPN null, res 2560 x 1600
item94 = results[94]
print("idx 94:", "mpn=", item94['identity']['manufacturer_part_number'], "res=", item94['display']['resolution'])

# idx 98: laptop_model not full title
item98 = results[98]
print("idx 98 laptop_model:", item98['identity']['laptop_model'])

# idx 105: Snapdragon X X1-26-100
item105 = results[105]
print("idx 105:", "mfg=", item105['cpu']['manufacturer'], "line=", item105['cpu']['line'], "model=", item105['cpu']['model'])

# idx 110: battery Wh null
item110 = results[110]
print("idx 110 battery Wh:", item110['power_battery']['battery_capacity_wh'])

# idx 111: laptop_model not full title
item111 = results[111]
print("idx 111 laptop_model:", item111['identity']['laptop_model'])

print("\nAll targeted checks inspected!")

