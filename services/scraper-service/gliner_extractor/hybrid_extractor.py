"""Hybrid Specification Extractor.

Combines Layer 1 (Dedicated Store Extractor: CompumartsExtractor)
with Layer 2 (Context-Aware Scoped GLiNER Fallback)
for high-precision laptop specification extraction.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from gliner_extractor.compumarts_extractor import CompumartsExtractor, ContextEnvelope
from gliner_extractor.key_matcher import DirectKeyMatcher
from gliner_extractor.wrapper import GLiNERExtractor

logger = logging.getLogger(__name__)


class HybridLaptopExtractor:
    """Two-layer hybrid extractor for laptop specifications."""

    def __init__(self, model_name: str = "urchade/gliner_base", device: str | None = None) -> None:
        self.compumarts_extractor = CompumartsExtractor()
        self.matcher = DirectKeyMatcher()
        self.gliner = GLiNERExtractor(model_name=model_name, device=device, lazy_load=True)

    def extract(
        self,
        title: str,
        specs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        store: str = "compumarts",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Extract laptop specifications using two-tier hybrid architecture.

        Args:
            title: Product title string.
            specs: Scraped specification table dictionary.
            metadata: Optional dictionary with scraper metadata (mpn, sku, brand, etc.).
            store: Store identifier (defaults to 'compumarts').

        Returns:
            Tuple of:
            - structured: Populated catalog-service database specification object.
            - metadata: Extraction metadata (latencies, layers used, compound count).
        """
        start_total = time.perf_counter()
        gliner_calls = 0
        gliner_time_ms = 0.0

        # Tier 1: Dedicated Store Extraction Layer (~0.5 ms)
        t0 = time.perf_counter()
        if store == "compumarts":
            structured, envelopes = self.compumarts_extractor.extract(specs, title, metadata)
        else:
            # Fallback to generic key matcher for any other store
            structured, compound_rows = self.matcher.match_specs(specs)
            envelopes = []
        layer1_time_ms = (time.perf_counter() - t0) * 1000

        # Ingest metadata if fields still missing
        if metadata:
            if metadata.get("mpn") and not structured["identity"].get("manufacturer_part_number"):
                structured["identity"]["manufacturer_part_number"] = metadata["mpn"]
            elif metadata.get("retailer_sku") and not structured["identity"].get("manufacturer_part_number"):
                structured["identity"]["manufacturer_part_number"] = metadata["retailer_sku"]
            if metadata.get("brand") and not structured["identity"].get("brand"):
                structured["identity"]["brand"] = metadata["brand"]

        # Tier 2: Context-Aware GLiNER Fallback for Envelopes
        for env in envelopes:
            target_area = env.target_area

            # Only skip if ALL fields this envelope targets are ALREADY populated in structured
            if target_area == "identity" and all(structured["identity"].get(f) for f in ("brand", "laptop_model", "laptop_family", "manufacturer_part_number")):
                continue
            elif target_area == "cpu" and all(structured["cpu"].get(f) is not None for f in ("model", "line", "cores", "threads", "clock_speed", "manufacturer")):
                continue
            elif target_area == "gpu" and (structured["gpu"].get("model") and structured["gpu"].get("manufacturer") and (structured["gpu"].get("vram_gb") is not None or structured["gpu"].get("integrated"))):
                continue
            elif target_area == "memory" and all(structured["memory"].get(f) is not None for f in ("capacity_gb", "max_supported_gb", "memory_type", "speed", "slot_count")):
                continue
            elif target_area == "storage" and all(structured["storage"].get(f) is not None for f in ("capacity_gb", "storage_type", "interface", "form_factor", "slot_count", "max_supported_gb")):
                continue
            elif target_area == "display" and all(structured["display"].get(f) is not None for f in ("size_inches", "resolution", "refresh_rate_hz", "panel_type", "aspect_ratio")):
                continue
            elif target_area == "power_battery" and all(structured["power_battery"].get(f) is not None for f in ("battery_capacity_wh", "power_adapter_w", "battery_cells")):
                continue
            elif target_area == "connectivity" and all(structured["connectivity"].get(f) is not None for f in ("wifi", "bluetooth", "ethernet")):
                continue
            elif target_area == "physical" and all(structured["physical"].get(f) is not None for f in ("weight_kg", "color", "width_mm")):
                continue
            elif target_area == "operating_system" and structured["operating_system"].get("name") is not None:
                continue
            elif target_area == "build" and all(structured["build"].get(f) is not None for f in ("has_backlit_keyboard", "has_fingerprint")):
                continue
            elif target_area == "audio_webcam" and (structured["webcam"].get("resolution") and structured["audio"].get("microphone") and structured["audio"].get("speaker_count") is not None):
                continue
            # target_area == "unmapped_specs": NEVER skip! Always evaluate!

            # Format rich semantic prompt with surrounding context
            prompt_text = env.format_gliner_text()

            t_gliner = time.perf_counter()
            ents = self.gliner.extract_entities(prompt_text, env.target_labels, threshold=0.35)
            gliner_time_ms += (time.perf_counter() - t_gliner) * 1000
            gliner_calls += 1

            for ent in ents:
                lbl = ent["label"].lower().strip()
                txt = ent["text"].strip()
                if not txt:
                    continue

                # Identity
                if lbl == "laptop brand" and not structured["identity"]["brand"]:
                    structured["identity"]["brand"] = txt
                elif lbl == "laptop model" and not structured["identity"]["laptop_model"]:
                    structured["identity"]["laptop_model"] = txt
                elif lbl == "laptop series" and not structured["identity"]["laptop_family"]:
                    structured["identity"]["laptop_family"] = txt
                elif lbl == "part number" and not structured["identity"]["manufacturer_part_number"]:
                    if not re.search(r"\b(SSD|RAM|DDR|NVMe|PCIe|FHD|QHD|WQXGA|UHD|Hz|Intel|Ryzen|GeForce|RTX|GTX|TB|GB)\b", txt, re.I) and len(txt) <= 30:
                        structured["identity"]["manufacturer_part_number"] = txt

                # CPU
                elif lbl == "processor model" and not structured["cpu"]["model"]:
                    if not re.search(r"\b(NPU|AI Chip)\b", txt, re.I):
                        structured["cpu"]["model"] = txt
                elif lbl == "processor line" and not structured["cpu"]["line"]:
                    structured["cpu"]["line"] = txt
                elif lbl == "processor manufacturer" and not structured["cpu"]["manufacturer"]:
                    structured["cpu"]["manufacturer"] = txt
                elif lbl == "cpu core count" and structured["cpu"]["cores"] is None:
                    m = re.search(r"\d+", txt)
                    if m and int(m.group(0)) in {2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 32}:
                        structured["cpu"]["cores"] = int(m.group(0))
                elif lbl == "cpu thread count" and structured["cpu"]["threads"] is None:
                    m = re.search(r"\d+", txt)
                    if m and int(m.group(0)) in {2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48}:
                        structured["cpu"]["threads"] = int(m.group(0))
                elif lbl == "cpu clock speed" and not structured["cpu"]["clock_speed"]:
                    if re.search(r"\b(?:GHz|MHz)\b", txt, re.I) and not re.search(r"\b\d{2,3}\s*Hz\b", txt):
                        structured["cpu"]["clock_speed"] = txt

                # GPU
                elif lbl == "graphics model" and not structured["gpu"]["model"]:
                    structured["gpu"]["model"] = txt
                elif lbl == "graphics manufacturer" and not structured["gpu"]["manufacturer"]:
                    structured["gpu"]["manufacturer"] = txt
                elif lbl in ("graphics vram", "vram") and structured["gpu"]["vram_gb"] is None:
                    m_v = re.search(r"(\d+)", txt)
                    if m_v and int(m_v.group(0)) in {1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24}:
                        structured["gpu"]["vram_gb"] = int(m_v.group(0))
                elif lbl in ("gpu tdp wattage", "graphics power wattage", "tdp") and structured["gpu"]["tdp_w"] is None:
                    m_w = re.search(r"(\d+)", txt)
                    if m_w:
                        structured["gpu"]["tdp_w"] = int(m_w.group(0))

                # Memory
                elif lbl == "ram capacity" and structured["memory"]["capacity_gb"] is None:
                    m_r = re.search(r"(\d+)", txt)
                    if m_r and int(m_r.group(0)) in {4, 6, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256}:
                        structured["memory"]["capacity_gb"] = int(m_r.group(0))
                elif lbl in ("max ram capacity", "maximum memory") and structured["memory"]["max_supported_gb"] is None:
                    m_mr = re.search(r"(\d+)", txt)
                    if m_mr:
                        mr_val = int(m_mr.group(0))
                        inst_ram = structured["memory"].get("capacity_gb") or 0
                        if mr_val >= inst_ram and mr_val in (8, 16, 24, 32, 48, 64, 96, 128, 192, 256):
                            structured["memory"]["max_supported_gb"] = mr_val
                elif lbl == "ram type" and not structured["memory"]["memory_type"]:
                    m_t = re.search(r"\b(LPDDR5X|LPDDR5|DDR5|DDR4|LPDDR4X|DDR3)\b", txt, re.I)
                    if m_t:
                        structured["memory"]["memory_type"] = m_t.group(1).upper()
                elif lbl == "ram speed" and structured["memory"]["speed"] is None:
                    m_sp = re.search(r"(\d{4})", txt)
                    if m_sp:
                        structured["memory"]["speed"] = int(m_sp.group(0))
                elif lbl == "ram slot count" and structured["memory"]["slot_count"] is None:
                    m_sc = re.search(r"\b([1-4])\b", txt)
                    if m_sc:
                        structured["memory"]["slot_count"] = int(m_sc.group(0))

                # Storage
                elif lbl == "storage capacity" and structured["storage"]["capacity_gb"] is None:
                    m_s = re.search(r"(\d+)", txt)
                    if m_s:
                        val = int(m_s.group(0))
                        val_gb = val * 1024 if val in (1, 2, 4, 8) else val
                        if val_gb >= 64:
                            structured["storage"]["capacity_gb"] = val_gb
                elif lbl == "storage type" and not structured["storage"]["storage_type"]:
                    structured["storage"]["storage_type"] = txt
                elif lbl == "storage interface" and not structured["storage"]["interface"]:
                    structured["storage"]["interface"] = txt
                elif lbl == "storage form factor" and not structured["storage"]["form_factor"]:
                    if not re.search(r"\b(DDR|RAM|GDDR|SO-?DIMM)\b", txt, re.I):
                        m_ff = re.search(r"\b(M\.2\s*(?:2280|2242|2230)?|2\.5(?:\"|\s*inch)?)\b", txt, re.I)
                        if m_ff:
                            structured["storage"]["form_factor"] = m_ff.group(0).strip()
                elif lbl == "storage slot count" and structured["storage"]["slot_count"] is None:
                    m_sl = re.search(r"\b([1-4])\b", txt)
                    if m_sl:
                        structured["storage"]["slot_count"] = int(m_sl.group(0))

                # Display
                elif lbl == "screen size" and structured["display"]["size_inches"] is None:
                    if not re.search(r":\d+", txt):
                        m_sz = re.search(r"(\d{2}(?:\.\d+)?)", txt)
                        if m_sz and 10.0 <= float(m_sz.group(0)) <= 18.5:
                            structured["display"]["size_inches"] = float(m_sz.group(0))
                elif lbl == "screen resolution" and not structured["display"]["resolution"]:
                    m_res = re.search(r"(\d{3,4}\s*[xX×]\s*\d{3,4})", txt)
                    if m_res:
                        structured["display"]["resolution"] = m_res.group(1)
                    else:
                        structured["display"]["resolution"] = txt
                elif lbl in ("refresh rate", "display refresh rate") and structured["display"]["refresh_rate_hz"] is None:
                    m_hz = re.search(r"(\d{2,3})\s*Hz", txt, re.I)
                    if m_hz and int(m_hz.group(1)) in {60, 90, 120, 144, 165, 180, 240, 300, 360, 480}:
                        structured["display"]["refresh_rate_hz"] = int(m_hz.group(1))
                elif lbl in ("panel type", "display panel type") and not structured["display"]["panel_type"]:
                    m_pt = re.search(r"\b(IPS|OLED|AMOLED|Mini[- ]?LED|VA|TN|WVA)\b", txt, re.I)
                    if m_pt:
                        structured["display"]["panel_type"] = m_pt.group(1).upper()
                elif lbl == "aspect ratio" and not structured["display"]["aspect_ratio"]:
                    m_ar = re.search(r"\b(16:9|16:10|3:2)\b", txt)
                    if m_ar:
                        structured["display"]["aspect_ratio"] = m_ar.group(1)

                # Power & Battery
                elif lbl in ("battery capacity wh", "battery capacity") and structured["power_battery"]["battery_capacity_wh"] is None:
                    m_wh = re.search(r"(\d+(?:\.\d+)?)\s*(?:Wh|W/hr)", txt, re.I)
                    if m_wh:
                        structured["power_battery"]["battery_capacity_wh"] = float(m_wh.group(1))
                elif lbl in ("power adapter wattage", "adapter") and structured["power_battery"]["power_adapter_w"] is None:
                    m_pw = re.search(r"(\d+)\s*(?:W|Watt)", txt, re.I)
                    if m_pw:
                        structured["power_battery"]["power_adapter_w"] = int(m_pw.group(1))
                elif lbl in ("battery cells", "cells") and structured["power_battery"]["battery_cells"] is None:
                    m_c = re.search(r"\b([2-6])\s*(?:cell|cells)?", txt, re.I)
                    if m_c:
                        structured["power_battery"]["battery_cells"] = int(m_c.group(1))

                # Connectivity
                elif lbl == "wifi standard" and not structured["connectivity"]["wifi"]:
                    structured["connectivity"]["wifi"] = txt
                elif lbl == "bluetooth version" and not structured["connectivity"]["bluetooth"]:
                    if not re.search(r"(?:DP|DisplayPort|HDMI|USB|Hz|GHz)", txt, re.I):
                        if re.search(r"Bluetooth|BT|\b[45]\.\d\b", txt, re.I):
                            structured["connectivity"]["bluetooth"] = txt
                elif lbl == "ethernet speed" and not structured["connectivity"]["ethernet"]:
                    if not re.search(r"(?:Hz|GHz|MHz|RAM|SSD|DDR|GB|TB)", txt, re.I):
                        if re.search(r"\b(Gigabit|Gbps|Mbps|LAN|RJ-?45|Ethernet)\b", txt, re.I):
                            structured["connectivity"]["ethernet"] = txt

                # Physical
                elif lbl == "laptop weight" and structured["physical"]["weight_kg"] is None:
                    m_w = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilo)", txt, re.I)
                    if m_w:
                        structured["physical"]["weight_kg"] = float(m_w.group(1))
                elif lbl == "laptop color" and not structured["physical"]["color"]:
                    if len(txt) < 40 and not re.search(r"\b\d+\s*x\s*\d+\b", txt):
                        structured["physical"]["color"] = txt

                # OS
                elif lbl == "operating system name" and not structured["operating_system"]["name"]:
                    structured["operating_system"]["name"] = txt

                # Build & Security
                elif lbl == "backlit keyboard" and structured["build"]["has_backlit_keyboard"] is None:
                    structured["build"]["has_backlit_keyboard"] = "yes" in txt.lower() or "backlit" in txt.lower() or "true" in txt.lower()
                elif lbl == "fingerprint reader" and structured["build"]["has_fingerprint"] is None:
                    structured["build"]["has_fingerprint"] = "yes" in txt.lower() or "fingerprint" in txt.lower() or "true" in txt.lower()

                # Audio & Webcam
                elif lbl == "webcam resolution" and not structured["webcam"]["resolution"]:
                    structured["webcam"]["resolution"] = txt
                elif lbl == "microphone" and not structured["audio"]["microphone"]:
                    structured["audio"]["microphone"] = txt
                elif lbl == "speaker count" and structured["audio"]["speaker_count"] is None:
                    m_spk = re.search(r"\b([1-8])\b", txt)
                    if m_spk:
                        val = int(m_spk.group(1))
                        if 1 <= val <= 8:
                            structured["audio"]["speaker_count"] = val

        # Tier 2.5: Identity resolution (Model/Family from Title) if still missing
        needs_model = not structured["identity"].get("laptop_model")
        needs_family = not structured["identity"].get("laptop_family")
        if title and (needs_model or needs_family or not structured["identity"].get("manufacturer_part_number")):
            # Extract part number or model code via regex first
            m_code = re.search(r"\b([A-Z0-9]{3,8}-[A-Z0-9]{2,6}(?:-[A-Z0-9]{2,6})?|[0-9]{2}[A-Z0-9]{6,10})\b", title)
            if m_code:
                code_str = m_code.group(1)
                if not structured["identity"].get("manufacturer_part_number"):
                    structured["identity"]["manufacturer_part_number"] = code_str
                if not structured["identity"].get("laptop_model"):
                    structured["identity"]["laptop_model"] = code_str

            if not structured["identity"].get("laptop_family"):
                t_gliner = time.perf_counter()
                identity_labels = ["laptop family", "laptop model"]
                ents = self.gliner.extract_entities(title, identity_labels, threshold=0.35)
                gliner_time_ms += (time.perf_counter() - t_gliner) * 1000
                gliner_calls += 1

                for ent in ents:
                    lbl = ent["label"]
                    txt = ent["text"].strip()
                    if any(hw in txt.lower() for hw in ["intel", "amd", "ryzen", "rtx", "geforce", "core", "ddr", "ssd", "ips", "hz"]):
                        continue
                    if lbl == "laptop family" and not structured["identity"]["laptop_family"]:
                        structured["identity"]["laptop_family"] = txt
                    elif lbl == "laptop model" and not structured["identity"]["laptop_model"]:
                        structured["identity"]["laptop_model"] = txt

        total_time_ms = (time.perf_counter() - start_total) * 1000

        metadata_res = {
            "total_time_ms": round(total_time_ms, 2),
            "layer1_time_ms": round(layer1_time_ms, 3),
            "gliner_time_ms": round(gliner_time_ms, 2),
            "gliner_calls_count": gliner_calls,
            "envelopes_count": len(envelopes),
        }

        return structured, metadata_res
