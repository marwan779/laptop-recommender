import re
from typing import Any


class ProductClassifier:
    """Classifies products and detects non-laptop devices, accessories, and used/refurbished items.

    Ensures that only genuine, brand-new laptops are ingested into the database.
    Applies across both retail store scrapers and official brand scrapers.
    """

    # Used / Refurbished / Pre-owned patterns (English & Arabic)
    USED_PATTERN = re.compile(
        r"\b(used|refurbished|renewed|open[- ]?box|pre[- ]?owned|second[- ]?hand|secondhand|b[- ]?grade|c[- ]?grade)\b|"
        r"(مستعمل|استعمال|استيراد|كسر\s*زيرو|مجدد|معاد\s*تصنيعه|مفتوح\s*العلبة|مفتوح\s*الكرتونة|فرز\s*ثان|فرز\s*تاني)",
        re.IGNORECASE,
    )

    # Hard-veto non-laptop devices and components that can never be accepted as laptops
    HARD_VETO_PATTERNS: list[tuple[str, re.Pattern]] = [
        (
            "printer",
            re.compile(
                r"\b(printer|laserjet|inkjet|pixma|scanner|projector|toner|cartridge)\b|"
                r"(طابعة|طابعه|سكانر|ماسح\s*ضوئي|بروجكتور|حبر\s*طابعة)",
                re.IGNORECASE,
            ),
        ),
        (
            "monitor",
            re.compile(
                r"\b(gaming\s+monitor|curved\s+monitor|portable\s+monitor|oled\s+monitor|ultrawide\s+monitor|"
                r"ips\s+monitor|smart\s+monitor|lcd\s+monitor|led\s+monitor|displaywidget|tripod\s+socket)\b|"
                r"\bmonitors?\b|"
                r"(شاشة|شاشه|شاشات)",
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
    ]

    # Standalone accessories vs laptop bundles
    ACCESSORY_PATTERN = re.compile(
        r"\b(backpack|laptop\s+bag|briefcase|sleeve|laptop\s+stand|cooling\s+pad|docking\s+station|docking|"
        r"usb\s+hub|type-c\s+hub|mousepad|mouse\s+pad|headset|earphones|headphones|earbuds|webcam|microphone|"
        r"flash\s+drive|usb\s+drive|power\s+bank|stylus\s+pen|screen\s+protector|charger|adapter|cable|mouse|keyboard|"
        r"router|extender|hard\s+drive|external\s+hard|external\s+hdd|memory\s+card|sd\s+card|microsd|"
        r"airpods|apple\s+pencil|magic\s+mouse|magsafe)\b|"
        r"(حقيبة|شنطة|شنطه|جراب|حامل\s*لاب|قاعدة\s*تبريد|شاحن|كابل|سلك|ماوس\s*باد|سماعة|سماعات|كاميرا\s*ويب|فلاشة|فلاشه)",
        re.IGNORECASE,
    )

    # Core laptop hardware and form factor indicators used to recognize bundles
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

    # Backlit/layout exception pattern for keyboard
    KEYBOARD_LAYOUT_PATTERN = re.compile(
        r"\b(backlit|rgb|english|arabic|layout|island-style|chiclet)\b",
        re.IGNORECASE,
    )

    @classmethod
    def is_valid_new_laptop(cls, title: str | None) -> tuple[bool, str]:
        """Validate whether a product title represents a legitimate, brand-new laptop.

        Returns:
            (True, "valid_laptop") or (True, "valid_laptop_bundle") if valid.
            (False, "<reason>") if disqualified.
        """
        if not title or len(title.strip()) < 3:
            return False, "invalid_title"

        t = title.strip()

        # 1. Used / Refurbished veto
        if cls.USED_PATTERN.search(t):
            return False, "used_or_refurbished"

        # 2. Hard veto for non-laptop machines, components, displays, etc.
        for cat, pat in cls.HARD_VETO_PATTERNS:
            if pat.search(t):
                # Exception: 2-in-1 convertible laptops with tablet mode
                if cat == "tablet":
                    if re.search(r"\b(laptop|notebook|2-in-1|convertible|x360|yoga|flex)\b", t, re.IGNORECASE):
                        continue
                # Exception: Arabic laptop titles mentioning internal screen (e.g. شاشة 15.6 بوصة)
                if cat == "monitor":
                    if not re.search(r"(شاشة\s*(كمبيوتر|ألعاب|عرض|منحنية)|gaming\s*monitor)", t, re.IGNORECASE):
                        if cls.LAPTOP_TERMS_PATTERN.search(t):
                            continue
                # Exception: Laptop titles mentioning internal GPU (e.g. كارت شاشة RTX 4060)
                if cat == "gpu":
                    if cls.LAPTOP_TERMS_PATTERN.search(t):
                        continue
                # Exception: Laptop bundling an All-in-One printer (e.g. Laptop + All-in-One Printer)
                if cat == "desktop":
                    if re.search(r"\b(laptop|notebook)\b", t, re.IGNORECASE) and re.search(
                        r"\b(smart\s*tank|printer|deskjet|laserjet|inkjet)\b", t, re.IGNORECASE
                    ):
                        continue
                return False, f"non_laptop:{cat}"

        # 3. Accessory check (allowing legitimate laptops bundled with accessories)
        if cls.ACCESSORY_PATTERN.search(t):
            t_lower = t.lower()

            # Special case: keyboard layout / backlit descriptors (e.g. "backlit keyboard", "keyboard arabic", "layout")
            if "keyboard" in t_lower and any(
                k in t_lower for k in ["keyboard english", "keyboard arabic", "backlit", "rgb", "layout"]
            ):
                t_without_keyboard = re.sub(r"\bkeyboard\b", " ", t_lower)
                if not cls.ACCESSORY_PATTERN.search(t_without_keyboard):
                    return True, "valid_laptop"

            has_cpu = bool(cls.CPU_PATTERN.search(t_lower))
            has_specs = bool(cls.SPECS_PATTERN.search(t_lower))

            # A legitimate laptop bundling accessories MUST have a real CPU and specs
            # (e.g. "Vivobook 16 i7 16GB 512GB Includes Mouse & Bag")
            # Sleeves or bags mentioning screen sizes or laptop brands without CPU are NOT laptops
            if has_cpu and has_specs:
                return True, "valid_laptop_bundle"
            return False, "non_laptop:accessory"

        return True, "valid_laptop"

    @classmethod
    def is_used_or_refurbished(cls, title: str | None) -> bool:
        """Check if product title indicates used, refurbished, or renewed condition."""
        if not title:
            return False
        return bool(cls.USED_PATTERN.search(title))

    @classmethod
    def is_standalone_accessory(cls, title: str | None) -> bool:
        """Convenience method returning True if title is NOT a valid new laptop."""
        valid, _ = cls.is_valid_new_laptop(title)
        return not valid
