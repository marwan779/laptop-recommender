import sys
sys.path.insert(0, ".")
from app.core.classifier import ProductClassifier

test_cases = [
    # BTech
    ("L'AVVENTO Laptop Bag 15.6 inch Anti-Theft", False),
    ("HP 65W Smart AC Adapter Laptop Charger", False),
    ("Logitech Wireless Mouse M185", False),
    ("Cooling Pad for Gaming Laptop", False),
    ("HP Pavilion x360 Convertible 14-ek1009ne Laptop Intel Core i5 8GB 512GB SSD", True),
    ("Lenovo Legion 5 15IAH7H Laptop Intel Core i7 16GB RAM 512GB SSD RTX 3060", True),
    ("Dell Inspiron 3520 Laptop Intel Core i5-1235U 8GB 512GB SSD 15.6 FHD", True),
    # Noon
    ("Noon East Laptop Sleeve Bag 15.6 Inch", False),
    ("Lenovo V15 G3 IAP Laptop Intel Core i5 8GB 512GB SSD", True),
    # TwoB
    ("L'AVVENTO (BG937) Business & Travel Backpack Anti-Theft Back", False),
    ("E-train (BG53U) Backpack Bag Up to 15.6 - Purple", False),
    ("HP 65W Smart AC Adapter Charger", False),
    ("Redragon Wireless Gaming Mouse", False),
    (
        "HP OmniBook 5 Flip 14-km0007ne Laptop - Intel Core Ultra 5-322 - 16GB - 512GB SSD - Win11 + HP Smart Tank 581 All-in-One (4A8D4A)",
        True,
    ),
    # Tradeline
    ("Apple Magic Mouse - White", False),
    ("Apple 70W USB-C Power Adapter Charger", False),
    ("Incase Laptop Sleeve for 16-inch MacBook Pro", False),
    ("Apple AirPods Pro 2", False),
    ("USB-C to MagSafe 3 Cable", False),
    # Logitech keyboard
    ("Logitech Wireless Keyboard K120 USB", False),
]

all_pass = True
for title, expected in test_cases:
    valid, reason = ProductClassifier.is_valid_new_laptop(title)
    status = "PASS" if valid == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"[{status}] {title[:60]} -> got {valid} ({reason}), expected {expected}")

print("ALL PASS:", all_pass)
