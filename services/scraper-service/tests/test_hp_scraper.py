import pytest
from app.scrapers.hp import HpDateExtractor, clean_spec_text, HpBrandScraper
from app.schemas.laptop import LaptopSummary


def test_clean_spec_text():
    raw = "AMD Ryzen™ AI 9 HX 375 * * ( * ) \xa0  5.1 GHz  "
    cleaned = clean_spec_text(raw)
    assert "*" not in cleaned
    assert "\xa0" not in cleaned
    assert "AMD Ryzen™ AI 9 HX 375 5.1 GHz" in cleaned


def test_hp_date_extractor_hardware():
    # Test RTX 5080 -> 2025
    dt, yr = HpDateExtractor.extract("OMEN MAX Gaming Laptop 16", "Discrete, NVIDIA GeForce RTX 5080 Laptop GPU")
    assert yr == 2025
    assert dt == "2025-01-01"

    # Test Ryzen AI 9 -> 2024
    dt, yr = HpDateExtractor.extract("OMEN MAX 16", "AMD Ryzen AI 9 HX 375")
    assert yr == 2024
    assert dt == "2024-07-01"

    # Test Lunar Lake Intel Ultra 7 258V -> 2024
    dt, yr = HpDateExtractor.extract("HP OmniBook Ultra Flip", "Intel Core Ultra 7 258V")
    assert yr == 2024
    assert dt == "2024-09-01"

    # Test Snapdragon X Elite -> 2024
    dt, yr = HpDateExtractor.extract("HP OmniBook X 14", "Snapdragon X Elite X1E-78-100")
    assert yr == 2024
    assert dt == "2024-06-01"

    # Test 13th Gen -> 2023
    dt, yr = HpDateExtractor.extract("HP Victus 15", "Intel Core i5-13500H")
    assert yr == 2023
    assert dt == "2023-01-01"


def test_hp_date_extractor_model_gens():
    # EliteBook G2i -> 2025
    dt, yr = HpDateExtractor.extract("HP EliteBook X Flip G2i 14 inch")
    assert yr == 2025

    # EliteBook G1i -> 2024
    dt, yr = HpDateExtractor.extract("HP EliteBook X Flip G1i 14 inch")
    assert yr == 2024

    # OmniBook -> 2024
    dt, yr = HpDateExtractor.extract("HP OmniBook 5 Flip 2-in-1 Laptop")
    assert yr == 2024


def test_hp_brand_scraper_family():
    scraper = HpBrandScraper()
    assert scraper._determine_family("HP OmniBook 5 Flip 2-in-1", "/products/laptops/...") == "OmniBook"
    assert scraper._determine_family("OMEN MAX Gaming Laptop 16", "/products/laptops/...") == "OMEN"
    assert scraper._determine_family("Victus Gaming Laptop 15", "/products/laptops/...") == "Victus"
    assert scraper._determine_family("HP EliteBook X Flip G1i", "/products/laptops/...") == "EliteBook"
    assert scraper._determine_family("HP ProBook 450 G10", "/products/laptops/...") == "ProBook"
    assert scraper._determine_family("HP Laptop 15-fd0279ne", "/products/laptops/...") == "HP Essential"


def test_hp_watermark_matching():
    scraper = HpBrandScraper()
    assert scraper._matches_watermark("Victus Gaming Laptop 15-fa2005ne (B85M8EA)", "15-fa2005ne") is True
    assert scraper._matches_watermark("Victus Gaming Laptop 15-fa2005ne (B85M8EA)", "B85M8EA") is True
    assert scraper._matches_watermark("OMEN MAX Gaming Laptop 16", "Victus") is False
