"""Script to unify cpu_specs.py format and add Apple M1, M4, M4 Pro, M4 Max.
"""

from __future__ import annotations
import pprint
import re
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CPU_SPECS_PATH = Path(r"D:\Development\Side Projects\laptop-recommender\services\scraper-service\cpu_specs.py")

def normalize_launch_date(raw_date: str | None) -> str | None:
    if not raw_date:
        return raw_date
    raw = str(raw_date).strip()
    
    # Check Q[1-4] 'YY -> Q[1-4] 20YY
    m_q_apostrophe = re.match(r"^Q([1-4])'(\d{2})$", raw)
    if m_q_apostrophe:
        q = m_q_apostrophe.group(1)
        yr = int(m_q_apostrophe.group(2))
        full_yr = 2000 + yr if yr < 50 else 1900 + yr
        return f"Q{q} {full_yr}"

    # Check Q[1-4] YYYY -> already canonical
    m_q_yyyy = re.match(r"^Q([1-4])\s+(\d{4})$", raw)
    if m_q_yyyy:
        return f"Q{m_q_yyyy.group(1)} {m_q_yyyy.group(2)}"

    # Check Month Year: e.g. "March 2020", "October 2021", "January 2026", "November 2020"
    month_to_q = {
        "january": "Q1", "jan": "Q1", "february": "Q1", "feb": "Q1", "march": "Q1", "mar": "Q1",
        "april": "Q2", "apr": "Q2", "may": "Q2", "june": "Q2", "jun": "Q2",
        "july": "Q3", "jul": "Q3", "august": "Q3", "aug": "Q3", "september": "Q3", "sep": "Q3",
        "october": "Q4", "oct": "Q4", "november": "Q4", "nov": "Q4", "december": "Q4", "dec": "Q4"
    }
    m_month_yr = re.match(r"^([A-Za-z]+)\s+(\d{4})$", raw)
    if m_month_yr:
        m_name = m_month_yr.group(1).lower()
        yr = m_month_yr.group(2)
        if m_name in month_to_q:
            return f"{month_to_q[m_name]} {yr}"

    # Check MM/YYYY: e.g. "01/2023", "09/2022"
    m_mm_yyyy = re.match(r"^(\d{1,2})/(\d{4})$", raw)
    if m_mm_yyyy:
        month = int(m_mm_yyyy.group(1))
        yr = m_mm_yyyy.group(2)
        q = (month - 1) // 3 + 1
        return f"Q{q} {yr}"

    # Check MM/DD/YYYY or D/MM/YYYY: e.g. "01/04/2022", "06/06/2022", "1/12/2021"
    m_date = re.match(r"^(\d{1,2})/\d{1,2}/(\d{4})$", raw)
    if m_date:
        month = int(m_date.group(1))
        yr = m_date.group(2)
        q = (month - 1) // 3 + 1
        return f"Q{q} {yr}"

    return raw


