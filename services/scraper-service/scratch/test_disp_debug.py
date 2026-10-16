import sys
import json
import re

sys.path.insert(0, ".")
with open("pipeline_results_compumarts.json", "r", encoding="utf-8") as f:
    data = json.load(f)

item = data[1]
from pipeline.sanitizer import TextSanitizer

sanitizer = TextSanitizer()
table = sanitizer.sanitize_table(item["source_table"])

print("Table Touch keys:")
for k, v in table.items():
    if "touch" in k.lower():
        print(f"  {k} -> {repr(v)}")

disp_rows = table.get("Display", "")
primary_text = disp_rows
title = item["title"]
touch_targets = [primary_text, title, " ".join(table.values())]

for idx, tt in enumerate(touch_targets):
    m1 = re.search(r"\b(?:touchscreen|touch\s*screen|multi-touch|touch\s+display|touch\s+\d+hz|dual\s+16[″\"]\s+3k\s+oled\s+touch)\b", tt, re.I)
    m2 = re.search(r"\btouch\b", tt, re.I) and not re.search(r"\b(?:touchpad|touch\s*pad|non-touch|no\s+touch)\b", tt, re.I)
    print(f"target {idx}: m1={bool(m1)}, m2={bool(m2)}")
    if m1:
        print(f"  m1 match: {m1.group(0)}")

for k, v in table.items():
    if "touch" in k.lower() and "pad" not in k.lower():
        vl = v.lower()
        print("Loop item key:", k, "vl:", repr(vl))
        print("any yes:", any(yes in vl for yes in ["yes", "true", "supported"]))
        print("any no:", any(no in vl for no in ["no", "false", "non-touch"]))
