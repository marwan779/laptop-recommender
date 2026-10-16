
import re
table = {'Touchscreen': 'None', 'Touchpad': 'Buttonless Mylar multi-touch touchpad'}
touch_targets = ['', '', ' '.join(table.values())]
for tt in touch_targets:
    if not tt:
        continue
    if re.search(r'\b(?:touchscreen|touch\s*screen|multi-touch|touch\s+display)\b', tt, re.I):
        if not re.search(r'\b(?:non-touch|no\s+touch)\b', tt, re.I):
            print('Matched in touch_targets: True!')
            break

for k, v in table.items():
    if 'touch' in k.lower() and 'pad' not in k.lower():
        vl = v.lower()
        print('Checking key:', k, 'val:', vl)
        if any(yes in vl for yes in ['yes', 'true', 'supported']):
            print('-> True')
            break
        elif any(no in vl for no in ['no', 'false', 'non-touch']):
            print('-> False')
            break