def get_apple_new_chips() -> dict[str, dict[str, Any]]:
    return {
        "apple_m1": {
            "manufacturer": "Apple",
            "model": "M1",
            "official_name": "Apple M1",
            "family": "Apple Silicon",
            "codename": "M1",
            "segment": "Mobile",
            "launch_date": "Q4 2020",
            "status": "Launched",
            "lithography": "TSMC 5nm (N5)",
            "socket": "Integrated",
            "total_cores": 8,
            "performance_cores": 4,
            "efficient_cores": 4,
            "low_power_efficient_cores": None,
            "total_threads": 8,
            "max_turbo_frequency_mhz": 3200,
            "p_core_max_turbo_mhz": 3200,
            "p_core_base_mhz": 2064,
            "e_core_max_turbo_mhz": 2064,
            "e_core_base_mhz": 2064,
            "lp_e_core_max_turbo_mhz": None,
            "lp_e_core_base_mhz": None,
            "cache_mb": 16,
            "cache_type": "12MB L2 (P-cores) + 4MB L2 (E-cores)",
            "base_power_w": 15,
            "max_turbo_power_w": 20,
            "minimum_assured_power_w": 10,
            "max_operating_temperature_c": 100,
            "max_supported_memory_gb": 16,
            "supported_memory_types": ["LPDDR4X-4266"],
            "max_ddr5_speed_mts": None,
            "max_lpddr5x_speed_mts": None,
            "max_memory_channels": 2,
            "apple_memory_bandwidth_gbps": 68.25,
            "apple_media_engine": "Hardware-accelerated H.264, HEVC",
            "integrated_gpu_name": "Apple M1 GPU (8-core)",
            "gpu_max_frequency_mhz": 1278,
            "gpu_xe_cores": None,
            "gpu_compute_units": 8,
            "gpu_peak_tops": 2.6,
            "ray_tracing": False,
            "directx_support": None,
            "opengl_support": None,
            "opencl_support": "OpenCL 1.2 (Metal)",
            "av1_encode_decode": False,
            "max_supported_displays": 2,
            "npu_name": "16-core Neural Engine",
            "npu_peak_tops": 11.0,
            "npu_sparsity_support": None,
            "npu_windows_studio_effects": False,
            "thunderbolt_4_support": False,
            "usb4": True,
            "pcie_revisions": ["3.0"],
            "max_pcie_lanes": None,
            "graphics_output": ["DisplayPort", "HDMI"],
            "instruction_set": "ARMv8.5-A",
            "instruction_extensions": ["NEON", "Apple AMX"],
            "intel_64": False,
            "intel_dl_boost": False,
            "intel_thread_director": False,
            "intel_turbo_boost": False,
            "intel_turbo_boost_max_3": False,
            "intel_speed_shift": False,
            "intel_vt_x": False,
            "intel_vt_d": False,
            "intel_aes_ni": False,
            "intel_trusted_execution": False,
            "source_url": "https://support.apple.com/en-us/111883",
            "last_verified": "2026-10-11",
        },
        "apple_m4": {
            "manufacturer": "Apple",
            "model": "M4",
            "official_name": "Apple M4",
            "family": "Apple Silicon",
            "codename": "Donan",
            "segment": "Mobile",
            "launch_date": "Q4 2024",
            "status": "Launched",
            "lithography": "TSMC 3nm (N3E)",
            "socket": "Integrated",
            "total_cores": 10,
            "performance_cores": 4,
            "efficient_cores": 6,
            "low_power_efficient_cores": None,
            "total_threads": 10,
            "max_turbo_frequency_mhz": 4400,
            "p_core_max_turbo_mhz": 4400,
            "p_core_base_mhz": 2800,
            "e_core_max_turbo_mhz": 2800,
            "e_core_base_mhz": 2800,
            "lp_e_core_max_turbo_mhz": None,
            "lp_e_core_base_mhz": None,
            "cache_mb": 20,
            "cache_type": "16MB L2 Shared + SLC",
            "base_power_w": 22,
            "max_turbo_power_w": 28,
            "minimum_assured_power_w": 15,
            "max_operating_temperature_c": 100,
            "max_supported_memory_gb": 32,
            "supported_memory_types": ["LPDDR5X"],
            "max_ddr5_speed_mts": None,
            "max_lpddr5x_speed_mts": 7500,
            "max_memory_channels": 2,
            "apple_memory_bandwidth_gbps": 120,
            "apple_media_engine": "ProRes, H.264, HEVC, AV1",
            "integrated_gpu_name": "Apple M4 GPU (10-core)",
            "gpu_max_frequency_mhz": 1400,
            "gpu_xe_cores": None,
            "gpu_compute_units": 10,
            "gpu_peak_tops": None,
            "ray_tracing": True,
            "directx_support": None,
            "opengl_support": None,
            "opencl_support": "OpenCL 1.2 (Metal)",
            "av1_encode_decode": True,
            "max_supported_displays": 3,
            "npu_name": "16-core Neural Engine",
            "npu_peak_tops": 38.0,
            "npu_sparsity_support": None,
            "npu_windows_studio_effects": False,
            "thunderbolt_4_support": True,
            "usb4": True,
            "pcie_revisions": ["4.0"],
            "max_pcie_lanes": None,
            "graphics_output": ["DisplayPort", "HDMI"],
            "instruction_set": "ARMv9.2-A",
            "instruction_extensions": ["NEON", "SME"],
            "intel_64": False,
            "intel_dl_boost": False,
            "intel_thread_director": False,
            "intel_turbo_boost": False,
            "intel_turbo_boost_max_3": False,
            "intel_speed_shift": False,
            "intel_vt_x": False,
            "intel_vt_d": False,
            "intel_aes_ni": False,
            "intel_trusted_execution": False,
            "source_url": "https://support.apple.com/en-us/111909",
            "last_verified": "2026-10-11",
        },
        "apple_m4_pro": {
            "manufacturer": "Apple",
            "model": "M4 Pro",
            "official_name": "Apple M4 Pro",
            "family": "Apple Silicon",
            "codename": "Brava",
            "segment": "Mobile",
            "launch_date": "Q4 2024",
            "status": "Launched",
            "lithography": "TSMC 3nm (N3E)",
            "socket": "Integrated",
            "total_cores": 14,
            "performance_cores": 10,
            "efficient_cores": 4,
            "low_power_efficient_cores": None,
            "total_threads": 14,
            "max_turbo_frequency_mhz": 4510,
            "p_core_max_turbo_mhz": 4510,
            "p_core_base_mhz": 2800,
            "e_core_max_turbo_mhz": 2800,
            "e_core_base_mhz": 2800,
            "lp_e_core_max_turbo_mhz": None,
            "lp_e_core_base_mhz": None,
            "cache_mb": 24,
            "cache_type": "L2 Shared + SLC",
            "base_power_w": 35,
            "max_turbo_power_w": 45,
            "minimum_assured_power_w": 25,
            "max_operating_temperature_c": 100,
            "max_supported_memory_gb": 64,
            "supported_memory_types": ["LPDDR5X"],
            "max_ddr5_speed_mts": None,
            "max_lpddr5x_speed_mts": 8533,
            "max_memory_channels": 3,
            "apple_memory_bandwidth_gbps": 273,
            "apple_media_engine": "ProRes, H.264, HEVC, AV1",
            "integrated_gpu_name": "Apple M4 Pro GPU (20-core)",
            "gpu_max_frequency_mhz": 1450,
            "gpu_xe_cores": None,
            "gpu_compute_units": 20,
            "gpu_peak_tops": None,
            "ray_tracing": True,
            "directx_support": None,
            "opengl_support": None,
            "opencl_support": "OpenCL 1.2 (Metal)",
            "av1_encode_decode": True,
            "max_supported_displays": 3,
            "npu_name": "16-core Neural Engine",
            "npu_peak_tops": 38.0,
            "npu_sparsity_support": None,
            "npu_windows_studio_effects": False,
            "thunderbolt_4_support": True,
            "thunderbolt_5_support": True,
            "usb4": True,
            "pcie_revisions": ["4.0"],
            "max_pcie_lanes": None,
            "graphics_output": ["DisplayPort", "HDMI"],
            "instruction_set": "ARMv9.2-A",
            "instruction_extensions": ["NEON", "SME"],
            "intel_64": False,
            "intel_dl_boost": False,
            "intel_thread_director": False,
            "intel_turbo_boost": False,
            "intel_turbo_boost_max_3": False,
            "intel_speed_shift": False,
            "intel_vt_x": False,
            "intel_vt_d": False,
            "intel_aes_ni": False,
            "intel_trusted_execution": False,
            "source_url": "https://support.apple.com/en-us/111910",
            "last_verified": "2026-10-11",
        },
        "apple_m4_max": {
            "manufacturer": "Apple",
            "model": "M4 Max",
            "official_name": "Apple M4 Max",
            "family": "Apple Silicon",
            "codename": "Hidra",
            "segment": "Mobile",
            "launch_date": "Q4 2024",
            "status": "Launched",
            "lithography": "TSMC 3nm (N3E)",
            "socket": "Integrated",
            "total_cores": 16,
            "performance_cores": 12,
            "efficient_cores": 4,
            "low_power_efficient_cores": None,
            "total_threads": 16,
            "max_turbo_frequency_mhz": 4510,
            "p_core_max_turbo_mhz": 4510,
            "p_core_base_mhz": 2800,
            "e_core_max_turbo_mhz": 2800,
            "e_core_base_mhz": 2800,
            "lp_e_core_max_turbo_mhz": None,
            "lp_e_core_base_mhz": None,
            "cache_mb": 48,
            "cache_type": "L2 Shared + SLC",
            "base_power_w": 45,
            "max_turbo_power_w": 80,
            "minimum_assured_power_w": 35,
            "max_operating_temperature_c": 100,
            "max_supported_memory_gb": 128,
            "supported_memory_types": ["LPDDR5X"],
            "max_ddr5_speed_mts": None,
            "max_lpddr5x_speed_mts": 8533,
            "max_memory_channels": 4,
            "apple_memory_bandwidth_gbps": 546,
            "apple_media_engine": "Dual ProRes, H.264, HEVC, AV1",
            "integrated_gpu_name": "Apple M4 Max GPU (40-core)",
            "gpu_max_frequency_mhz": 1450,
            "gpu_xe_cores": None,
            "gpu_compute_units": 40,
            "gpu_peak_tops": None,
            "ray_tracing": True,
            "directx_support": None,
            "opengl_support": None,
            "opencl_support": "OpenCL 1.2 (Metal)",
            "av1_encode_decode": True,
            "max_supported_displays": 4,
            "npu_name": "16-core Neural Engine",
            "npu_peak_tops": 38.0,
            "npu_sparsity_support": None,
            "npu_windows_studio_effects": False,
            "thunderbolt_4_support": True,
            "thunderbolt_5_support": True,
            "usb4": True,
            "pcie_revisions": ["4.0"],
            "max_pcie_lanes": None,
            "graphics_output": ["DisplayPort", "HDMI"],
            "instruction_set": "ARMv9.2-A",
            "instruction_extensions": ["NEON", "SME"],
            "intel_64": False,
            "intel_dl_boost": False,
            "intel_thread_director": False,
            "intel_turbo_boost": False,
            "intel_turbo_boost_max_3": False,
            "intel_speed_shift": False,
            "intel_vt_x": False,
            "intel_vt_d": False,
            "intel_aes_ni": False,
            "intel_trusted_execution": False,
            "source_url": "https://support.apple.com/en-us/111910",
            "last_verified": "2026-10-11",
        },
    }


