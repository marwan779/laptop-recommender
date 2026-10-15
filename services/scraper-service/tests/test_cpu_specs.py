"""Automated tests for Canonical Laptop CPU Specifications Dictionary (2021–Present).

Validates:
- Exact matches and canonical key lookup
- Retailer aliases and messy product title normalization
- Prevention of ambiguous or partial matches
- Unknown and unsupported processors
- Full schema and data integrity across all 168 SKUs
- Core count math, units consistency, and official source URLs
- Scraping enrichment interface
"""

import pytest
from app.core.cpu_specs import (
    CPU_SPECS,
    CPU_ALIASES,
    AMBIGUOUS_CPU_TOKENS,
    normalize_cpu_name,
    lookup_cpu,
    enrich_cpu_specs,
    get_cpu_summary_stats,
    clean_cpu_string,
)


class TestExactMatches:
    """Verify that canonical model identifiers resolve directly to verified specifications."""

    @pytest.mark.parametrize(
        "canonical_key, expected_mfg, expected_cores, expected_threads",
        [
            ("intel_core_i9_13900hx", "Intel", 24, 32),
            ("intel_core_i7_13700h", "Intel", 14, 20),
            ("intel_core_ultra_7_155h", "Intel", 16, 22),
            ("intel_core_ultra_9_288v", "Intel", 8, 8),
            ("intel_core_7_150u", "Intel", 10, 12),
            ("amd_ryzen_7_7840hs", "AMD", 8, 16),
            ("amd_ryzen_5_5600h", "AMD", 6, 12),
            ("amd_ryzen_ai_9_hx_370", "AMD", 12, 24),
            ("apple_m3_pro_12_core", "Apple", 12, 12),
            ("apple_m2_8_core", "Apple", 8, 8),
        ],
    )
    def test_canonical_keys_resolve(
        self, canonical_key: str, expected_mfg: str, expected_cores: int, expected_threads: int
    ):
        spec = lookup_cpu(canonical_key)
        assert spec is not None, f"Key {canonical_key} failed to resolve"
        assert spec["manufacturer"] == expected_mfg
        assert spec["total_cores"] == expected_cores
        assert spec["total_threads"] == expected_threads


class TestRetailerAliases:
    """Verify that common retailer variations, noisy titles, and abbreviations normalize reliably."""

    @pytest.mark.parametrize(
        "raw_string, expected_key",
        [
            # Intel standard format
            ("Intel Core i7-13700H", "intel_core_i7_13700h"),
            ("i7-13700H", "intel_core_i7_13700h"),
            ("Intel Core i7 13700H @ 2.4 GHz", "intel_core_i7_13700h"),
            ("13700H", "intel_core_i7_13700h"),
            ("Core i7-13650HX Processor", "intel_core_i7_13650hx"),
            ("13650HX", "intel_core_i7_13650hx"),
            # Intel Core Ultra
            ("Intel Core Ultra 7 155H", "intel_core_ultra_7_155h"),
            ("Core Ultra 7 155H up to 4.8GHz", "intel_core_ultra_7_155h"),
            ("Ultra 7 155H", "intel_core_ultra_7_155h"),
            ("155H", "intel_core_ultra_7_155h"),
            ("Core Ultra 9 185H", "intel_core_ultra_9_185h"),
            ("Core Ultra 7 258V", "intel_core_ultra_7_258v"),
            # Intel Core Series 1
            ("Intel Core 7 150U", "intel_core_7_150u"),
            ("Core 5 120U Processor", "intel_core_5_120u"),
            ("150U", "intel_core_7_150u"),
            # AMD Ryzen
            ("AMD Ryzen 7 7840HS", "amd_ryzen_7_7840hs"),
            ("Ryzen 7 7840HS with Radeon 780M Graphics", "amd_ryzen_7_7840hs"),
            ("7840HS", "amd_ryzen_7_7840hs"),
            ("Ryzen 7 7735HS Processor", "amd_ryzen_7_7735hs"),
            ("AMD Ryzen 5 5600H", "amd_ryzen_5_5600h"),
            ("5600H", "amd_ryzen_5_5600h"),
            ("R7 7735HS", "amd_ryzen_7_7735hs"),
            # AMD Ryzen AI
            ("AMD Ryzen AI 9 HX 370", "amd_ryzen_ai_9_hx_370"),
            ("Ryzen AI 9 HX 370 Processor", "amd_ryzen_ai_9_hx_370"),
            ("Ryzen AI 9 365", "amd_ryzen_ai_9_365"),
            # Apple Silicon
            ("Apple M3 Pro", "apple_m3_pro_12_core"),
            ("Apple M3 Pro (11-core)", "apple_m3_pro_11_core"),
            ("M2 (8-core)", "apple_m2_8_core"),
            ("Apple M1 Max", "apple_m1_max_32_core"),
            ("M4 Pro (14-core)", "apple_m4_pro_14_core"),
        ],
    )
    def test_retailer_aliases_normalize(self, raw_string: str, expected_key: str):
        resolved_key = normalize_cpu_name(raw_string)
        assert resolved_key == expected_key, f"Expected {expected_key} for '{raw_string}', got {resolved_key}"


