"""Comprehensive test suite verifying all entity labels emitted through _apply_entity,
dedicated GPU priority, price sanity, CPU full name validation, and MPN validation.
"""

from __future__ import annotations

import pytest
from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.hybrid_extractor import HybridLaptopExtractor
from gliner_extractor.schema import empty_structured
from gliner_extractor.validators import (
    validate_cpu_full_name,
    validate_mpn,
    validate_price_egp,
    validate_ram_capacity,
    validate_max_ram_capacity,
)


ALL_TIER1_LABELS: list[tuple[str, str]] = [
    # Identity
    ("laptop brand", "Lenovo"),
    ("laptop model", "Legion Pro 5 16IRX9"),
    ("laptop series", "Legion"),
    ("laptop family", "Legion Pro 5"),
    ("part number", "83DV00V0ED"),
    # CPU
    ("processor model", "14700HX"),
    ("processor line", "Core i7"),
    ("processor manufacturer", "Intel"),
    ("cpu core count", "20 cores"),
    ("cpu thread count", "28 threads"),
    ("cpu clock speed", "5.5 GHz"),
    # GPU
    ("graphics model", "GeForce RTX 4070 Laptop GPU"),
    ("graphics manufacturer", "NVIDIA"),
    ("graphics vram", "8GB"),
    ("vram", "8GB"),
    ("gpu tdp wattage", "140W"),
    ("graphics power wattage", "140W"),
    ("tdp", "140W"),
    # Memory
    ("ram capacity", "32GB"),
    ("max ram capacity", "64GB"),
    ("maximum memory", "64GB"),
    ("ram type", "DDR5"),
    ("ram speed", "5600 MHz"),
    ("ram slot count", "2 slots"),
    # Storage
    ("storage capacity", "1TB SSD"),
    ("storage type", "NVMe SSD"),
    ("storage interface", "PCIe 4.0"),
    ("storage form factor", "M.2 2280"),
    ("storage slot count", "2"),
    # Display
    ("screen size", "16-inch"),
    ("screen resolution", "2560 x 1600"),
    ("refresh rate", "240Hz"),
    ("display refresh rate", "240Hz"),
    ("panel type", "IPS"),
    ("display panel type", "IPS"),
    ("aspect ratio", "16:10"),
    # Power & Battery
    ("battery capacity wh", "80Wh"),
    ("battery capacity", "80Wh"),
    ("power adapter wattage", "300W"),
    ("adapter", "300W"),
    ("battery cells", "4 cells"),
    ("cells", "4 cells"),
    # Connectivity
    ("wifi standard", "Wi-Fi 6E"),
    ("bluetooth version", "Bluetooth 5.3"),
    ("ethernet speed", "1Gbps RJ-45"),
    # Physical
    ("laptop weight", "2.5 kg"),
    ("laptop color", "Onyx Grey"),
    # Operating System
    ("operating system name", "Windows 11 Home"),
    # Build & Security
    ("backlit keyboard", "RGB Backlit keyboard"),
    ("fingerprint reader", "Fingerprint reader on power button"),
    # Audio & Webcam
    ("webcam resolution", "1080p FHD webcam"),
    ("microphone", "Dual array microphone"),
    ("speaker count", "2 x 2W stereo speakers"),
]


class TestAllEntityLabels:
    """Test that EVERY label Tier 1 can emit through _apply_entity executes without exception."""

    def test_apply_every_label_without_exception(self):
        extractor = HybridLaptopExtractor()
        for lbl, txt in ALL_TIER1_LABELS:
            struct = empty_structured()
            # Must not raise any exception
            extractor._apply_entity(struct, lbl, txt)

    def test_max_ram_capacity_with_is_max_flag(self):
        extractor = HybridLaptopExtractor()
        struct = empty_structured()
        struct["memory"]["capacity_gb"] = 16

        extractor._apply_entity(struct, "max ram capacity", "64GB")
        assert struct["memory"]["max_supported_gb"] == 64
        assert struct["extraction_meta"]["field_sources"]["memory.max_supported_gb"] == "tier2"

        # Also direct validator verification
        val, err = validate_ram_capacity(64, is_max=True)
        assert val == 64
        assert err is None

        val2, err2 = validate_max_ram_capacity(32)
        assert val2 == 32
        assert err2 is None

    def test_malformed_entity_does_not_crash_pipeline(self):
        extractor = HybridLaptopExtractor()
        struct = empty_structured()
        # Bad/garbage inputs must be handled safely
        for lbl in ["max ram capacity", "ram speed", "cpu core count", "storage capacity", "power adapter wattage"]:
            extractor._apply_entity(struct, lbl, "total_nonsense_string_with_no_numbers")
            extractor._apply_entity(struct, lbl, "")


