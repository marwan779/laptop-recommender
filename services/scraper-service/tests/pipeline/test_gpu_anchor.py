"""Unit tests for Layer 3.5 GPU Anchor Extraction and TDP protocol rules."""

from typing import Any, Dict
import pytest

from gpu_specs import GPU_SPECS, GPUSpecificationEntry
from pipeline.gpu_anchor import GPUAnchorExtractor
from pipeline.orchestrator import LaptopExtractionPipeline
from pipeline.schema import RawScrapedProduct


class TestGPUSpecsValidation:
    """Validate all entries in the GPU specs database against the Pydantic schema."""

    def test_all_93_gpus_conform_to_schema(self):
        """Every single GPU entry must strictly satisfy the GPUSpecificationEntry schema."""
        assert len(GPU_SPECS) >= 90
        for key, entry in GPU_SPECS.items():
            obj = GPUSpecificationEntry(**entry)
            assert obj.model is not None
            assert obj.architecture is not None
            if obj.integrated:
                assert obj.vram_gb is None
                assert obj.tdp_limits is None
            else:
                assert isinstance(obj.vram_gb, int)
                assert obj.tdp_limits is not None
                assert obj.tdp_limits.min_w <= obj.tdp_limits.max_w


class TestGPUAnchorExtraction:
    """Test SKU identification, VRAM disambiguation, and silicon anchoring."""

    @pytest.fixture
    def extractor(self):
        return GPUAnchorExtractor()

    def test_discrete_rtx_with_store_tgp(self, extractor: GPUAnchorExtractor):
        """Store-provided TGP within bounds must be preserved exactly."""
        title = "Lenovo LOQ 15IRX9 83DV01HSED - Core i7-13650HX - RTX 4050 6GB - 15.6 FHD 144Hz"
        spec_text = "NVIDIA GeForce RTX 4050 6GB GDDR6, Boost Clock 2370MHz, TGP 105W"
        specs, constraints, key = extractor.extract(title=title, spec_texts=[spec_text])

        assert key == "RTX_4050_6GB"
        assert specs is not None
        assert specs["manufacturer"] == "NVIDIA"
        assert specs["model"] == "GeForce RTX 4050"
        assert specs["vram_gb"] == 6
        assert specs["integrated"] is False
        assert specs["tdp_w"] == 105  # Validated store TGP
        assert specs["boost_clock_mhz"] == 2370
        assert specs["ai_tops"] == 194

    def test_discrete_rtx_omitted_tgp_never_defaults(self, extractor: GPUAnchorExtractor):
        """When the store omits TGP, tdp_w must remain None (never default to silicon bounds)."""
        title = "ASUS TUF Gaming A15 FA507NV AMD Ryzen 7 7735HS 16GB 512GB RTX 4060 8GB"
        spec_text = "NVIDIA GeForce RTX 4060 8GB GDDR6 Laptop GPU"
        specs, constraints, key = extractor.extract(title=title, spec_texts=[spec_text])

        assert key == "RTX_4060_8GB"
        assert specs is not None
        assert specs["manufacturer"] == "NVIDIA"
        assert specs["model"] == "GeForce RTX 4060"
        assert specs["vram_gb"] == 8
        assert specs["tdp_w"] is None  # Strictly None when store omitted TGP

    def test_out_of_bounds_tgp_rejected(self, extractor: GPUAnchorExtractor):
        """TGP outside physical bounds [min_w, max_w] must be rejected."""
        title = "MSI Thin GF63 RTX 4050 6GB TGP 250W"
        specs, _, key = extractor.extract(title=title)

        assert key == "RTX_4050_6GB"
        assert specs is not None
        assert specs["tdp_w"] is None  # 250W is beyond RTX 4050 max 140W

    def test_vram_disambiguation_rtx_3050(self, extractor: GPUAnchorExtractor):
        """Multi-VRAM SKU correctly selects 6GB vs 4GB variant based on text."""
        # 6GB variant
        title_6gb = "Acer Nitro 5 AN515 Intel Core i5-12500H RTX 3050 6GB"
        specs_6gb, _, key_6gb = extractor.extract(title=title_6gb)
        assert key_6gb == "RTX_3050_6GB"
        assert specs_6gb["vram_gb"] == 6

        # 4GB variant
        title_4gb = "Dell G15 5520 Intel Core i5-12500H RTX 3050 4GB"
        specs_4gb, _, key_4gb = extractor.extract(title=title_4gb)
        assert key_4gb == "RTX_3050_4GB"
        assert specs_4gb["vram_gb"] == 4

    def test_integrated_gpus(self, extractor: GPUAnchorExtractor):
        """Integrated GPUs have integrated=True, vram_gb=None, tdp_w=None."""
        cases = [
            ("ASUS Zenbook S 14 UX5406SA Intel Core Ultra 7 258V Intel Arc 140V", "Intel_Arc_140V_Shared", "Intel Arc 140V"),
            ("Acer Swift Go 14 AMD Ryzen 7 7840U AMD Radeon 780M", "Radeon_780M_Shared", "AMD Radeon 780M"),
            ("Apple MacBook Pro 14 M4 chip 10-core GPU 16GB", "Apple_M4_GPU_Unified", "Apple M4 GPU"),
            ("Microsoft Surface Laptop 7 Snapdragon X Elite Adreno X1-85", "Qualcomm_Adreno_X1_85_Shared", "Qualcomm Adreno X1-85"),
        ]
        for text, exp_key, exp_model in cases:
            specs, _, key = extractor.extract(title=text)
            assert key == exp_key
            assert specs is not None
            assert specs["model"] == exp_model
            assert specs["integrated"] is True
            assert specs["vram_gb"] is None
            assert specs["tdp_w"] is None

    def test_integrated_gpu_via_cpu_context(self, extractor: GPUAnchorExtractor):
        """Generic 'Radeon Graphics' resolves to exact iGPU via cpu_context."""
        title = "Lenovo ThinkPad E16 Gen 1 AMD Ryzen 7 7730U AMD Radeon Graphics"
        cpu_ctx = {"integrated_gpu": "AMD Radeon 610M (2 graphics cores, 2200 MHz)"}
        specs, _, key = extractor.extract(title=title, cpu_context=cpu_ctx)

        assert key == "Radeon_610M_Shared"
        assert specs["model"] == "AMD Radeon 610M"
        assert specs["integrated"] is True

    def test_integrated_gpu_with_tgp_rejected(self, extractor: GPUAnchorExtractor):
        """Integrated GPU text mentioning wattage must never assign tdp_w."""
        title = "HP Pavilion AMD Radeon 780M TGP 45W"
        specs, _, _ = extractor.extract(title=title)
        assert specs["tdp_w"] is None


