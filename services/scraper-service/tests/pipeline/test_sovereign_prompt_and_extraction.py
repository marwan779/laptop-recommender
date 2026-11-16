"""Tests for dual-source prompt payloads, contradiction overrides, and post-validation."""

from __future__ import annotations

from app.domain.catalog.sovereign_prompt import (
    build_batch_messages,
    build_dual_source_payload,
    extract_batch_results,
    validate_and_normalize_extracted_specs,
)
from app.pipeline.schema import empty_laptop_specifications


def test_dual_source_payload_includes_store_raw_specs_and_compact_icecat() -> None:
    laptop = {
        "canonical_id": "laptop_lenovo_ideapad_slim_83k101ered_16gb_512gb",
        "brand": "Lenovo",
        "laptop_family": "IdeaPad Slim",
        "laptop_model": "83K101ERED",
        "title": "Lenovo IdeaPad Slim 3 83K101ERED",
        "mpn": "83K101ERED",
        "icecat_match_type": "EXACT_MATCH",
        "icecat_mpn": "83K100V8IX",
        "raw_store_context": {
            "source_table": {"Memory": "16GB DDR5 4800Hz", "Max Memory": "Not upgradable"},
            "raw_description": "16GB DDR5 4800Hz | Max Memory: Not upgradable",
            "store_slot_count": 0,
        },
        "specs": empty_laptop_specifications(),
    }
    icecat_specs = {
        "memory": {"capacity_gb": 8, "max_supported_gb": 24, "is_soldered": False, "raw_spec": "ignore me"},
        "power_battery": {"battery_capacity_wh": 60.0, "power_adapter_w": 65.0},
    }

    payload = build_dual_source_payload(laptop, icecat_specs)
    assert payload["identity"]["mpn"] == "83K101ERED"
    assert payload["icecat_context"]["icecat_mpn"] == "83K100V8IX"
    assert "raw_spec" not in payload["icecat_context"]["memory"]
    assert payload["icecat_context"]["power_battery"]["battery_capacity_wh"] == 60.0
    assert payload["store_raw_specs"]["source_table"]["Max Memory"] == "Not upgradable"


def test_validate_and_normalize_preserves_store_contradiction_fixes_and_icecat_gaps() -> None:
    # Covers 83K101ERED soldered RAM, P1503CVA/83S50035ED 2 M.2 slots, S5408QA mm height,
    # UX3405CA keyboard backlight, A14-UX3407NA USB4, G614PR 5200 MHz, and Icecat battery/TDP gaps.
    det = empty_laptop_specifications()
    det["cpu"]["raw_spec"] = "Intel Core i7-14650HX"
    det["gpu"]["raw_spec"] = "NVIDIA GeForce RTX 4060 8GB"

    llm_output = {
        "memory": {
            "capacity_gb": 16,
            "memory_type": "DDR5",
            "speed": "5200 MHz",
            "is_soldered": True,
            "slot_count": 0,
            "max_supported_gb": 16,
        },
        "storage": {
            "capacity_gb": 1024,
            "storage_type": "NVMe SSD",
            "slot_count": 2,
        },
        "physical": {
            "height_front_mm": "14.9",
            "height_rear_mm": "16.9",
            "weight_kg": "1.39",
        },
        "build_security": {"has_backlit_keyboard": True},
        "connectivity": {"ports": ["2x USB 4.0 Gen 3 Type-C (40Gbps)"]},
        "power_battery": {"battery_capacity_wh": 75.0, "power_adapter_w": 100.0},
        "gpu": {"model": "GeForce RTX 4060", "vram_gb": 8, "tdp_w": 115.0},
        "conflicts_resolved": ["Store Not upgradable overrides Icecat 24GB max"],
    }

    normalized = validate_and_normalize_extracted_specs(
        llm_output,
        deterministic_specs=det,
        title="ASUS Zenbook 14 UX3405CA Core i7-14650HX RTX 4060",
    )

    assert normalized["memory"]["is_soldered"] is True
    assert normalized["memory"]["slot_count"] == 0
    assert normalized["memory"]["max_supported_gb"] == 16
    assert normalized["memory"]["speed"] == "5200 MHz"
    assert normalized["storage"]["slot_count"] == 2
    assert normalized["physical"]["height_front_mm"] == 14.9
    assert normalized["physical"]["height_rear_mm"] == 16.9
    assert normalized["build_security"]["has_backlit_keyboard"] is True
    assert normalized["connectivity"]["ports"] == ["2x USB 4.0 Gen 3 Type-C (40Gbps)"]
    assert normalized["power_battery"]["battery_capacity_wh"] == 75.0
    assert normalized["gpu"]["tdp_w"] == 115.0
    assert normalized["conflicts_resolved"] == ["Store Not upgradable overrides Icecat 24GB max"]


