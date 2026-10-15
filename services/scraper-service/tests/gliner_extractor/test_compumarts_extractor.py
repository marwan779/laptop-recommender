import pytest
from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.schema import empty_structured


def test_empty_structured_schema():
    extractor = CompumartsExtractor()
    structured, _ = extractor.extract({}, "Test Laptop")
    
    assert "identity" in structured
    assert "cpu" in structured
    assert "gpu" in structured
    assert "memory" in structured
    assert "storage" in structured
    assert "display" in structured
    assert "power_battery" in structured
    assert "connectivity" in structured
    assert "operating_system" in structured
    assert "physical" in structured
    assert "build" in structured
    assert "audio" in structured
    assert "webcam" in structured
    assert "extraction_meta" in structured
    
    meta = structured["extraction_meta"]
    assert "status" in meta
    assert "rejected" in meta
    assert "conflicts" in meta
    assert "field_sources" in meta


def test_dimension_extraction_single_rows():
    extractor = CompumartsExtractor()
    raw_specs = {
        "Height": "23.5 mm",
        "Width": "362.3 mm",
        "Depth": "239.9 mm",
        "Weight": "2.11 kg",
        "Color": "Black"
    }
    title = "Acer Nitro V 15 ANV15-52-9340 Gaming Laptop – Core i9-13900H, RTX 5050"
    structured, _ = extractor.extract(raw_specs, title)
    phys = structured["physical"]
    
    assert phys["height_mm"] == 23.5
    assert phys["width_mm"] == 362.3
    assert phys["depth_mm"] == 239.9
    assert phys["weight_kg"] == 2.11
    assert phys["color"] == "Black"


def test_mpn_rejection_of_specs():
    extractor = CompumartsExtractor()
    # Garbage spec in part number field
    raw_specs = {
        "Part Number": "1TB SSD",
        "Processor": "Intel Core Ultra 9 275HX"
    }
    structured, _ = extractor.extract(raw_specs, "Acer Predator Helios Neo 16")
    assert structured["identity"]["manufacturer_part_number"] is None
    assert any(r.get("value") == "1TB SSD" for r in structured["extraction_meta"]["rejected"])


def test_gpu_secondary_model_and_vram():
    extractor = CompumartsExtractor()
    raw_specs = {
        "Graphics": "NVIDIA GeForce RTX 5070, 8 GB GDDR7, Boost Clock up to 10 MHz, Max Power 115 W",
        "Processor": "Intel Core Ultra 9 275HX"
    }
    title = "Acer Predator Helios Neo 16 AI Gaming Laptop – Ultra 9 275HX, RTX 5070 8GB"
    structured, _ = extractor.extract(raw_specs, title)
    gpu = structured["gpu"]
    
    assert gpu["manufacturer"] == "NVIDIA"
    assert "RTX 5070" in gpu["model"]
    assert gpu["vram_gb"] == 8
    assert gpu["integrated"] is False
    # Check if Intel AI Boost or Intel Arc iGPU is captured in secondary_model if present, or None
    assert gpu["secondary_model"] is None or isinstance(gpu["secondary_model"], str)


def test_cpu_specs_db_backfill():
    extractor = CompumartsExtractor()
    raw_specs = {
        "Processor": "Intel Core Ultra 9 275HX, 24 Cores / 24 Threads"
    }
    title = "Acer Predator Helios Neo 16"
    structured, _ = extractor.extract(raw_specs, title)
    cpu = structured["cpu"]
    
    assert cpu["manufacturer"] == "Intel"
    assert cpu["model"] == "275HX"
    assert cpu["cores"] == 24
    assert cpu["threads"] == 24
    # Check if clock speeds got populated or backfilled
    if cpu["clock_boost_ghz"] is not None:
        assert isinstance(cpu["clock_boost_ghz"], (int, float))


def test_title_vs_table_conflict_detection():
    extractor = CompumartsExtractor()
    raw_specs = {
        "Memory": "16GB DDR5 SDRAM",
        "Storage": "512 GB PCIe NVMe SSD"
    }
    # Title claims 32GB RAM and 1TB SSD
    title = "Gaming Laptop – 32GB RAM, 1TB SSD"
    structured, _ = extractor.extract(raw_specs, title)
    
    # Table takes precedence
    assert structured["memory"]["capacity_gb"] == 16
    assert structured["storage"]["capacity_gb"] == 512
    
    # Conflict is recorded in extraction_meta
    conflicts = structured["extraction_meta"]["conflicts"]
    assert len(conflicts) >= 2
    fields_conflicted = [c["field"] for c in conflicts]
    assert "memory.capacity_gb" in fields_conflicted
    assert "storage.capacity_gb" in fields_conflicted


def test_product_type_and_condition_detection():
    extractor = CompumartsExtractor()
    
    # Laptop
    assert extractor.detect_product_type({}, "Acer Nitro V 15 ANV15-52-9340 Gaming Laptop") == "laptop"
    # Mouse / accessory
    assert extractor.detect_product_type({}, "Logitech G502 HERO Gaming Mouse") == "accessory"
    # Bag
    assert extractor.detect_product_type({}, "Lenovo 15.6 Casual Backpack B210") == "bag"
    # Monitor
    assert extractor.detect_product_type({}, "Samsung 27 Odyssey G5 Gaming Monitor") == "monitor"
    
    # Condition
    assert extractor.detect_condition({}, "Acer Nitro V 15 Brand New") == "new"
    assert extractor.detect_condition({}, "Dell Latitude 5420 Refurbished Laptop") == "refurbished"
    assert extractor.detect_condition({"Condition": "Open Box"}, "Lenovo ThinkPad X1") == "open_box"


def test_title_model_and_resolution_and_storage_interface():
    extractor = CompumartsExtractor()
    # Test title model extraction fallback
    t1 = "Acer Nitro V 15 ANV15-A31-R8LA Gaming Laptop | AMD Ryzen 7 170 | RTX 5060"
    s1, _ = extractor.extract({}, t1)
    assert s1["identity"]["laptop_model"] == "ANV15-A31-R8LA"

    t2 = "HP ProBook 460 G11 Business Laptop Intel Core Ultra 7 155U 16GB DDR5 RAM 512GB NVMe SSD NVIDIA GeForce RTX 2050 4GB 16-Inch FHD+ Windows 11 Pro"
    s2, _ = extractor.extract({"Display": "16-Inch"}, t2)
    assert s2["identity"]["laptop_model"] == "460 G11"
    assert s2["display"]["resolution"] == "1920 x 1200"
    assert s2["storage"]["interface"] == "NVMe"

    t3 = "HP 255 G10 AMD Ryzen 5 7535U 16GB RAM 512GB SSD"
    s3, _ = extractor.extract({}, t3)
    assert s3["identity"]["laptop_model"] == "255 G10"

    t4 = "HP 15-fd1062ne Laptop Intel Core Ultra 7 155H"
    s4, _ = extractor.extract({}, t4)
    assert s4["identity"]["laptop_model"] == "15-fd1062ne"

