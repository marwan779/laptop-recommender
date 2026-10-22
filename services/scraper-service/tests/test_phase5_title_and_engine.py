from bs4 import BeautifulSoup

from app.core.patterns.engine import PatternEngine
from app.core.patterns.models import SpecExtractionResult
from app.core.patterns.title_extractor import TitleSpecExtractor


def test_spec_extraction_result_legacy_tuple():
    res = SpecExtractionResult(
        specs={"CPU": "Intel"},
        raw_description="Desc",
        mpn="MPN123",
        model_code="MOD123",
        price_val=50000.0,
        price_str="50,000 EGP",
    )
    # Check to_legacy_tuple
    tup = res.to_legacy_tuple()
    assert tup == ({"CPU": "Intel"}, "Desc", "MPN123", "MOD123", 50000.0, "50,000 EGP")

    # Check unpacking
    specs, desc, mpn, mod, price, price_str = res
    assert specs == {"CPU": "Intel"}
    assert desc == "Desc"
    assert mpn == "MPN123"
    assert mod == "MOD123"
    assert price == 50000.0
    assert price_str == "50,000 EGP"


def test_title_extractor_modern_hardware():
    title = (
        "Acer Predator Helios Neo 16 AI Gaming Laptop – Ultra 9 275HX, "
        'RTX 5070 8GB GDDR7, 32GB DDR5, 1TB SSD, 16" QHD 240Hz, FreeDOS'
    )
    specs = TitleSpecExtractor.extract(title)

    assert specs["Brand"] == "Acer"
    assert "Ultra 9 275HX" in specs["Processor"]
    assert "RTX 5070" in specs["Graphics"]
    assert "32GB" in specs["Memory"]
    assert "1TB SSD" in specs["Storage"]
    assert "240Hz" in specs["Display"]
    assert specs["Operating System"] == "FreeDOS"


def test_title_extractor_snapdragon_and_ryzen_ai():
    # Snapdragon X Elite
    title_snap = "Dell XPS 13 Copilot+ PC – Snapdragon X Elite X1E-80-100, 16GB RAM, 512GB SSD, Windows 11"
    specs_snap = TitleSpecExtractor.extract(title_snap)
    assert specs_snap["Brand"] == "DELL"
    assert "Snapdragon X Elite" in specs_snap["Processor"]

    # Ryzen AI 9
    title_ryzen = "ASUS ROG Zephyrus G16 – AMD Ryzen AI 9 HX 370, RTX 4070, 32GB RAM, 1TB SSD"
    specs_ryzen = TitleSpecExtractor.extract(title_ryzen)
    assert specs_ryzen["Brand"] == "ASUS"
    assert "Ryzen AI 9 HX 370" in specs_ryzen["Processor"]


def test_pattern_engine_field_sources():
    soup = BeautifulSoup("<table><tr><td>Processor</td><td>Intel Core i7-13700H</td></tr></table>", "html.parser")
    title = "Gaming Laptop – 16GB RAM, 1TB SSD"
    res = PatternEngine.extract_specs(soup, title, store_key="compumarts")

    assert "title_specs" in res.model_dump()
    assert "field_sources" in res.model_dump()
    assert res.field_sources.get("Processor") == "dom"
    # RAM was missing in table, so backfilled from title
    assert res.field_sources.get("Memory") == "title"
