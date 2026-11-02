"""OpenIcecat Live JSON API Service & Structured Spec Parser.

Fetches full 21-group hardware specifications from Icecat's JSON API:
`https://live.icecat.biz/api/?UserName=openIcecat-live&Language=en&icecat_id={id}`
and maps them deterministically into our 11-category specification schema.
"""

from __future__ import annotations

import re
import time
from typing import Any

from curl_cffi import requests

from app.common.logger import get_logger
from app.pipeline.physical_validator import PhysicalValidator

logger = get_logger("pipeline.icecat.api")

OPENICECAT_LIVE_API = "https://live.icecat.biz/api/"


def _to_bool(raw_val: str | None, pres_val: str | None) -> bool | None:
    """Convert Icecat Y/N or Yes/No strings into Python bool."""
    for v in (raw_val, pres_val):
        if not v:
            continue
        s = str(v).strip().lower()
        if s in ("y", "yes", "true", "1", "supported", "installed"):
            return True
        if s in ("n", "no", "false", "0", "not installed", "not supported"):
            return False
    return None


def _to_float(val: str | float | int | None) -> float | None:
    """Extract first valid float from string."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"(\d+(?:\.\d+)?)", str(val))
    return float(m.group(1)) if m else None


def _to_int(val: str | float | int | None) -> int | None:
    """Extract first valid int from string."""
    f = _to_float(val)
    return int(round(f)) if f is not None else None


class IcecatAPIService:
    """Fetches and parses structured product specification sheets from OpenIcecat Live JSON API."""

    def __init__(self, timeout: int = 15, request_delay: float = 0.25) -> None:
        self.timeout = timeout
        self.request_delay = request_delay
        self.session = requests.Session(impersonate="chrome120")
        self.validator = PhysicalValidator()

    def fetch_product_data(self, icecat_id: int | str, max_retries: int = 3) -> dict[str, Any] | None:
        """Fetch raw JSON `data` object from live.icecat.biz/api for a given icecat_id."""
        params = {
            "UserName": "openIcecat-live",
            "Language": "en",
            "icecat_id": str(icecat_id),
        }
        for attempt in range(1, max_retries + 1):
            try:
                if self.request_delay > 0:
                    time.sleep(self.request_delay)
                resp = self.session.get(OPENICECAT_LIVE_API, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    payload = resp.json()
                    data = payload.get("data")
                    if data and isinstance(data, dict):
                        return data
                    logger.warning("OpenIcecat API returned empty data for icecat_id=%s", icecat_id)
                    return None
                elif resp.status_code == 429:
                    time.sleep(3 * attempt)
                else:
                    logger.warning(
                        "OpenIcecat API returned status %d for icecat_id=%s",
                        resp.status_code,
                        icecat_id,
                    )
            except Exception as e:
                logger.warning(
                    "OpenIcecat API error for icecat_id=%s (attempt %d/%d): %s",
                    icecat_id,
                    attempt,
                    max_retries,
                    e,
                )
                time.sleep(1.5 * attempt)
        return None

    def parse_product_json(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Translate Icecat `FeaturesGroups` JSON into our 11-category specification schema."""
        features_map: dict[str, tuple[str, str]] = {}
        for group in data.get("FeaturesGroups", []) or []:
            for feat in group.get("Features", []) or []:
                f_name = ((feat.get("Feature") or {}).get("Name") or {}).get("Value")
                if not f_name:
                    continue
                pres = str(feat.get("PresentationValue") or "").strip()
                raw = str(feat.get("RawValue") or "").strip()
                features_map[f_name.strip().lower()] = (pres, raw)

        def get_pres(key: str) -> str | None:
            pair = features_map.get(key.lower())
            return pair[0] if pair and pair[0] else None

        def get_raw(key: str) -> str | None:
            pair = features_map.get(key.lower())
            return pair[1] if pair and pair[1] else None

        def get_bool(key: str) -> bool | None:
            pair = features_map.get(key.lower())
            if not pair:
                return None
            return _to_bool(pair[1], pair[0])

        parsed: dict[str, dict[str, Any]] = {
            "identity": {},
            "cpu": {},
            "gpu": {},
            "memory": {},
            "storage": {},
            "display": {},
            "power_battery": {},
            "physical": {},
            "connectivity": {},
            "audio_webcam": {},
            "build_security": {},
        }

        # 1. Identity & Design (Never overwrite regional MPN or OS)
        color_name = get_pres("Colour name") or get_pres("Product colour")
        if color_name:
            parsed["identity"]["color"] = color_name

        base_color = get_pres("Product colour")
        if base_color:
            parsed["identity"]["base_color"] = base_color

        form_factor = get_pres("Form factor")
        if form_factor:
            parsed["identity"]["form_factor"] = form_factor

        market_pos = get_pres("Market positioning")
        if market_pos:
            parsed["identity"]["market_positioning"] = market_pos

        intro_year = _to_int(get_raw("Introduction year") or get_pres("Introduction year"))
        if intro_year and 2015 <= intro_year <= 2030:
            parsed["identity"]["release_year"] = intro_year

        # 2. CPU Supplements (Silicon dictionary remains primary owner; these fill missing fields)
        cpu_mfr = get_pres("Processor manufacturer") or ""
        cpu_fam = get_pres("Processor family") or ""
        cpu_mod = get_pres("Processor model") or ""
        if cpu_fam or cpu_mod:
            parsed["cpu"]["_icecat_cpu_text"] = f"{cpu_mfr} {cpu_fam} {cpu_mod}".strip()

        cpu_base_w = _to_float(get_raw("Processor base power") or get_pres("Processor base power"))
        if cpu_base_w and 5 <= cpu_base_w <= 200:
            parsed["cpu"]["base_power_w"] = cpu_base_w
            parsed["cpu"]["tdp_w"] = cpu_base_w

        cpu_turbo_w = _to_float(get_raw("Maximum turbo power") or get_pres("Maximum turbo power"))
        if cpu_turbo_w and 10 <= cpu_turbo_w <= 300:
            parsed["cpu"]["max_turbo_power_w"] = cpu_turbo_w

        npu_tops = _to_float(
            get_raw("NPU performance up to")
            or get_pres("NPU performance up to")
            or get_raw("Total processor performance up to")
        )
        if npu_tops:
            parsed["cpu"]["npu_tops"] = npu_tops

        cpu_cores = _to_int(get_raw("Processor cores") or get_pres("Processor cores"))
        if cpu_cores and 2 <= cpu_cores <= 64:
            parsed["cpu"]["cores"] = cpu_cores

        cpu_threads = _to_int(get_raw("Processor threads") or get_pres("Processor threads"))
        if cpu_threads and 2 <= cpu_threads <= 128:
            parsed["cpu"]["threads"] = cpu_threads

        cpu_base_ghz = _to_float(get_raw("Processor frequency") or get_pres("Processor frequency"))
        if cpu_base_ghz and 0.8 <= cpu_base_ghz <= 6.0:
            parsed["cpu"]["clock_base_ghz"] = cpu_base_ghz

        cpu_boost_ghz = _to_float(get_raw("Processor boost frequency") or get_pres("Processor boost frequency"))
        if cpu_boost_ghz and 1.5 <= cpu_boost_ghz <= 6.5:
            parsed["cpu"]["clock_boost_ghz"] = cpu_boost_ghz

        l3_mb = _to_float(get_raw("L3 cache") or get_pres("L3 cache") or get_raw("Processor cache"))
        l2_mb = _to_float(get_raw("L2 cache") or get_pres("L2 cache"))
        if l3_mb and 2 <= l3_mb <= 256:
            parsed["cpu"]["cache_mb"] = round(l3_mb + (l2_mb or 0.0), 1) if l2_mb else round(l3_mb, 1)

        # 3. GPU Supplements (GPU dictionary remains primary owner)
        gpu_tdp = _to_float(get_raw("Maximum graphics card power") or get_pres("Maximum graphics card power"))
        if gpu_tdp and 15 <= gpu_tdp <= 250:
            parsed["gpu"]["tdp_w"] = gpu_tdp

        vram_type = get_pres("Discrete graphics memory type")
        if vram_type and vram_type.upper() not in ("N", "NO", "NONE", "NOT AVAILABLE"):
            parsed["gpu"]["vram_type"] = vram_type

        igpu_model = get_pres("On-board graphics card model")
        if igpu_model and igpu_model.upper() not in ("N", "NO", "NONE", "NOT AVAILABLE"):
            parsed["gpu"]["igpu_model"] = igpu_model

        dgpu_model = get_pres("Discrete graphics card model") or ""
        if dgpu_model and dgpu_model.upper() not in ("N", "NO", "NONE", "NOT AVAILABLE"):
            parsed["gpu"]["_icecat_gpu_text"] = dgpu_model
        elif igpu_model and igpu_model.upper() not in ("N", "NO", "NONE", "NOT AVAILABLE"):
            parsed["gpu"]["_icecat_gpu_text"] = igpu_model

        # 4. Memory
        mem_gb = _to_int(get_raw("Internal memory") or get_pres("Internal memory"))
        if mem_gb and mem_gb in (4, 8, 12, 16, 18, 24, 32, 36, 48, 64, 96, 128):
            parsed["memory"]["capacity_gb"] = mem_gb

        mem_type_raw = get_pres("Internal memory type") or ""
        m_ddr = re.search(r"\b(LPDDR5X|LPDDR5|LPDDR4X|LPDDR4|DDR5|DDR4|DDR3)\b", mem_type_raw, re.IGNORECASE)
        if m_ddr:
            parsed["memory"]["memory_type"] = m_ddr.group(1).upper()

        mem_speed_mhz = _to_int(get_raw("Memory clock speed") or get_pres("Memory clock speed"))
        if mem_speed_mhz and 1600 <= mem_speed_mhz <= 10000:
            parsed["memory"]["speed"] = f"{mem_speed_mhz} MHz"

        max_mem_gb = _to_int(get_raw("Maximum internal memory") or get_pres("Maximum internal memory"))
        if max_mem_gb and 4 <= max_mem_gb <= 256:
            parsed["memory"]["max_supported_gb"] = max_mem_gb

        mem_form_pres = get_pres("Memory form factor")
        if mem_form_pres:
            parsed["memory"]["form_factor"] = mem_form_pres

        mem_channels = get_pres("Memory channels")
        if mem_channels:
            parsed["memory"]["channels"] = mem_channels

        mem_layout = get_pres("Memory layout (slots x size)")
        if mem_layout:
            parsed["memory"]["layout"] = mem_layout

        mem_form = (mem_form_pres or "").lower()
        mem_slots_str = get_pres("Memory slots") or mem_layout or ""
        if "on-board" in mem_form or "onboard" in mem_form or "soldered" in mem_form:
            parsed["memory"]["is_soldered"] = True
            parsed["memory"]["slot_count"] = 0
        elif mem_slots_str:
            m_slots = re.search(r"\b([1-4])\s*x\b", mem_slots_str, re.IGNORECASE) or re.search(
                r"^([1-4])\b", mem_slots_str.strip()
            )
            if m_slots:
                parsed["memory"]["slot_count"] = int(m_slots.group(1))
                parsed["memory"]["is_soldered"] = False

        # 5. Storage
        storage_pres = (
            get_pres("Total storage capacity") or get_pres("Total SSDs capacity") or get_pres("SSD capacity") or ""
        )
        storage_raw = _to_int(
            get_raw("Total storage capacity") or get_raw("Total SSDs capacity") or get_raw("SSD capacity")
        )
        if storage_raw:
            if "tb" in storage_pres.lower() and storage_raw <= 8:
                parsed["storage"]["capacity_gb"] = storage_raw * 1024
            elif storage_raw == 1000:
                parsed["storage"]["capacity_gb"] = 1024
            elif storage_raw == 2000:
                parsed["storage"]["capacity_gb"] = 2048
            elif storage_raw >= 64:
                parsed["storage"]["capacity_gb"] = storage_raw

        storage_media = (get_pres("Storage media") or "").upper()
        if "SSD" in storage_media:
            parsed["storage"]["storage_type"] = "SSD"
        elif "HDD" in storage_media:
            parsed["storage"]["storage_type"] = "HDD"
        elif "EMMC" in storage_media:
            parsed["storage"]["storage_type"] = "eMMC"

        ssd_iface = (get_pres("SSD interface") or "").lower()
        has_nvme = get_bool("NVMe") or ("nvme" in ssd_iface)
        if "5.0" in ssd_iface:
            parsed["storage"]["interface"] = "PCIe 5.0 NVMe" if has_nvme else "PCIe 5.0"
        elif "4.0" in ssd_iface:
            parsed["storage"]["interface"] = "PCIe 4.0 NVMe" if has_nvme else "PCIe 4.0"
        elif "3.0" in ssd_iface:
            parsed["storage"]["interface"] = "PCIe 3.0 NVMe" if has_nvme else "PCIe 3.0"
        elif "pci" in ssd_iface or has_nvme:
            parsed["storage"]["interface"] = "PCIe NVMe"
        elif "sata" in ssd_iface:
            parsed["storage"]["interface"] = "SATA"

        ssd_ff = get_pres("SSD form factor") or ""
        if "m.2" in ssd_ff.lower():
            if "2280" in ssd_ff:
                parsed["storage"]["form_factor"] = "M.2 2280"
            elif "2242" in ssd_ff:
                parsed["storage"]["form_factor"] = "M.2 2242"
            else:
                parsed["storage"]["form_factor"] = "M.2"
        elif "2.5" in ssd_ff:
            parsed["storage"]["form_factor"] = "2.5-inch"

        ssd_count = _to_int(get_raw("Number of SSDs installed") or get_pres("Number of SSDs installed"))
        if ssd_count and 1 <= ssd_count <= 4:
            parsed["storage"]["installed_ssd_count"] = ssd_count

        # 6. Display
        diag_in = _to_float(get_raw("Display diagonal"))
        if not diag_in:
            m_in = re.search(r"\((\d{2}(?:\.\d)?)\s*\"", get_pres("Display diagonal") or "")
            if m_in:
                diag_in = float(m_in.group(1))
        if diag_in and 10.0 <= diag_in <= 19.0:
            parsed["display"]["size_inches"] = diag_in

        res_raw = get_raw("Display resolution") or get_pres("Display resolution") or ""
        m_res = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", res_raw)
        if m_res:
            w_px, h_px = int(m_res.group(1)), int(m_res.group(2))
            parsed["display"]["resolution"] = f"{w_px}x{h_px}"
            parsed["display"]["resolution_width"] = w_px
            parsed["display"]["resolution_height"] = h_px

        hd_type = get_pres("HD type")
        if hd_type:
            parsed["display"]["hd_type"] = hd_type

        hz = _to_int(get_raw("Maximum refresh rate") or get_pres("Maximum refresh rate"))
        if hz and 60 <= hz <= 500:
            parsed["display"]["refresh_rate_hz"] = hz

        panel = (get_pres("Panel type") or "").upper()
        for p_type in ("OLED", "AMOLED", "MINI-LED", "IPS", "VA", "TN", "WVA"):
            if p_type in panel:
                parsed["display"]["panel_type"] = (
                    "IPS" if p_type == "WVA" else ("Mini-LED" if p_type == "MINI-LED" else p_type)
                )
                break

        aspect = get_raw("Native aspect ratio") or get_pres("Native aspect ratio")
        if aspect and re.match(r"^\d{1,2}:\d{1,2}$", aspect.strip()):
            parsed["display"]["aspect_ratio"] = aspect.strip()

        touch = get_bool("Touchscreen")
        if touch is not None:
            parsed["display"]["touchscreen"] = touch

        nits = _to_int(get_raw("Display brightness") or get_pres("Display brightness"))
        if nits and 150 <= nits <= 2000:
            parsed["display"]["brightness_nits"] = nits

        gamut_pct = get_pres("Colour gamut")
        gamut_space = get_pres("RGB colour space")
        if gamut_pct and gamut_space:
            pct_str = gamut_pct if "%" in gamut_pct else f"{gamut_pct}%"
            parsed["display"]["color_gamut"] = f"{pct_str} {gamut_space}"
        elif gamut_space:
            parsed["display"]["color_gamut"] = gamut_space

        resp_ms = _to_float(get_raw("Display response rise/fall") or get_pres("Display response rise/fall"))
        if resp_ms and 0.1 <= resp_ms <= 50:
            parsed["display"]["response_time_ms"] = resp_ms

        if get_bool("Anti-glare screen") is True:
            parsed["display"]["surface_treatment"] = "Anti-glare"
        else:
            disp_surface = (get_pres("Display surface") or "").lower()
            if "matt" in disp_surface or "anti-glare" in disp_surface:
                parsed["display"]["surface_treatment"] = "Anti-glare"
            elif "gloss" in disp_surface:
                parsed["display"]["surface_treatment"] = "Glossy"

        hdr_tech = get_pres("High Dynamic Range (HDR) technology")
        hdr_supp = get_bool("High Dynamic Range (HDR) supported")
        if hdr_tech:
            parsed["display"]["hdr"] = hdr_tech
        elif hdr_supp is not None:
            parsed["display"]["hdr"] = hdr_supp

        gsync = get_bool("NVIDIA G-SYNC")
        freesync = get_bool("AMD FreeSync")
        if gsync is True and freesync is True:
            parsed["display"]["adaptive_sync"] = "G-SYNC / FreeSync"
        elif gsync is True:
            parsed["display"]["adaptive_sync"] = "G-SYNC"
        elif freesync is True:
            parsed["display"]["adaptive_sync"] = "FreeSync"

        # 7. Power & Battery
        batt_wh = _to_float(get_raw("Battery capacity") or get_pres("Battery capacity"))
        if batt_wh and 20.0 <= batt_wh <= 105.0:
            parsed["power_battery"]["battery_capacity_wh"] = batt_wh

        adapter_w = _to_float(get_raw("AC adapter power") or get_pres("AC adapter power"))
        if adapter_w and 30.0 <= adapter_w <= 500.0:
            parsed["power_battery"]["power_adapter_w"] = adapter_w

        cells = _to_int(get_raw("Number of battery cells") or get_pres("Number of battery cells"))
        if cells and 1 <= cells <= 12:
            parsed["power_battery"]["battery_cells"] = cells

        batt_tech = get_pres("Battery technology")
        if batt_tech:
            parsed["power_battery"]["battery_type"] = batt_tech

        usb_pd = get_bool("USB Power Delivery (USB PD)")
        usbc_chg = get_bool("USB Type-C charging port")
        if usb_pd is True or usbc_chg is True:
            parsed["power_battery"]["usb_c_pd_charging"] = True
        elif usb_pd is False and usbc_chg is False:
            parsed["power_battery"]["usb_c_pd_charging"] = False

        fast_chg = get_bool("Fast charging")
        if fast_chg is None:
            fast_chg = usb_pd
        if fast_chg is not None:
            parsed["power_battery"]["fast_charging"] = fast_chg

        fast_chg_50 = _to_int(get_raw("Fast charging time (50%)") or get_pres("Fast charging time (50%)"))
        if fast_chg_50 and 10 <= fast_chg_50 <= 120:
            parsed["power_battery"]["fast_charge_50_mins"] = fast_chg_50

        # 8. Physical (Weight & Dimensions)
        weight_pres = get_pres("Weight") or ""
        weight_raw = _to_float(get_raw("Weight"))
        if weight_raw:
            if weight_raw > 20.0:
                weight_kg = round(weight_raw / 1000.0, 2)
            else:
                weight_kg = round(weight_raw, 2)
        else:
            weight_kg = _to_float(weight_pres)
        if weight_kg and 0.5 <= weight_kg <= 6.0:
            parsed["physical"]["weight_kg"] = weight_kg

        width_raw = _to_float(get_raw("Width") or get_pres("Width"))
        if width_raw:
            width_mm = width_raw * 10.0 if width_raw < 50.0 else width_raw
            if 200.0 <= width_mm <= 450.0:
                parsed["physical"]["width_mm"] = round(width_mm, 1)

        depth_raw = _to_float(get_raw("Depth") or get_pres("Depth"))
        if depth_raw:
            depth_mm = depth_raw * 10.0 if depth_raw < 50.0 else depth_raw
            if 150.0 <= depth_mm <= 380.0:
                parsed["physical"]["depth_mm"] = round(depth_mm, 1)

        h_front_raw = _to_float(get_raw("Height (front)") or get_pres("Height (front)"))
        if h_front_raw:
            h_front_mm = h_front_raw * 10.0 if h_front_raw < 5.0 else h_front_raw
            if 5.0 <= h_front_mm <= 55.0:
                parsed["physical"]["height_front_mm"] = round(h_front_mm, 1)

        h_rear_raw = _to_float(get_raw("Height (rear)") or get_pres("Height (rear)"))
        if h_rear_raw:
            h_rear_mm = h_rear_raw * 10.0 if h_rear_raw < 5.0 else h_rear_raw
            if 5.0 <= h_rear_mm <= 55.0:
                parsed["physical"]["height_rear_mm"] = round(h_rear_mm, 1)

        height_raw = _to_float(get_raw("Height") or get_raw("Height (rear)") or get_raw("Height (front)"))
        if height_raw:
            height_mm = height_raw * 10.0 if height_raw < 5.0 else height_raw
            if 5.0 <= height_mm <= 55.0:
                parsed["physical"]["height_mm"] = round(height_mm, 1)

        # 9. Connectivity & Ports
        wifi = get_pres("Top Wi-Fi standard") or get_pres("Wi-Fi standards")
        if wifi and wifi.lower() not in ("n", "no", "none"):
            parsed["connectivity"]["wifi"] = wifi

        antenna = get_pres("Antenna type")
        if antenna and antenna.lower() not in ("n", "no", "none"):
            parsed["connectivity"]["wifi_antenna"] = antenna

        bt_ver = get_pres("Bluetooth version")
        if bt_ver:
            parsed["connectivity"]["bluetooth"] = (
                f"Bluetooth {bt_ver}" if not bt_ver.lower().startswith("bluetooth") else bt_ver
            )
        elif get_bool("Bluetooth") is True:
            parsed["connectivity"]["bluetooth"] = "Yes"

        eth = get_bool("Ethernet LAN")
        if eth is not None:
            parsed["connectivity"]["ethernet"] = eth

        eth_rates = get_pres("Ethernet LAN data rates") or ""
        if "2500" in eth_rates:
            parsed["connectivity"]["ethernet_speed"] = "2.5 Gbps"
        elif "1000" in eth_rates:
            parsed["connectivity"]["ethernet_speed"] = "1 Gbps"
        elif "100" in eth_rates:
            parsed["connectivity"]["ethernet_speed"] = "100 Mbps"

        mob_conn = get_bool("Mobile network connection")
        mob_gen = get_pres("Mobile network generation")
        if mob_conn is True:
            parsed["connectivity"]["cellular"] = mob_gen or "Yes"
        elif mob_conn is False:
            parsed["connectivity"]["cellular"] = "No"

        usbc_dp = get_bool("USB Type-C DisplayPort Alternate Mode")
        if usbc_dp is not None:
            parsed["connectivity"]["usb_c_displayport"] = usbc_dp

        if usb_pd is True or usbc_chg is True:
            parsed["connectivity"]["usb_c_power_delivery"] = True
        elif usb_pd is False and usbc_chg is False:
            parsed["connectivity"]["usb_c_power_delivery"] = False

        card_rdr = get_bool("Card reader integrated")
        if card_rdr is not None:
            parsed["connectivity"]["has_card_reader"] = card_rdr

        card_types = get_pres("Compatible memory cards")
        if card_types and card_types.lower() not in ("n", "no", "none"):
            parsed["connectivity"]["card_reader_type"] = card_types

        tb4_qty = _to_int(get_raw("Thunderbolt 4 ports quantity"))
        tb3_qty = _to_int(get_raw("Thunderbolt 3 ports quantity"))
        if (tb4_qty and tb4_qty > 0) or get_bool("Intel® Thunderbolt 4") or get_bool("Intel Thunderbolt 4"):
            parsed["connectivity"]["thunderbolt_version"] = "Thunderbolt 4"
        elif tb3_qty and tb3_qty > 0:
            parsed["connectivity"]["thunderbolt_version"] = "Thunderbolt 3"

        ports_list: list[str] = []
        port_mappings = [
            ("USB 2.0 ports quantity", "USB 2.0"),
            ("USB 3.2 Gen 1 (3.1 Gen 1) Type-A ports quantity", "USB 3.2 Gen 1 Type-A"),
            ("USB 3.2 Gen 2 (3.1 Gen 2) Type-A ports quantity", "USB 3.2 Gen 2 Type-A"),
            ("USB 3.2 Gen 1 (3.1 Gen 1) Type-C ports quantity", "USB 3.2 Gen 1 Type-C"),
            ("USB 3.2 Gen 2 (3.1 Gen 2) Type-C ports quantity", "USB 3.2 Gen 2 Type-C"),
            ("USB 3.2 Gen 2x2 Type-C ports quantity", "USB 3.2 Gen 2x2 Type-C"),
            ("USB4 Gen 2x2 ports quantity", "USB4"),
            ("USB4 Gen 3x2 ports quantity", "USB4"),
            ("Thunderbolt 4 ports quantity", "Thunderbolt 4"),
            ("Thunderbolt 3 ports quantity", "Thunderbolt 3"),
            ("HDMI ports quantity", f"HDMI {get_pres('HDMI version')}" if get_pres("HDMI version") else "HDMI"),
            ("Mini DisplayPorts quantity", "Mini DisplayPort"),
            ("Ethernet LAN (RJ-45) ports", "RJ-45 Ethernet"),
        ]
        for feat_key, label in port_mappings:
            qty = _to_int(get_raw(feat_key) or get_pres(feat_key))
            if qty and qty > 0:
                ports_list.append(f"{qty}x {label.strip()}")
        if get_bool("Combo headphone/mic port"):
            ports_list.append("1x Combo Audio Jack")
        if ports_list:
            parsed["connectivity"]["ports"] = ports_list

        # 10. Audio & Webcam
        speakers = _to_int(get_raw("Number of built-in speakers") or get_pres("Number of built-in speakers"))
        if speakers and 1 <= speakers <= 8:
            parsed["audio_webcam"]["speaker_count"] = speakers

        spk_power = _to_float(get_raw("Speaker power") or get_pres("Speaker power"))
        if spk_power and 0.5 <= spk_power <= 25.0:
            parsed["audio_webcam"]["speaker_power_w"] = spk_power

        audio_sys = get_pres("Audio system") or get_pres("Speaker manufacturer")
        if audio_sys and audio_sys.lower() not in ("n", "no", "none", "na"):
            parsed["audio_webcam"]["audio_system"] = audio_sys

        cam_hd = get_pres("Front camera HD type") or ""
        cam_res = get_pres("Front camera resolution") or ""
        cam_mp = get_pres("Front camera resolution (numeric)")
        if "full hd" in cam_hd.lower() or "1920 x 1080" in cam_res:
            parsed["audio_webcam"]["webcam_resolution"] = "1080p"
        elif "ultra hd" in cam_hd.lower() or "4k" in cam_hd.lower() or "3840 x 2160" in cam_res:
            parsed["audio_webcam"]["webcam_resolution"] = "4K"
        elif "qhd" in cam_hd.lower() or "2560 x 1440" in cam_res:
            parsed["audio_webcam"]["webcam_resolution"] = "1440p"
        elif "hd" in cam_hd.lower() or "1280 x 720" in cam_res:
            parsed["audio_webcam"]["webcam_resolution"] = "720p"
        elif cam_mp:
            parsed["audio_webcam"]["webcam_resolution"] = cam_mp

        ir_cam = get_bool("Infrared (IR) camera")
        if ir_cam is not None:
            parsed["audio_webcam"]["has_ir_camera"] = ir_cam

        priv_cam = get_bool("Privacy camera")
        if priv_cam is not None:
            parsed["audio_webcam"]["has_privacy_shutter"] = priv_cam

        mic = get_bool("Built-in microphone")
        if mic is not None:
            parsed["audio_webcam"]["microphone"] = mic

        # 11. Build & Security
        backlit = get_bool("Keyboard backlit")
        if backlit is not None:
            parsed["build_security"]["has_backlit_keyboard"] = backlit

        kb_zone = get_pres("Keyboard backlit zone")
        kb_color = get_pres("Keyboard backlit colour")
        if kb_zone:
            if "per-key" in kb_zone.lower():
                parsed["build_security"]["keyboard_backlight_type"] = "Per-Key RGB"
            elif re.search(r"\b4-zone\b", kb_zone.lower()):
                parsed["build_security"]["keyboard_backlight_type"] = "RGB 4-Zone"
            elif "rgb" in kb_zone.lower():
                parsed["build_security"]["keyboard_backlight_type"] = kb_zone.strip()
        elif kb_color:
            if "rgb" in kb_color.lower():
                parsed["build_security"]["keyboard_backlight_type"] = "RGB"
            elif "white" in kb_color.lower():
                parsed["build_security"]["keyboard_backlight_type"] = "Single Color (White)"
            elif "blue" in kb_color.lower():
                parsed["build_security"]["keyboard_backlight_type"] = "Single Color (Blue)"

        fp = get_bool("Fingerprint reader")
        if fp is not None:
            parsed["build_security"]["has_fingerprint"] = fp

        numpad = get_bool("Numeric keypad")
        if numpad is not None:
            parsed["build_security"]["has_numpad"] = numpad

        copilot = get_bool("Copilot key")
        if copilot is not None:
            parsed["build_security"]["has_copilot_key"] = copilot

        material = get_pres("Housing material")
        if material:
            parsed["build_security"]["chassis_material"] = material

        pointing = get_pres("Pointing device")
        if pointing:
            parsed["build_security"]["pointing_device"] = pointing

        sec_features: list[str] = []
        if get_bool("Trusted Platform Module (TPM)"):
            tpm_v = get_pres("Trusted Platform Module (TPM) version")
            sec_features.append(f"TPM {tpm_v}" if tpm_v else "TPM")
        if get_bool("Windows Hello"):
            sec_features.append("Windows Hello")
        if get_bool("Face recognition"):
            sec_features.append("Face Recognition")
        if get_bool("Cable lock slot"):
            lock_t = get_pres("Cable lock slot type (1)") or get_pres("Cable lock slot type")
            sec_features.append(f"{lock_t} Lock" if lock_t else "Cable Lock Slot")
        if get_bool("Password protection"):
            pwd_t = get_pres("Password protection type")
            sec_features.append(f"Password Protection ({pwd_t})" if pwd_t else "Password Protection")
        if sec_features:
            parsed["build_security"]["security_features"] = sec_features

        return parsed