class TestDedicatedGpuPriority:
    """Verify discrete GPU priority over integrated GPU (e.g. ROG Strix G16 items)."""

    def test_rog_strix_g16_priority_discrete_over_radeon(self):
        ext = CompumartsExtractor()
        specs = {
            "Processor": "AMD Ryzen 9 8940HX Processor 2.4GHz",
            "Intergrated GPU": "AMD Radeon Graphics",
            "Graphic": "NVIDIA GeForce RTX 5050 Laptop GPU",
            "Graphic Memory": "8GB GDDR7",
            "Discrete/Optimus": "MUX Switch + NVIDIA Advanced Optimus",
        }
        title = "ASUS ROG Strix G16 G614PH-RV659W AMD Ryzen 9 8940HX RTX 5050 8GB"
        gpu, _ = ext.extract_gpu(specs, title)

        assert gpu["manufacturer"] == "NVIDIA"
        assert "RTX 5050" in gpu["model"]
        assert gpu["integrated"] is False
        assert gpu["secondary_model"] == "Radeon Graphics"
        assert gpu["vram_gb"] == 8

    def test_rog_strix_g16_rtx5080_priority(self):
        ext = CompumartsExtractor()
        specs = {
            "Processor": "AMD Ryzen 9 8940HX Processor 2.4GHz",
            "Intergrated GPU": "AMD Radeon Graphics",
            "Graphic": "NVIDIA GeForce RTX 5080 Laptop GPU",
            "Graphic Memory": "16GB GDDR7",
        }
        title = "ASUS ROG Strix G16 G614PW-TS161W AMD Ryzen 9 8940HX NVIDIA GeForce RTX 5080 16GB"
        gpu, _ = ext.extract_gpu(specs, title)

        assert gpu["manufacturer"] == "NVIDIA"
        assert "RTX 5080" in gpu["model"]
        assert gpu["integrated"] is False
        assert gpu["secondary_model"] == "Radeon Graphics"
        assert gpu["vram_gb"] == 16


class TestPriceAndMpnValidation:
    """Test price sanity and MPN rejection rules."""

    def test_price_sanity_range(self):
        assert validate_price_egp(1.0)[0] is None
        assert "out_of_sanity_range" in validate_price_egp(1.0)[1]

        assert validate_price_egp(4999.0)[0] is None
        assert validate_price_egp(5000.0)[0] == 5000.0
        assert validate_price_egp(55000.0)[0] == 55000.0
        assert validate_price_egp(500000.0)[0] == 500000.0
        assert validate_price_egp(500001.0)[0] is None

    def test_mpn_rejection_rules(self):
        # Barcode rejection (12-13 digits)
        assert validate_mpn("4711636553421")[0] is None
        assert validate_mpn("4711636553421")[1] == "mpn_barcode_not_allowed"

        # URL slug rejection
        assert validate_mpn("acer-nitro-v-15-rtx-5050-egypt")[0] is None
        assert validate_mpn("acer-nitro-v-15-rtx-5050-egypt")[1] == "mpn_url_slug_rejected"

        # Brand mismatch
        assert validate_mpn("83DV00V0ED", brand="Acer")[0] is None
        assert validate_mpn("83DV00V0ED", brand="Acer")[1] == "mpn_brand_mismatch"

        # Brand match
        assert validate_mpn("83DV00V0ED", brand="Lenovo")[0] == "83DV00V0ED"
        assert validate_mpn("G614PH-RV659W", brand="ASUS")[0] == "G614PH-RV659W"


class TestCpuFullNameValidation:
    """Test clean_text and prose/codename rejection on cpu.full_name."""

    def test_reject_prose_and_codenames(self):
        val, err = validate_cpu_full_name("Cores 10 Cores (6 Performance + 4 Efficient)")
        assert val is None
        assert err == "cpu_full_name_is_core_description"

        val, err = validate_cpu_full_name("Raptor Lake i7-13620H")
        assert val is None
        assert err == "cpu_full_name_contains_codename"

    def test_accept_valid_cpu_full_names(self):
        val, err = validate_cpu_full_name("Intel Core i7-13620H")
        assert val == "Intel Core i7-13620H"
        assert err is None

        val, err = validate_cpu_full_name("AMD Ryzen 9 8940HX Processor")
        assert val == "AMD Ryzen 9 8940HX Processor"
        assert err is None

