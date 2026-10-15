import json

with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def p(s):
    print(str(s).encode('ascii', 'replace').decode('ascii'))

print('=== Item 8 (Power) ===')
for idx in ['76', '110']:
    p(f"{idx} {data[idx]['structured']['power_battery']}")

print('\n=== Item 9 (Audio) ===')
for idx in ['0', '10', '45', '72', '93']:
    p(f"{idx} {data[idx]['structured']['audio']}")

print('\n=== Item 10 (OS) ===')
for idx in ['3', '10', '31', '32', '87', '97']:
    p(f"{idx} {data[idx]['structured']['operating_system']}")

print('\n=== Item 11 (Storage) ===')
for idx in ['6', '13', '29', '70', '85']:
    p(f"{idx} {data[idx]['structured']['storage']}")

print('\n=== Item 12 (Connectivity) ===')
for idx in ['3', '14', '17', '34', '35', '76']:
    c = data[idx]['structured']['connectivity']
    p(f"{idx} eth: {c.get('ethernet')} ports count: {len(c.get('ports') or [])}")
    p(f"   sample ports: {(c.get('ports') or [])[:3]}")

