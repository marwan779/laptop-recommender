import re

text = '15.6" FHD (1920x1080) IPS'
pat_old = re.compile(r'\b(1[0-8](?:\.\d)?)\s*(?:inch|\"|\'|″|-inch)\b', re.I)
pat_new = re.compile(r'\b(1[0-8](?:\.\d)?)\s*(?:inch|\"|\'|″|-inch)(?!\w)', re.I)

print("Old pat match:", pat_old.search(text))
print("New pat match:", pat_new.search(text))