def unify_cpu_specs():
    import cpu_specs
    old_specs = cpu_specs.CPU_SPECS
    unified: dict[str, dict[str, Any]] = {}

    for key, spec in old_specs.items():
        record = dict(spec)

        # 1. Standardize launch_date to "Q[1-4] YYYY"
        if "launch_date" in record:
            record["launch_date"] = normalize_launch_date(record["launch_date"])

        # 2. Standardize Apple memory bandwidth naming
        if "apple_memory_bandwidth_gbs" in record:
            bw = record.pop("apple_memory_bandwidth_gbs")
            if "apple_memory_bandwidth_gbps" not in record or not record["apple_memory_bandwidth_gbps"]:
                record["apple_memory_bandwidth_gbps"] = bw

        # Add missing bandwidth for M2
        if key == "apple_m2" and ("apple_memory_bandwidth_gbps" not in record or not record["apple_memory_bandwidth_gbps"]):
            record["apple_memory_bandwidth_gbps"] = 100

        # 3. Standardize AMD Zen 5 cores naming
        if "zen_5_cores" in record:
            z5 = record.pop("zen_5_cores")
            if "zen5_cores" not in record or record["zen5_cores"] is None:
                record["zen5_cores"] = z5
        if "zen_5c_cores" in record:
            z5c = record.pop("zen_5c_cores")
            if "zen5c_cores" not in record or record["zen5c_cores"] is None:
                record["zen5c_cores"] = z5c

        # 4. Standardize AMD compute units naming
        if "amd_graphics_compute_units" in record:
            cu = record.pop("amd_graphics_compute_units")
            if "gpu_compute_units" not in record or record["gpu_compute_units"] is None:
                record["gpu_compute_units"] = cu

        # 5. Standardize base frequency naming for AMD
        if "base_frequency_mhz" in record and record["base_frequency_mhz"] is not None:
            if "base_clock_mhz" not in record or record["base_clock_mhz"] is None:
                record["base_clock_mhz"] = record["base_frequency_mhz"]
        elif "base_clock_mhz" in record and record["base_clock_mhz"] is not None:
            if "base_frequency_mhz" not in record or record["base_frequency_mhz"] is None:
                record["base_frequency_mhz"] = record["base_clock_mhz"]

        unified[key] = record

    # Add the requested Apple chips
    new_apple = get_apple_new_chips()
    for k, v in new_apple.items():
        unified[k] = v

    print(f"Total unified SKUs: {len(unified)}")
    
    # Save back to cpu_specs.py
    formatted = pprint.pformat(unified, indent=4, sort_dicts=False, width=120)
    content = f"# cpu_specs.py - Canonical Laptop CPU Specifications (2019-2026)\n\nCPU_SPECS = {formatted}\n"
    CPU_SPECS_PATH.write_text(content, encoding="utf-8")
    print(f"[OK] Successfully wrote unified CPU_SPECS to {CPU_SPECS_PATH}")


if __name__ == "__main__":
    unify_cpu_specs()