def test_micro_batch_prompt_and_extraction_roundtrip() -> None:
    p1 = build_dual_source_payload({"canonical_id": "cid_1", "title": "Laptop 1"}, None)
    p2 = build_dual_source_payload({"canonical_id": "cid_2", "title": "Laptop 2"}, None)
    msgs = build_batch_messages([p1, p2])
    assert len(msgs) == 2
    assert "cid_1" in msgs[1]["content"] and "cid_2" in msgs[1]["content"]

    parsed = {"results": {"cid_1": {"memory": {"capacity_gb": 16}}, "cid_2": {"storage": {"slot_count": 2}}}}
    extracted = extract_batch_results(parsed, ["cid_1", "cid_2"])
    assert set(extracted.keys()) == {"cid_1", "cid_2"}
    assert extracted["cid_1"]["memory"]["capacity_gb"] == 16


def test_validate_fixes_ethernet_microphone_clear_contract_bundle_and_noise() -> None:
    det = empty_laptop_specifications()
    det["identity"]["color"] = "White"
    det["identity"]["is_bundle"] = False
    det["connectivity"]["ethernet"] = "Gigabit Ethernet (RJ-45, 10/100/1000 Mbps)"
    det["connectivity"]["ports"] = [
        "120 Hz refresh rate",
        "Wi-Fi 7(802.11be) (Triple band)2*2 Wireless Card",
        "Bluetooth 5.4",
        "1x RJ-45 Ethernet Port",
    ]
    det["audio_webcam"]["raw_spec"] = "Audio: Built-in Stereo Speakers and Array Microphone"
    det["build_security"]["security_features"] = ["TPM 2.0", "No fingerprint reader"]

    llm_output = {
        "identity": {"color": None},
        "connectivity": {"ports": ["1x RJ-45 Ethernet Port", "120 Hz refresh rate", "Bluetooth 5.4"]},
        "audio_webcam": {"microphone": True},
    }

    normalized = validate_and_normalize_extracted_specs(
        llm_output,
        deterministic_specs=det,
        title="LENOVO IdeaPad Slim 3 - White Backlit - Dos - Mouse + BAG",
    )

    assert normalized["connectivity"]["ethernet"] is True
    assert normalized["connectivity"]["ethernet_speed"] == "1 Gbps"
    assert normalized["connectivity"]["ports"] == ["1x RJ-45 Ethernet Port"]
    assert normalized["audio_webcam"]["microphone"] == "Built-in microphone"
    assert normalized["identity"]["is_bundle"] is True
    assert normalized["identity"]["color"] is None
    assert normalized["build_security"]["security_features"] == ["TPM 2.0"]


def test_explicit_empty_ports_clears_bad_deterministic_ports() -> None:
    det = empty_laptop_specifications()
    det["connectivity"]["ports"] = ["120 Hz refresh rate"]

    normalized = validate_and_normalize_extracted_specs(
        {"connectivity": {"ports": []}},
        deterministic_specs=det,
        title="Dell Alienware 16 Aurora AC16250",
    )

    assert normalized["connectivity"]["ports"] == []
