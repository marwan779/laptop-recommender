import json
import re

with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def parse_ethernet_speed(text: str) -> str | None:
    if not text:
        return None
    t = text.lower()
    if re.search(r'\b10\s*g(?:igabit)?\b', t):
        return '10G'
    if re.search(r'\b5\s*g(?:igabit)?\b', t):
        return '5G'
    if re.search(r'\b2\.5\s*g(?:igabit)?\b', t):
        return '2.5G'
    if re.search(r'\b(?:1\s*g(?:igabit)?|gigabit|1000m|10\/100\/1000|100\/1000m|rj-?45)\b', t):
        return '1G'
    if re.search(r'\b(?:100m|10\/100|fast\s+ethernet)\b', t):
        return '100M'
    return None

def clean_ports_list(ports: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for p in ports:
        if not p:
            continue
        s = str(p)
        # Remove footnotes
        s = re.sub(r'\b(?:\d{1,2}\s+){1,4}\d{1,2}$', '', s.strip())
        s = re.sub(r'\(\s*\d+\s*\)', '', s)
        # Remove marketing lines
        if any(bad in s.lower() for bad in ["all the ports you need", "built to dominate", "connect with ease"]):
            continue
        # Remove (TBD)
        s = re.sub(r'\(TBD\)', '', s, flags=re.I)
        # Clean whitespace and newlines
        s = re.sub(r'\s+', ' ', s).strip()
        if not s or s.lower() in ("no", "0", "none"):
            continue
        s_norm = s.lower()
        if s_norm not in seen:
            seen.add(s_norm)
            cleaned.append(s)
    return cleaned

def parse_ports_summary(all_ports_text: str) -> dict:
    t = all_ports_text.lower()
    # usb-a count
    m_usba = re.findall(r'(\d+)\s*(?:x|[×*])?\s*(?:usb\s*3|usb-a|type-a)', t)
    usb_a_count = sum(int(x) for x in m_usba) if m_usba else (1 if 'type-a' in t or 'usb-a' in t else 0)
    
    # usb-c count
    m_usbc = re.findall(r'(\d+)\s*(?:x|[×*])?\s*(?:usb-c|type-c|thunderbolt)', t)
    usb_c_count = sum(int(x) for x in m_usbc) if m_usbc else (1 if 'type-c' in t or 'usb-c' in t else 0)
    
    has_tb = bool(re.search(r'thunderbolt', t))
    has_hdmi = bool(re.search(r'hdmi', t))
    has_eth = bool(re.search(r'rj-?45|ethernet|lan', t))
    has_sd = bool(re.search(r'sd|card\s*reader|microsd', t))
    has_audio = bool(re.search(r'audio|headphone|3\.5mm|combo\s*jack', t))
    
    return {
        "usb_a": usb_a_count,
        "usb_c": usb_c_count,
        "thunderbolt": has_tb,
        "hdmi": has_hdmi,
        "ethernet": has_eth,
        "sd_card": has_sd,
        "audio_jack": has_audio,
    }

print("Testing ethernet speed parsing...")
for idx in ['3', '14', '17', '34', '35']:
    item = data[idx]
    c = item['structured']['connectivity']
    raw_eth = c.get('ethernet') or ''
    ports = c.get('ports') or []
    full_t = f"{raw_eth} {' '.join(ports)}"
    spd = parse_ethernet_speed(full_t)
    print(f"idx {idx}: raw_eth={raw_eth!r} -> spd={spd!r}")

print("\nTesting ports cleaning on idx 17, 76...")
for idx in ['17', '76']:
    item = data[idx]
    c = item['structured']['connectivity']
    cleaned = clean_ports_list(c.get('ports') or [])
    print(f"idx {idx} cleaned ports:", cleaned)

