import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.llm_auditor import FieldCorrection, GeminiAuditor, cast_value_to_field_type
from pipeline.physical_validator import PhysicalValidator


def test_type_casting():
    assert cast_value_to_field_type("memory.slot_count", "0") == 0
    assert cast_value_to_field_type("memory.slot_count", 0) == 0
    assert cast_value_to_field_type("memory.slot_count", "null") is None
    assert cast_value_to_field_type("memory.is_soldered", "true") is True
    assert cast_value_to_field_type("memory.is_soldered", "false") is False
    assert cast_value_to_field_type("display.size_inches", "15.6") == 15.6
    assert cast_value_to_field_type("display.color_gamut", "None") is None
    assert cast_value_to_field_type("display.color_gamut", "100% sRGB") == "100% sRGB"
    print("test_type_casting: PASSED")


def test_physical_validator_guarding():
    # Attempting to set display.color_gamut to Mica silver should be rejected by PhysicalValidator
    is_valid, val, err = PhysicalValidator.validate_field("display.color_gamut", "Mica silver")
    assert not is_valid
    assert "color_gamut_contains_chassis_color" in err

    # Valid gamut
    is_valid, val, err = PhysicalValidator.validate_field("display.color_gamut", "100% sRGB")
    assert is_valid
    assert val == "100% sRGB"

    # Setting color_gamut to None (clearing it) should be valid
    is_valid, val, err = PhysicalValidator.validate_field("display.color_gamut", None)
    assert is_valid
    assert val is None

    # Memory slots: 0 is valid for soldered
    is_valid, val, err = PhysicalValidator.validate_field("memory.slot_count", 0)
    assert is_valid
    assert val == 0

    print("test_physical_validator_guarding: PASSED")


def test_apply_corrections_mock():
    # Mock auditor without real API key to test local patching engine
    auditor = object.__new__(GeminiAuditor)

    # Test 1: Lenovo Yoga 7 (memory.slot_count 2 -> 0, is_soldered -> True)
    laptop_yoga = {
        "url": "https://compumarts.com/lenovo-yoga-7",
        "specs": {
            "memory": {"slot_count": 2, "is_soldered": True, "capacity_gb": 32},
            "cpu": {"line": "Core Ultra 7"},
        }
    }
    corrections_yoga = [
        FieldCorrection(
            field_path="memory.slot_count",
            current_value=2,
            corrected_value=0,
            reason="Memory is soldered with no physical slots",
            evidence_quote="Memory soldered to systemboard, no slots, dual-channel"
        ),
        # Attempt to touch locked CPU field (must be skipped!)
        FieldCorrection(
            field_path="cpu.line",
            current_value="Core Ultra 7",
            corrected_value="Hacked CPU",
            reason="Illegal attempt to modify locked CPU",
            evidence_quote="None"
        )
    ]
    applied = auditor.apply_corrections(laptop_yoga, corrections_yoga)
    assert len(applied) == 1
    assert applied[0]["field_path"] == "memory.slot_count"
    assert applied[0]["old_value"] == 2
    assert applied[0]["new_value"] == 0
    assert laptop_yoga["specs"]["memory"]["slot_count"] == 0
    assert laptop_yoga["specs"]["memory"]["is_soldered"] is True
    assert laptop_yoga["specs"]["cpu"]["line"] == "Core Ultra 7"  # Locked CPU untouched!

    # Test 2: MSI Thin 15 (storage.form_factor "2.5-inch" -> "M.2")
    laptop_msi = {
        "url": "https://compumarts.com/msi-thin-15",
        "specs": {
            "storage": {"capacity_gb": 1024, "form_factor": "2.5-inch", "storage_type": "SSD"}
        }
    }
    corrections_msi = [
        FieldCorrection(
            field_path="storage.form_factor",
            current_value="2.5-inch",
            corrected_value="M.2",
            reason="Installed primary drive is NVMe PCIe Gen4 SSD, 2.5-inch is expansion bay only",
            evidence_quote="1TB NVMe PCIe Gen4 SSD (plus 1x 2.5\" SATA expansion slot)"
        )
    ]
    applied = auditor.apply_corrections(laptop_msi, corrections_msi)
    assert len(applied) == 1
    assert applied[0]["new_value"] == "M.2"
    assert laptop_msi["specs"]["storage"]["form_factor"] == "M.2"

    # Test 3: HP Victus 15 (display.color_gamut "Mica silver" -> None)
    laptop_victus = {
        "url": "https://compumarts.com/hp-victus-15",
        "specs": {
            "display": {"size_inches": 15.6, "color_gamut": "Mica silver"}
        }
    }
    corrections_victus = [
        FieldCorrection(
            field_path="display.color_gamut",
            current_value="Mica silver",
            corrected_value=None,
            reason="Mica silver is exterior chassis color, not display color gamut",
            evidence_quote="Colors: Mica silver"
        )
    ]
    applied = auditor.apply_corrections(laptop_victus, corrections_victus)
    assert len(applied) == 1
    assert applied[0]["new_value"] is None
    assert laptop_victus["specs"]["display"]["color_gamut"] is None

    # Test 4: ASUS Vivobook 16 (storage.slot_count 2 -> 1)
    laptop_asus = {
        "url": "https://compumarts.com/asus-vivobook-16",
        "specs": {
            "storage": {"slot_count": 2, "capacity_gb": 512}
        }
    }
    corrections_asus = [
        FieldCorrection(
            field_path="storage.slot_count",
            current_value=2,
            corrected_value=1,
            reason="Only 1 M.2 PCIe slot is storage; the other slot is DDR4 SO-DIMM RAM",
            evidence_quote="Expansion Slots: 1x DDR4 SO-DIMM slot, 1x M.2 2280 PCIe slot"
        )
    ]
    applied = auditor.apply_corrections(laptop_asus, corrections_asus)
    assert len(applied) == 1
    assert applied[0]["new_value"] == 1
    assert laptop_asus["specs"]["storage"]["slot_count"] == 1

    print("test_apply_corrections_mock: ALL 4 TARGET TEST CASES PASSED!")


if __name__ == "__main__":
    test_type_casting()
    test_physical_validator_guarding()
    test_apply_corrections_mock()