class TestOrchestratorTDPProtocol:
    """Verify that orchestrator respects the TDP envelope suppression rule."""

    def test_missing_gpu_tdp_does_not_dispatch_envelope(self):
        """When discrete GPU is anchored and only tdp_w is missing, no component envelope is dispatched."""
        orchestrator = LaptopExtractionPipeline(log_envelopes=False)

        # Scraped product with clear GPU model and VRAM, but NO TGP in table or sections
        product = RawScrapedProduct(
            url="https://test.com/laptop",
            store="test",
            title="ASUS TUF Gaming A15 AMD Ryzen 7 7735HS RTX 4060 8GB",
            raw_html="<html></html>",
            raw_tables={
                "specs": {
                    "Processor": "AMD Ryzen 7 7735HS",
                    "Graphics": "NVIDIA GeForce RTX 4060 8GB GDDR6",
                    "Memory": "16GB DDR5 4800MHz",
                    "Storage": "512GB PCIe NVMe SSD",
                    "Display": "15.6 FHD 144Hz IPS",
                    "Battery": "90Wh",
                    "Weight": "2.2 kg",
                }
            },
            raw_sections={"Graphics": "NVIDIA GeForce RTX 4060 8GB GDDR6"},
        )

        result = orchestrator.process_raw_product(product)
        specs = result.specs

        # GPU anchored
        assert specs["gpu"]["model"] == "GeForce RTX 4060"
        assert specs["gpu"]["vram_gb"] == 8
        assert specs["gpu"]["tdp_w"] is None

        # Verify no GPU component envelope was dispatched
        gpu_envelopes = [
            e for e in result.component_envelopes_generated if e.component_name == "gpu"
        ]
        assert len(gpu_envelopes) == 0, "Missing tdp_w alone should NEVER trigger an AI envelope!"
