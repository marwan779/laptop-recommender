import json
import re
from pathlib import Path

# Load fixtures
with open('tests/fixtures/regression_laptops.json', 'r', encoding='utf-8') as f:
    fixtures = json.load(f)

print(f"Loaded {len(fixtures)} fixtures")

# Test items 4-12 on specific idx
indices_to_test = ['1', '3', '5', '6', '10', '12', '13', '14', '16', '17', '19', '29', '30', '31', '34', '35', '43', '44', '45', '48', '51', '56', '57', '58', '59', '60', '62', '63', '68', '69', '70', '71', '72', '76', '77', '79', '80', '83', '85', '87', '89', '93', '94', '97', '98', '105', '108', '110', '111']
print(f"Checking {len(indices_to_test)} targeted indices: {indices_to_test}")

