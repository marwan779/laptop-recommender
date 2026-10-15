import json
import re

with open('pipeline_results_compumarts.json', encoding='utf-8') as f:
    items = json.load(f)

interfaces = []
form_factors = []
for item in items:
    raw = item['specs']['storage'].get('raw_spec', '')
    title = item.get('title', '')
    full = f'{raw} {title}'
    
    m_iface = re.findall(r'\b(PCIe\s*(?:Gen\s*)?[345](?:\.0)?(?:\s*x\s*[24])?(?:\s*NVMe)?|NVMe\s*PCIe|NVMe|SATA(?:\s*III)?)\b', full, re.I)
    if m_iface:
        interfaces.append(m_iface[0])
    
    m_ff = re.findall(r'\b(M\.2\s*(?:2280|2242|2230)?|2\.5(?:-inch|")?)\b', full, re.I)
    if m_ff:
        form_factors.append(m_ff[0])

print(f'Interfaces found: {len(interfaces)} / {len(items)}')
print('Sample interfaces:', list(set(interfaces))[:10])
print(f'Form factors found: {len(form_factors)} / {len(items)}')
print('Sample form factors:', list(set(form_factors))[:10])