class TestAmbiguityProtection:
    """Verify that ambiguous, partial, or generic inputs return None rather than guessing."""

    @pytest.mark.parametrize(
        "ambiguous_input",
        [
            "Intel",
            "AMD",
            "Apple",
            "Core",
            "Ryzen",
            "Intel Core",
            "AMD Ryzen",
            "Core i7",
            "Core i5",
            "Core i9",
            "Core i3",
            "i7",
            "i5",
            "i9",
            "Ryzen 7",
            "Ryzen 5",
            "Ryzen 9",
            "R7",
            "R5",
            "Core Ultra",
            "Core Ultra 7",
            "Core Ultra 9",
            "Ultra 7",
            "Processor",
            "CPU",
            "",
            None,
        ],
    )
    def test_ambiguous_tokens_return_none(self, ambiguous_input: str | None):
        assert normalize_cpu_name(ambiguous_input) is None
        assert lookup_cpu(ambiguous_input) is None


class TestUnknownCPUs:
    """Verify that unknown, unreleased, or fictional CPUs return None."""

    @pytest.mark.parametrize(
        "unknown_input",
        [
            "Intel Core i7-99999K",
            "AMD Ryzen 9 99999HX",
            "Qualcomm Snapdragon X Elite X1E-80-100",
            "Apple M9 Extreme",
            "Nvidia Tegra X1",
            "MediaTek Dimensity 9300",
        ],
    )
    def test_unknown_cpus_return_none(self, unknown_input: str):
        assert normalize_cpu_name(unknown_input) is None
        assert lookup_cpu(unknown_input) is None


class TestDataIntegrityAndSchemaValidation:
    """Comprehensive validation across all 168 canonical records."""

    def test_catalog_size_and_manufacturers(self):
        stats = get_cpu_summary_stats()
        assert stats["total_cpus"] >= 150
        assert "Intel" in stats["by_manufacturer"]
        assert "AMD" in stats["by_manufacturer"]
        assert "Apple" in stats["by_manufacturer"]
        assert stats["by_manufacturer"]["Intel"] >= 80
        assert stats["by_manufacturer"]["AMD"] >= 45
        assert stats["by_manufacturer"]["Apple"] >= 15

    def test_required_fields_and_types(self):
        required_fields = [
            "manufacturer",
            "model",
            "family",
            "codename",
            "segment",
            "launch_date",
            "status",
            "lithography",
            "total_cores",
            "total_threads",
            "max_turbo_frequency_mhz",
            "cache_mb",
            "base_power_w",
            "source_url",
            "last_verified",
        ]

        for key, spec in CPU_SPECS.items():
            for f in required_fields:
                assert f in spec, f"CPU {key} missing required field '{f}'"
                assert spec[f] is not None, f"CPU {key} has None for required field '{f}'"

            # Validate types and units
            assert isinstance(spec["total_cores"], int) and spec["total_cores"] > 0
            assert isinstance(spec["total_threads"], int) and spec["total_threads"] >= spec["total_cores"]
            assert isinstance(spec["max_turbo_frequency_mhz"], int) and spec["max_turbo_frequency_mhz"] >= 2000
            assert isinstance(spec["cache_mb"], (int, float)) and spec["cache_mb"] > 0
            assert isinstance(spec["base_power_w"], (int, float)) and spec["base_power_w"] > 0

            # Source URL must be valid
            assert spec["source_url"].startswith("https://")
            assert spec["last_verified"] == "2026-10-11"

    def test_core_count_math_consistency(self):
        """Verify that P-cores + E-cores (+ LP-E cores) sum up exactly to total_cores."""
        for key, spec in CPU_SPECS.items():
            p = spec.get("performance_cores")
            e = spec.get("efficient_cores")
            lpe = spec.get("low_power_efficient_cores")

            if p is not None and e is not None:
                expected_sum = p + e + (lpe or 0)
                assert (
                    spec["total_cores"] == expected_sum
                ), f"CPU {key} total_cores={spec['total_cores']} does not match sum {p}+{e}+{lpe}={expected_sum}"


class TestEnrichmentInterface:
    """Verify that enrich_cpu_specs populates missing fields from canonical data."""

    def test_enrich_partial_record(self):
        scraped = {
            "model": "Core i7-13700H",
            "cores": None,
            "threads": None,
            "cache_mb": None,
        }
        enriched = enrich_cpu_specs(scraped)
        assert enriched["canonical_verified"] is True
        assert enriched["canonical_key"] == "intel_core_i7_13700h"
        assert enriched["canonical_model"] == "Intel Core i7-13700H"
        assert enriched["cores"] == 14
        assert enriched["threads"] == 20
        assert enriched["cache_mb"] == 24.0
        assert enriched["base_power_w"] == 45.0
        assert enriched["npu_name"] is None  # 13700H had no NPU
        assert enriched["source_url"].startswith("https://")

    def test_enrich_does_not_overwrite_existing_scraped_fields(self):
        scraped = {
            "model": "Core i7-13700H",
            "cores": 14,
            "custom_note": "retailer note",
        }
        enriched = enrich_cpu_specs(scraped)
        assert enriched["cores"] == 14
        assert enriched["custom_note"] == "retailer note"
        assert enriched["threads"] == 20  # Populated from canonical

    def test_enrich_unresolved_cpu_marks_unverified(self):
        scraped = {
            "model": "Generic Unknown CPU 123",
            "cores": 4,
        }
        enriched = enrich_cpu_specs(scraped)
        assert enriched["canonical_verified"] is False
        assert enriched["cores"] == 4

