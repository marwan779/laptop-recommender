from unittest.mock import MagicMock
import pytest

from app.core.classifier import ProductClassifier
from app.scrapers.base import BaseBrandScraper
from app.stores.base import BaseStoreScraper


class TestProductClassifierUnits:
    """Direct behavioral tests for ProductClassifier."""

    @pytest.mark.parametrize(
        ("title", "expected_reason"),
        [
            (
                "ASUS ROG Strix 32” 1440P USB-C Curved HDR400 Gaming Monitor (XG32WCMS) QHD 280Hz",
                "non_laptop:monitor",
            ),
            ("Samsung Odyssey G7 27-inch Curved Gaming Monitor 240Hz", "non_laptop:monitor"),
            ("Dell UltraSharp U2723QE 27-inch 4K UHD Monitor", "non_laptop:monitor"),
            ("LG UltraGear 34GP83A-B 34 Inch 21:9 Curved QHD IPS Gaming Monitor", "non_laptop:monitor"),
            ("شاشة سامسونج 27 بوصة منحنية للألعاب 144 هرتز", "non_laptop:monitor"),
        ],
    )
    def test_rejects_standalone_monitors(self, title: str, expected_reason: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == expected_reason

    @pytest.mark.parametrize(
        ("title", "expected_reason"),
        [
            ("ASUS TUF GAMING GT502 HORIZON TG ARGB WHITE Mid-Tower Case", "non_laptop:pc_case"),
            ("NZXT H9 Flow Dual-Chamber ATX Mid-Tower PC Gaming Case", "non_laptop:pc_case"),
            ("Lian Li O11 Dynamic EVO RGB ATX Mid Tower Chassis", "non_laptop:pc_case"),
            ("Corsair 4000D Airflow Tempered Glass Mid-Tower ATX Case", "non_laptop:pc_case"),
            ("كيسة ألعاب احترافية مع 4 مراوح RGB", "non_laptop:pc_case"),
        ],
    )
    def test_rejects_pc_cases_and_chassis(self, title: str, expected_reason: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == expected_reason

    @pytest.mark.parametrize(
        ("title", "expected_reason"),
        [
            ("ASUS ROG STRIX B850-E WIFI GAMING MOTHERBOARD", "non_laptop:motherboard"),
            ("ASUS TUF GAMING B860-PLUS WIFI Motherboard LGA1851 DDR5", "non_laptop:motherboard"),
            ("ASUS TUF Gaming B650M-E WIFI Motherboard AM5", "non_laptop:motherboard"),
            ("MSI MAG B650 TOMAHAWK WIFI ATX Motherboard", "non_laptop:motherboard"),
            ("Gigabyte Z790 AORUS ELITE AX LGA1700 Motherboard", "non_laptop:motherboard"),
            ("مازربورد جيجابايت B760 للألعاب", "non_laptop:motherboard"),
        ],
    )
    def test_rejects_motherboards_and_chipsets(self, title: str, expected_reason: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == expected_reason

    @pytest.mark.parametrize(
        ("title", "expected_reason"),
        [
            ("Apple Mac Mini - M4 chip 10-core CPU 10-core GPU 24GB 512GB SSD", "non_laptop:desktop"),
            ("Apple Mac Studio M2 Max 32GB 512GB SSD", "non_laptop:desktop"),
            ("Apple iMac 24-inch 4.5K Retina Display M3 Chip 8-core CPU", "non_laptop:desktop"),
            ("Lenovo ThinkCentre M70q Gen 4 Tiny Desktop PC", "non_laptop:desktop"),
            ("HP OMEN 45L Gaming Desktop PC Intel Core i9-14900K RTX 4090", "non_laptop:desktop"),
            ("HP Pavilion 24 All-in-One Desktop PC Core i7 16GB RAM", "non_laptop:desktop"),
            ("كمبيوتر مكتبي ديل أوبتيبليكس الجيل الثالث عشر", "non_laptop:desktop"),
        ],
    )
    def test_rejects_desktops_all_in_ones_and_mini_pcs(self, title: str, expected_reason: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == expected_reason

    @pytest.mark.parametrize(
        ("title", "expected_reason"),
        [
            ("MSI GeForce RTX 4070 Ti SUPER 16G GAMING X SLIM Graphics Card", "non_laptop:gpu"),
            ("ASUS ROG Thor 1000W Platinum II Fully Modular Power Supply PSU", "non_laptop:psu"),
            ("Corsair iCUE H150i ELITE LCD XT Liquid CPU Cooler 360mm", "non_laptop:cooling"),
            ("ASUS ROG Ally X (2024) RC72LA Handheld Gaming Console", "non_laptop:handheld"),
            ("Lenovo Legion Go 8.8-inch QHD+ Handheld Gaming Device", "non_laptop:handheld"),
            ("Apple iPad Pro 11-inch M4 chip Standard glass 256GB Wi-Fi", "non_laptop:tablet"),
            ("Samsung Galaxy Tab S9 Ultra 14.6-inch Android Tablet 256GB", "non_laptop:tablet"),
            ("HP LaserJet Pro MFP 3103fdw All-in-One Wireless Laser Printer", "non_laptop:printer"),
        ],
    )
    def test_rejects_gpus_psus_coolers_consoles_tablets_printers(self, title: str, expected_reason: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == expected_reason

    @pytest.mark.parametrize(
        ("title", "expected_reason"),
        [
            ("USED HP Pro x360 Fortis 11 G10 2-in-1 Touch Laptop – Core i5-1230U", "used_or_refurbished"),
            ("Used HP ZBook 17 G6 Workstation Laptop – Core i5-9400H 32GB RAM", "used_or_refurbished"),
            ("USED Dell Latitude 7410 – Core i5-10310U – 8GB RAM – 256GB SSD", "used_or_refurbished"),
            ("as new Apple MacBook Pro 2019 Touchbar i9-9980HK 2.90GHz 15.4\" Retina", "used_or_refurbished"),
            ("Lenovo ThinkPad X1 Carbon Gen 9 Like New with original charger", "used_or_refurbished"),
            ("Apple MacBook Air 13-inch M1 - Renewed Grade A", "used_or_refurbished"),
            ("Lenovo ThinkPad T14 Gen 2 (Refurbished)", "used_or_refurbished"),
            ("Dell XPS 13 9310 Open Box with full warranty", "used_or_refurbished"),
            ("لاب توب ديل لاتيتيود 5490 كور اي 5 مستعمل وارد دبي", "used_or_refurbished"),
            ("لابتوب اتش بي زد بوك كسر زيرو بالكرتونة", "used_or_refurbished"),
            ("لاب توب لينوفو ثينك باد استيراد الخارج بحالة الزيرو", "used_or_refurbished"),
            ("لاب توب ديل لاتيتيود بحالة الجديد بالكرتونة", "used_or_refurbished"),
        ],
    )
    def test_rejects_used_refurbished_open_box(self, title: str, expected_reason: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == expected_reason
        assert ProductClassifier.is_used_or_refurbished(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "Lenovo 15.6 Laptop Everyday Backpack B210 Black",
            "HP Prelude Pro 15.6-inch Recycled Backpack",
            "Logitech MX Master 3S Wireless Performance Mouse",
            "Razer DeathAdder Essential Gaming Mouse 6400 DPI",
            "Anker 65W GaN USB-C Fast Charger PowerPort III",
            "Belkin USB-C 11-in-1 Multiport Docking Station Hub",
            "حقيبة ظهر للاب توب مقاومة للماء مقاس 15.6 بوصة",
            "ماوس لاسلكي مريح مع بطارية قابلة لإعادة الشحن",
        ],
    )
    def test_rejects_standalone_accessories(self, title: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is False
        assert reason == "non_laptop:accessory"
        assert ProductClassifier.is_standalone_accessory(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            # Legitimate laptops with bundled accessories
            "ASUS Vivobook 16 X1605VA – Intel Core i7-13620H, 16GB DDR4, 512GB SSD, 16\" OLED, Includes Mouse & Bag",
            "HP Laptop 15-fd2022ne - Intel Core Ultra 7-225U - 8GB DDR5 - 512GB SSD - 15.6-inch FHD - HP Backpack Bag and HP Bluetooth Mouse",
            "HP 15-fd1063ne - Intel Core Ultra 5-125H - 8GB DDR5 - 512GB SSD - 15.6-inch FHD - HP BackPack Bag, HP Bluetooth Mouse",
            "ASUS ROG Strix G16 G614PR-RV132W Gaming Laptop – Ryzen 9 8940HX, RTX 5070 Ti, 32GB, 1TB SSD, ROG Backpack",
            "ASUS Strix SCAR 18 (2024) — CORE i9-14900HX - 32GB DDR5 - 1TB SSD - RTX 4080 - Win 11 - ROG Backpack",
            # Legitimate laptops with backlit/rgb keyboards
            "ASUS Vivobook 16 X1605VA Laptop - Intel Core i7-13620H, 16GB RAM, 512GB SSD, Backlit Keyboard, Windows 11",
            "Lenovo Legion Pro 5 16IRX9 Intel Core i7-14650HX 16GB 1TB SSD RTX 4060 4-Zone RGB Keyboard",
            # 2-in-1 convertible laptops with tablet mode
            "HP Spectre x360 2-in-1 Convertible Laptop 14-inch OLED Touchscreen Core Ultra 7",
            "Lenovo Yoga 7 2-in-1 Laptop 14-inch Touchscreen (Tablet Mode) Intel Core Ultra 5 16GB 512GB",
            "HP Envy x360 2-in-1 Touch Laptop 15.6-inch AMD Ryzen 7 16GB RAM 512GB SSD",
            # Standard legitimate brand laptops
            "Apple MacBook Air 13-inch M3 Chip 16GB Unified Memory 512GB SSD - Midnight",
            "Apple MacBook Pro 14-inch M3 Pro 18GB Unified Memory 512GB SSD - Space Black",
            "ASUS Zenbook 14 OLED UX3405MA Intel Core Ultra 7 155H 16GB 1TB SSD",
            "Lenovo ThinkPad X1 Carbon Gen 12 Intel Core Ultra 7 155U 16GB 512GB",
            "GIGABYTE AORUS 16X 2024 Gaming Laptop Intel Core i7-14650HX RTX 4070 16GB 1TB",
            # Arabic legitimate laptop descriptions
            "لاب توب لينوفو ليجن 5 شاشة 15.6 بوصة كور اي 7 16 جيجا رام 512 جيجا اس اس دي كارت شاشة ار تي اكس 4060",
            "لاب توب اتش بي بافيليون 15 كور اي 5 الجيل الثاني عشر 8 جيجا رام",
        ],
    )
    def test_accepts_valid_new_laptops_and_bundles(self, title: str):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(title)
        assert is_valid is True
        assert reason in ("valid_laptop", "valid_laptop_bundle")
        assert ProductClassifier.is_standalone_accessory(title) is False
        assert ProductClassifier.is_used_or_refurbished(title) is False

    @pytest.mark.parametrize(
        "empty_or_invalid",
        [None, "", "   ", "ab", "x"],
    )
    def test_handles_empty_and_short_titles_safely(self, empty_or_invalid):
        is_valid, reason = ProductClassifier.is_valid_new_laptop(empty_or_invalid)
        assert is_valid is False
        assert reason == "invalid_title"
        assert ProductClassifier.is_standalone_accessory(empty_or_invalid) is True
        assert ProductClassifier.is_used_or_refurbished(empty_or_invalid) is False


class TestScraperIntegrationValidation:
    """Tests integration of ProductClassifier with BaseStoreScraper and BaseBrandScraper."""

    def test_base_store_scraper_delegates_to_classifier(self):
        # Verify standalone accessory check
        assert BaseStoreScraper._is_standalone_accessory("Lenovo 15.6 Laptop Everyday Backpack B210") is True
        assert BaseStoreScraper._is_standalone_accessory("ASUS ROG Strix 32” Gaming Monitor (XG32WCMS)") is True
        assert BaseStoreScraper._is_standalone_accessory("USED Dell Latitude 5490 Laptop") is True
        # Verify valid laptop is NOT an accessory
        assert (
            BaseStoreScraper._is_standalone_accessory("ASUS Zenbook 14 OLED UX3405MA Intel Core Ultra 7 16GB 1TB")
            is False
        )

        valid, reason = BaseStoreScraper.is_valid_new_laptop("ASUS TUF GAMING GT502 Mid-Tower Case")
        assert valid is False
        assert reason == "non_laptop:pc_case"

    def test_base_brand_scraper_delegates_to_classifier(self):
        valid, reason = BaseBrandScraper.is_valid_new_laptop("ASUS ROG Swift OLED PG32UCDM Gaming Monitor")
        assert valid is False
        assert reason == "non_laptop:monitor"

        valid, reason = BaseBrandScraper.is_valid_new_laptop("ASUS ROG Ally X Handheld Console")
        assert valid is False
        assert reason == "non_laptop:handheld"

        valid, reason = BaseBrandScraper.is_valid_new_laptop("Lenovo Legion Pro 5 16IRX9 Intel Core i7 16GB")
        assert valid is True
        assert reason in ("valid_laptop", "valid_laptop_bundle")
