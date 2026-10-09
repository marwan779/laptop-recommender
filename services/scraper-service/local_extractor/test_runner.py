"""Isolated Test Runner for Local Model Extractor.

Tests the local model against the exact real-world edge cases from El Badr and CompuMarts.
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from local_extractor import LocalModelExtractor, LaptopSpecExtraction


TEST_CASES = [
    {
        "id": "CASE_1_DUAL_STORAGE",
        "name": "Lenovo Gaming 3 (Dual Storage 1TB HDD + 256GB SSD)",
        "input_text": "LENOVO GAMING 3 RYZEN 7 5800H 16GB 1TB HDD 256GB SSD RTX 3050 15.6 FHD 165Hz",
        "expected_checks": {
            "dual_storage": lambda s: "1TB" in (s.storage or "") and "256GB" in (s.storage or ""),
            "processor": lambda s: "5800H" in (s.processor or ""),
            "graphics": lambda s: "3050" in (s.graphics or ""),
        },
    },
    {
        "id": "CASE_2_NO_DISPLAY_HALLUCINATION",
        "name": "Dell 3510 (No Screen Size in Title + GPU vs Model)",
        "input_text": "DELL 3510 Core I5 1135G7 4GB 1TB HDD MX350 2GB",
        "expected_checks": {
            "no_display_hallucination": lambda s: s.display is None,
            "series_model": lambda s: "3510" in (s.series_model or "") and "MX" not in (s.series_model or ""),
            "graphics": lambda s: "MX350" in (s.graphics or ""),
        },
    },
    {
        "id": "CASE_3_RAM_SPEED_AND_WARRANTY",
        "name": "Lenovo LOQ (RAM 5600, 20 Cores, 2Y Warranty)",
        "input_text": (
            "LENOVO LOQ 15IRX10 83JE00DAED — Core i7-14700HX 20 Cores – 24GB DDR5 5600 – "
            "512GB SSD – RTX 5050 8GB GDDR7 – 15.6 FHD IPS 100% sRGB 144Hz G-SYNC – Win 11 - 2Y Warranty"
        ),
        "expected_checks": {
            "ram_frequency": lambda s: "5600" in (s.ram or "") and "24GB" in (s.ram or ""),
            "cpu_cores": lambda s: "20" in (s.cpu_cores or ""),
            "warranty": lambda s: "2Y" in (s.warranty or "") or "2" in (s.warranty or ""),
        },
    },
    {
        "id": "CASE_4_SEPARATED_DISPLAY_AND_CERT",
        "name": "XPG Xenia (RAM 4266, FHD Touch, Intel EVO)",
        "input_text": (
            'XPG 15.6" XENIA Xe Gaming Lifestyle Ultrabook Intel EVO Core i7-1135G7 '
            '16GB DDR4 4266 Intel Iris Xe FHD Touch 1TB SSD Windows 10 Home'
        ),
        "expected_checks": {
            "ram_frequency": lambda s: "4266" in (s.ram or ""),
            "touch_display": lambda s: "Touch" in (s.display or "") and "FHD" in (s.display or ""),
            "intel_evo": lambda s: "EVO" in (s.processor or "") or "EVO" in getattr(s, "certifications", ""),
        },
    },
    {
        "id": "CASE_5_COMPUMARTS_UNSTRUCTURED_PDP",
        "name": "CompuMarts Asus TUF F16 (Flattened PDP Description)",
        "input_text": (
            "Laptop ASUS TUF Gaming FX607VU-RL167W\n"
            "Processor: Intel Core 7 Processor 240H 2.5 GHz (10 cores, 16 Threads)\n"
            "Graphics: NVIDIA GeForce RTX 4050 Laptop GPU 140W Max TGP 6GB GDDR6\n"
            "Panel Size: 16-inch FHD+ 16:10 144Hz IPS Anti-glare G-Sync\n"
            "Memory: 16GB DDR5-5600 SO-DIMM\n"
            "Storage: 512GB PCIe 4.0 NVMe M.2 SSD\n"
            "Battery: 56WHrs 4-cell Li-ion\n"
            "Weight: 2.20 Kg"
        ),
        "expected_checks": {
            "processor": lambda s: "240H" in (s.processor or ""),
            "gpu_tgp": lambda s: "4050" in (s.graphics or "") and "140W" in (s.graphics or ""),
            "display": lambda s: "16" in (s.display or "") and "144Hz" in (s.display or ""),
            "storage": lambda s: "512GB" in (s.storage or ""),
        },
    },
]


def run_tests():
    print("=" * 70)
    print("🚀 LOCAL MODEL EXTRACTOR TEST HARNESS")
    print("=" * 70)

    extractor = LocalModelExtractor()
    health = extractor.check_health()
    print(f"Backend Status: {health.get('status').upper()}")

    if health.get("status") != "ok":
        print(f"\n⚠️  {health.get('message')}")
        print("\nTo test with Ollama:")
        print("  1. Ensure Ollama is installed (https://ollama.com)")
        print("  2. Run in a terminal: ollama run qwen2.5:1.5b")
        print("  3. Re-run this script: python local_extractor/test_runner.py\n")
        return

    print(f"Active Backend: {health.get('backend')} | Available models: {health.get('models')}")
    print("-" * 70)

    total_passed = 0
    total_latency = 0.0

    for idx, case in enumerate(TEST_CASES, start=1):
        print(f"\n[{idx}/{len(TEST_CASES)}] Testing: {case['name']}")
        print(f"Input: {case['input_text'][:70]}...")

        specs, latency, error = extractor.extract(case["input_text"])

        if error or not specs:
            print(f"❌ FAILED: {error}")
            continue

        total_latency += latency
        print(f"⏱️ Latency: {latency * 1000:.1f}ms")
        print("Extracted:")
        for k, v in specs.model_dump(exclude_none=True).items():
            print(f"   • {k}: {v}")

        # Run checks
        failed_checks = []
        for check_name, check_fn in case["expected_checks"].items():
            if not check_fn(specs):
                failed_checks.append(check_name)

        if failed_checks:
            print(f"⚠️ Check Failures: {failed_checks}")
        else:
            print("✅ All assertion checks passed!")
            total_passed += 1

    print("\n" + "=" * 70)
    avg_latency = (total_latency / len(TEST_CASES)) * 1000 if TEST_CASES else 0
    print(f"SUMMARY: {total_passed}/{len(TEST_CASES)} passed | Avg Latency: {avg_latency:.1f}ms")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
