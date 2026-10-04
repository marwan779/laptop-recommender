import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

USED_PATTERN = re.compile(
    r"\b(used|refurbished|renewed|open[- ]?box|pre[- ]?owned|second[- ]?hand|secondhand|b[- ]?grade|c[- ]?grade)\b|"
    r"(مستعمل|استعمال|استيراد|كسر\s*زيرو|مجدد|معاد\s*تصنيعه|مفتوح\s*العلبة|مفتوح\s*الكرتونة|فرز\s*ثان|فرز\s*تاني)",
    re.IGNORECASE,
)

HARD_VETO_PATTERNS = [
    (
        "monitor",
        re.compile(
            r"\b(gaming\s+monitor|curved\s+monitor|portable\s+monitor|oled\s+monitor|ultrawide\s+monitor|"
            r"ips\s+monitor|smart\s+monitor|lcd\s+monitor|led\s+monitor|displaywidget|tripod\s+socket)\b|"
            r"\bmonitors?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pc_case",
        re.compile(
            r"\b(pc\s+case|gaming\s+case|computer\s+case|atx\s+case|micro[- ]?atx\s+case|itx\s+case|"
            r"mid[- ]?tower|full[- ]?tower|mini[- ]?tower|chassis|tempered\s+glass\s+case|gt502|"
            r"h9\s+flow|h7\s+flow|h5\s+flow|o11\s+dynamic|lancool|4000d|5000d)\b|"
            r"(كيسة|كيسه|شاسيه|صندوق\s*كمبيوتر)",
            re.IGNORECASE,
        ),
    ),
    (
        "motherboard",
        re.compile(
            r"\b(motherboard|mainboard|mobo)\b|"
            r"\b(b650m?|b760m?|b850m?|b860m?|z790m?|z890m?|x670e?|x870e?|a620m?|h610m?)\b|"
            r"\b(lga1700|lga1851|am5\s+socket|socket\s+am5|socket\s+am4)\b|"
            r"(مازربورد|لوحة\s*أم|لوحه\s*ام|لوحة\s*رئيسية|لوحه\s*رئيسيه)",
            re.IGNORECASE,
        ),
    ),
    (
        "desktop",
        re.compile(
            r"\b(desktop(\s+pc)?|all[- ]in[- ]one|aio\s+pc|mini\s+pc|nuc|tower\s+pc|workstation\s+pc|"
            r"gaming\s+desktop|gaming\s+pc|desktop\s+computer|optiplex|thinkcentre|ideacentre|elitedesk|prodesk)\b|"
            r"\b(mac\s+mini|mac\s+studio|mac\s+pro|imac)\b|"
            r"(كمبيوتر\s*مكتبي|جهاز\s*مكتبي|كمبيوتر\s*شامل|ميني\s*بي\s*سي|حاسوب\s*مكتبي)",
            re.IGNORECASE,
        ),
    ),
    (
        "gpu",
        re.compile(
            r"\b(graphics\s+card|video\s+card|vga\s+card|graphic\s+card)\b|"
            r"(كارت\s*شاشة|كرت\s*شاشة|بطاقة\s*رسوميات|كارت\s*شاشه)",
            re.IGNORECASE,
        ),
    ),
    (
        "psu",
        re.compile(
            r"\b(power\s+supply|modular\s+psu)\b|"
            r"(باور\s*سبلاي|مزود\s*طاقة|مزود\s*طاقه)",
            re.IGNORECASE,
        ),
    ),
    (
        "cooling",
        re.compile(
            r"\b(liquid\s+cooler|aio\s+cooler|cpu\s+cooler|case\s+fan|argb\s+fan|water\s+cooling|thermal\s+paste)\b|"
            r"(مبرد\s*مائي|مروحة\s*تبريد|تبريد\s*مائي|معجون\s*حراري)",
            re.IGNORECASE,
        ),
    ),
    (
        "handheld",
        re.compile(
            r"\b(rog\s+ally(\s*x)?|legion\s+go|steam\s+deck|msi\s+claw|nintendo\s+switch|playstation|ps5|ps4|xbox)\b|"
            r"(بلايستيشن|اكسبوكس|جهاز\s*ألعاب\s*محمول)",
            re.IGNORECASE,
        ),
    ),
    (
        "tablet",
        re.compile(
            r"\b(ipad(\s+(pro|air|mini))?|galaxy\s+tab|lenovo\s+tab|xiaomi\s+pad|redmi\s+pad|"
            r"drawing\s+tablet|graphics\s+tablet|pen\s+tablet|wacom|tablet)\b|"
            r"(تابلت|ايباد|لوح\s*رقمي)",
            re.IGNORECASE,
        ),
    ),
    (
        "printer",
        re.compile(
            r"\b(printer|laserjet|inkjet|pixma|scanner|projector|toner|cartridge)\b|"
            r"(طابعة|طابعه|سكانر|ماسح\s*ضوئي|بروجكتور|حبر\s*طابعة)",
            re.IGNORECASE,
        ),
    ),
]

ACCESSORY_PATTERN = re.compile(
    r"\b(backpack|laptop\s+bag|briefcase|sleeve|laptop\s+stand|cooling\s+pad|docking\s+station|docking|"
    r"usb\s+hub|type-c\s+hub|mousepad|mouse\s+pad|headset|earphones|headphones|earbuds|webcam|microphone|"
    r"flash\s+drive|usb\s+drive|power\s+bank|stylus\s+pen|screen\s+protector|charger|adapter|cable|mouse)\b|"
    r"(حقيبة|شنطة|شنطه|جراب|حامل\s*لاب|قاعدة\s*تبريد|شاحن|كابل|سلك|ماوس\s*باد|سماعة|سماعات|كاميرا\s*ويب|فلاشة|فلاشه)",
    re.IGNORECASE,
)

CPU_PATTERN = re.compile(
    r"\b(i[3579]|ryzen|core\s*ultra|intel|amd|celeron|athlon|m[1-4](\s+pro|\s+max)?|snapdragon)\b",
    re.IGNORECASE,
)
SPECS_PATTERN = re.compile(
    r"\b(\d+\s*gb|ssd|nvme|fhd|ips|oled|wuxga|ddr\d?|rtx|gtx|radeon|geforce|\d{1,2}(\.\d)?[\"\'\s-]*inch)\b",
    re.IGNORECASE,
)
LAPTOP_TERMS_PATTERN = re.compile(
    r"\b(laptop|notebook|macbook|2-in-1|convertible|zenbook|vivobook|thinkpad|ideapad|legion|loq|victus|omen|"
    r"tuf|rog|predator|nitro|latitude|inspiron|vostro|probook|elitebook|envy|spectre|pavilion|swift|aspire|gram|surface)\b|"
    r"(لاب\s*توب|لابتوب|حاسوب\s*محمول|نوت\s*بوك)",
    re.IGNORECASE,
)


def classify(title: str) -> tuple[bool, str]:
    if not title or len(title.strip()) < 3:
        return False, "invalid_title"

    # 1. Used / Refurbished veto
    if USED_PATTERN.search(title):
        return False, "used_or_refurbished"

    # 2. Hard veto for non-laptop machines / components / monitors
    for cat, pat in HARD_VETO_PATTERNS:
        if pat.search(title):
            if cat == "tablet":
                # Exception: 2-in-1 / convertible laptops with tablet mode
                if re.search(r"\b(laptop|notebook|2-in-1|convertible|x360|yoga|flex)\b", title, re.IGNORECASE):
                    continue
            return False, f"non_laptop:{cat}"

    # 3. Accessory check (allowing laptop bundles)
    if ACCESSORY_PATTERN.search(title):
        t = title.lower()
        has_cpu = bool(CPU_PATTERN.search(t))
        has_specs = bool(SPECS_PATTERN.search(t))
        has_laptop_term = bool(LAPTOP_TERMS_PATTERN.search(t))

        if (has_cpu and has_specs) or (has_laptop_term and (has_cpu or has_specs)):
            return True, "valid_laptop_bundle"
        return False, "non_laptop:accessory"

    return True, "valid_laptop"


if __name__ == "__main__":
    test_files = [
        "scraping-results/tests/store_compumarts.json",
        "scraping-results/tests/store_twob.json",
        "scraping-results/tests/store_sigma.json",
        "scraping-results/tests/store_elbadr.json",
        "scraping-results/tests/store_tradeline.json",
    ]

    for tf in test_files:
        data = json.load(open(tf, encoding="utf-8"))
        items = data.get("products", [])
        filtered = []
        for item in items:
            valid, reason = classify(item["title"])
            if not valid:
                filtered.append((item["title"], reason))
        print(f"\n=== {tf} ===")
        print(f"Filtered {len(filtered)} / {len(items)}")
        for t, r in filtered:
            print(f"  [{r}] {t}")
