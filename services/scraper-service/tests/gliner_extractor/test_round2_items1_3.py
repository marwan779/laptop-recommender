"""Unit and regression tests for Round 2 Items 1-3.

Item 1: Title RAM/storage parser VRAM bleed fix (false needs_review conflicts eliminated).
Item 2: Screen size winning as RAM (idx 35 resolved).
Item 3: Cross-field consistency validator (validate_consistency).
"""

import json
from pathlib import Path
import pytest

from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.validators import (
    extract_title_ram,
    extract_title_storage,
    validate_consistency,
)


@pytest.fixture
def fixtures_data():
    fixture_path = Path(__file__).parents[1] / "fixtures" / "regression_laptops.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_extract_title_ram_excludes_gpu_vram():
    # VRAM like RTX 5070 8GB must not be taken as RAM
    t1 = "MSI Cyborg 15 Max Gaming Laptop Intel Core i7-13620H RTX 5070 8GB 16GB DDR5 512GB SSD"
    assert extract_title_ram(t1) == 16

    t2 = "Lenovo LOQ 15 Gaming Laptop RTX 5070 8GB GDDR7 16GB RAM 512GB SSD"
    assert extract_title_ram(t2) == 16

    t3 = "Acer Predator Helios 16 Intel Ultra 9 32GB RAM 1TB SSD GeForce RTX 5090 24GB"
    assert extract_title_ram(t3) == 32

    # Screen size like 16" or 16-inch must not be taken as RAM
    t4 = "GIGABYTE AERO 16-inch QHD Intel Core i7 16GB DDR5 1TB SSD"
    assert extract_title_ram(t4) == 16


def test_extract_title_storage_excludes_ram():
    # 128GB LPDDR5X must not be taken as storage
    t1 = "ASUS ProArt PX13 Ryzen AI MAX+ 395 128GB LPDDR5X 1TB SSD 13.3 OLED Touch"
    assert extract_title_storage(t1) == 1024

    t2 = "Lenovo ThinkPad X1 16GB RAM 512GB SSD"
    assert extract_title_storage(t2) == 512


def test_title_ram_storage_conflicts_on_fixtures(fixtures_data):
    extractor = CompumartsExtractor()
    mem_conflicts = []
    stg_conflicts = []

    for idx_str, item in fixtures_data.items():
        title = item.get("title", "")
        specs = item.get("specs", {})
        meta = item.get("metadata", {})
        struct, _ = extractor.extract(specs, title=title, metadata=meta)
        for c in struct.get("extraction_meta", {}).get("conflicts", []):
            if c.get("field") == "memory.capacity_gb":
                mem_conflicts.append((idx_str, c))
            elif c.get("field") == "storage.capacity_gb":
                stg_conflicts.append((idx_str, c))

    # Over the whole dataset, fewer than 8 memory conflicts remain
    assert len(mem_conflicts) < 8
    conflict_indices = {idx for idx, _ in mem_conflicts}

    # Genuine conflicts MUST still be reported: idx 10, 35, 64
    assert "10" in conflict_indices
    assert "35" in conflict_indices
    assert "64" in conflict_indices

    # idx 62 storage conflict must be gone
    stg_conflict_indices = {idx for idx, _ in stg_conflicts}
    assert "62" not in stg_conflict_indices


def test_idx_35_screen_size_as_ram_resolution(fixtures_data):
    extractor = CompumartsExtractor()
    item = fixtures_data["35"]
    struct, _ = extractor.extract(item["specs"], title=item["title"], metadata=item["metadata"])

    # idx 35 RAM must be 32 (from title), not 16
    assert struct["memory"]["capacity_gb"] == 32

    # Conflict reason must be "table_value_looks_like_screen_size"
    mem_c = [c for c in struct["extraction_meta"]["conflicts"] if c["field"] == "memory.capacity_gb"]
    assert len(mem_c) == 1
    assert mem_c[0]["reason"] == "table_value_looks_like_screen_size"
    assert mem_c[0]["chosen"] == 32


def test_validate_consistency_threads_cores_ratio():
    structured = {
        "cpu": {"cores": 8, "threads": 7, "model": None},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    assert structured["cpu"]["threads"] is None
    assert any(r["rule"] == "consistency:threads_cores_ratio" for r in rejs)


def test_validate_consistency_cpu_mfg_line_mismatch():
    structured = {
        "cpu": {"manufacturer": "Qualcomm", "line": "Ryzen 5", "model": None},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    assert structured["cpu"]["line"] is None
    assert any(r["rule"] == "consistency:cpu_mfg_line_mismatch" for r in rejs)


def test_validate_consistency_aspect_ratio_reduced():
    structured = {
        "display": {"resolution": "2560 x 1440", "aspect_ratio": "16:10"},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    # 2560x1440 reduced is 16:9, text 16:10 is rejected
    assert structured["display"]["aspect_ratio"] == "16:9"
    assert any(r["rule"] == "consistency:aspect_ratio_mismatch" for r in rejs)


def test_validate_consistency_form_factor_nvme_incompatible():
    structured = {
        "storage": {"form_factor": "2.5", "interface": "PCIe 4.0 NVMe"},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    assert structured["storage"]["form_factor"] is None
    assert any(r["rule"] == "consistency:form_factor_nvme_incompatible" for r in rejs)


def test_validate_consistency_dgpu_vram_table():
    structured = {
        "gpu": {"model": "GeForce RTX 5060 Laptop GPU", "vram_gb": 16, "integrated": False},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    # RTX 5060 has 8GB VRAM in authoritative DB
    assert structured["gpu"]["vram_gb"] == 8
    assert any(r["rule"] == "consistency:dgpu_vram_invalid_for_model" for r in rejs)


def test_validate_consistency_max_ram_unverified():
    structured = {
        "memory": {"capacity_gb": 16, "max_supported_gb": 16, "memory_type": "DDR5"},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    assert structured["memory"]["max_supported_gb"] is None
    assert any(r["rule"] == "consistency:max_ram_equals_installed_unverified" for r in rejs)


def test_validate_consistency_adapter_matches_battery_wh():
    structured = {
        "power_battery": {"battery_capacity_wh": 41.0, "power_adapter_w": 41},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    assert structured["power_battery"]["power_adapter_w"] is None
    assert any(r["rule"] == "consistency:adapter_matches_battery_wh" for r in rejs)


def test_validate_consistency_cpu_spec_db_lookup():
    structured = {
        "cpu": {"model": "240H", "cores": 10, "threads": 10},
        "extraction_meta": {"rejected": []},
    }
    rejs = validate_consistency(structured)
    # Core 7 240H has 10 cores, 16 threads in authoritative DB
    assert structured["cpu"]["cores"] == 10
    assert structured["cpu"]["threads"] == 16

