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
from gliner_extractor.schema import empty_structured
from gliner_extractor.validators import (
    clean_text,
    compute_aspect_ratio,
    normalize_cpu_line,
    validate_battery_capacity,
    validate_battery_cells,
    validate_consistency,
    validate_bluetooth,
    validate_brand,
    validate_color,
    validate_cpu_cores_threads,
    validate_display_size,
    validate_ethernet,
    validate_gpu_vram,
    validate_microphone,
    validate_mpn,
    validate_os_name,
    validate_panel_type,
    validate_power_adapter,
    validate_price_egp,
    validate_ram_capacity,
    validate_ram_slots,
    validate_ram_speed,
    validate_ram_type,
    validate_refresh_rate,
    validate_resolution,
    validate_storage_capacity,
    validate_storage_form_factor,
    validate_storage_interface,
    validate_webcam,
    validate_weight,
    validate_wifi,
)
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
        try:
            if store == "compumarts":
                structured, envelopes = self.compumarts_extractor.extract(specs, title, metadata)
            else:
                # Fallback to generic key matcher for any other store
                raw_struct, compound_rows = self.matcher.match_specs(specs)
                structured = empty_structured()
                # Shallow copy known sections from raw_struct to empty_structured
                for k, v in raw_struct.items():
                    if k in structured and isinstance(v, dict):
                        structured[k].update(v)
                    elif k in structured:
                        structured[k] = v
                envelopes = []
        except Exception as exc:
            logger.exception("Error in Tier 1 extractor: %s", exc)
            structured = empty_structured()
            structured["extraction_meta"]["status"] = "failed"
            structured["extraction_meta"]["warnings"].append(f"tier1_exception: {str(exc)}")
            envelopes = []

        layer1_time_ms = (time.perf_counter() - t0) * 1000

        # Ensure extraction_meta structure exists
        if "extraction_meta" not in structured:
            structured["extraction_meta"] = empty_structured()["extraction_meta"]

        # Forward / Ingest merged metadata if fields still missing
        if metadata:
            rejections = structured["extraction_meta"]["rejected"]
            sources = structured["extraction_meta"]["field_sources"]

            cand_mpn = metadata.get("mpn") or metadata.get("retailer_sku") or metadata.get("sku")
            if cand_mpn and not structured["identity"].get("manufacturer_part_number"):
                v_mpn, err = validate_mpn(cand_mpn, title=title, brand=structured["identity"].get("brand") or metadata.get("brand"))
                if v_mpn:
                    structured["identity"]["manufacturer_part_number"] = v_mpn
                    sources["identity.manufacturer_part_number"] = "metadata"
                elif err:
                    rejections.append({"field": "identity.manufacturer_part_number", "value": cand_mpn, "rule": err})

            if metadata.get("brand") and not structured["identity"].get("brand"):
                v_brand, err = validate_brand(metadata["brand"])
                if v_brand:
                    structured["identity"]["brand"] = v_brand
                    sources["identity.brand"] = "metadata"
                elif err:
                    rejections.append({"field": "identity.brand", "value": metadata["brand"], "rule": err})

            if structured.get("price_egp") is None:
                cand_p = metadata.get("price") if metadata.get("price") is not None else metadata.get("price_egp")
                if cand_p is not None:
                    v_price, err_p = validate_price_egp(cand_p)
                    structured["price_egp"] = v_price
                    if err_p:
                        rejections.append({"field": "price_egp", "value": cand_p, "rule": err_p})

            if metadata.get("in_stock") is not None and "in_stock" in structured:
                structured["in_stock"] = bool(metadata["in_stock"])

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
            try:
                ents = self.gliner.extract_entities(prompt_text, env.target_labels, threshold=0.35)
            except Exception as exc:
                logger.warning("GLiNER extraction failed for envelope %s: %s", env.target_area, exc)
                structured["extraction_meta"]["warnings"].append(f"gliner_error_{env.target_area}: {str(exc)}")
                ents = []
            gliner_time_ms += (time.perf_counter() - t_gliner) * 1000
            gliner_calls += 1

            for ent in ents:
                lbl = ent.get("label", "").lower().strip()
                txt = ent.get("text", "").strip()
                if not txt:
                    continue
                try:
                    self._apply_entity(structured, lbl, txt)
                except Exception as exc:
                    logger.warning("Error applying GLiNER entity '%s' (%s): %s", lbl, txt, exc)
                    structured["extraction_meta"]["warnings"].append(f"apply_entity_error_{lbl}: {str(exc)}")

        # Tier 2.5: Identity resolution (Model/Family from Title) if still missing
        needs_model = not structured["identity"].get("laptop_model")
        needs_family = not structured["identity"].get("laptop_family")
        if title and (needs_model or needs_family or not structured["identity"].get("manufacturer_part_number")):
            # Extract part number or model code via regex first
            m_code = re.search(r"\b([A-Z0-9]{3,8}-[A-Z0-9]{2,6}(?:-[A-Z0-9]{2,6})?|[0-9]{2}[A-Z0-9]{6,10})\b", title)
            if m_code:
                code_str = m_code.group(1)
                v_mpn, _ = validate_mpn(code_str, title=title, brand=structured["identity"].get("brand"))
                if v_mpn and not structured["identity"].get("manufacturer_part_number"):
                    structured["identity"]["manufacturer_part_number"] = v_mpn
                    structured["extraction_meta"]["field_sources"]["identity.manufacturer_part_number"] = "title"
                if not structured["identity"].get("laptop_model"):
                    structured["identity"]["laptop_model"] = code_str
                    structured["extraction_meta"]["field_sources"]["identity.laptop_model"] = "title"

            if not structured["identity"].get("laptop_family"):
                try:
                    t_gliner = time.perf_counter()
                    identity_labels = ["laptop family", "laptop model"]
                    ents = self.gliner.extract_entities(title, identity_labels, threshold=0.35)
                    gliner_time_ms += (time.perf_counter() - t_gliner) * 1000
                    gliner_calls += 1

                    for ent in ents:
                        lbl = ent.get("label", "").lower().strip()
                        txt = ent.get("text", "").strip()
                        if any(hw in txt.lower() for hw in ["intel", "amd", "ryzen", "rtx", "geforce", "core", "ddr", "ssd", "ips", "hz"]):
                            continue
                        if lbl == "laptop family" and not structured["identity"].get("laptop_family"):
                            structured["identity"]["laptop_family"] = txt
                            structured["extraction_meta"]["field_sources"]["identity.laptop_family"] = "tier2"
                        elif lbl == "laptop model" and not structured["identity"].get("laptop_model"):
                            structured["identity"]["laptop_model"] = txt
                            structured["extraction_meta"]["field_sources"]["identity.laptop_model"] = "tier2"
                except Exception as exc:
                    logger.warning("Tier 2.5 GLiNER extraction failed: %s", exc)
                    structured["extraction_meta"]["warnings"].append(f"tier2.5_gliner_error: {str(exc)}")

        # Cross-field consistency validation
        validate_consistency(structured, raw_specs=specs)

        # Determine extraction_meta status
        if structured["extraction_meta"].get("status") != "failed":
            has_core = (
                structured["identity"].get("brand") is not None
                and (structured["cpu"].get("model") is not None or structured["cpu"].get("line") is not None)
                and structured["memory"].get("capacity_gb") is not None
                and structured["storage"].get("capacity_gb") is not None
            )
            has_rejections = bool(structured["extraction_meta"].get("rejected"))
            has_conflicts = any(c.get("needs_review") for c in structured["extraction_meta"].get("conflicts", []))
            if has_core and not has_rejections and not has_conflicts:
                structured["extraction_meta"]["status"] = "ok"
            else:
                structured["extraction_meta"]["status"] = "partial"

        structured["extraction_meta"]["tokens"] = {
            "max": self.gliner.max_tokens_seen,
            "truncations_prevented": self.gliner.truncations_prevented,
        }

        total_time_ms = (time.perf_counter() - start_total) * 1000

        metadata_res = {
            "total_time_ms": round(total_time_ms, 2),
            "layer1_time_ms": round(layer1_time_ms, 3),
            "gliner_time_ms": round(gliner_time_ms, 2),
            "gliner_calls_count": gliner_calls,
            "envelopes_count": len(envelopes),
        }

        return structured, metadata_res

    def _apply_entity(self, structured: dict[str, Any], lbl: str, txt: str) -> None:
        """Apply GLiNER extracted entity with strict validation gating."""
        rejections = structured["extraction_meta"]["rejected"]
        sources = structured["extraction_meta"]["field_sources"]

        # 1. Identity
        if lbl == "laptop brand" and not structured["identity"].get("brand"):
            v_val, err = validate_brand(txt)
            if v_val:
                structured["identity"]["brand"] = v_val
                sources["identity.brand"] = "tier2"
            elif err:
                rejections.append({"field": "identity.brand", "value": txt, "rule": err})

        elif lbl == "laptop model" and not structured["identity"].get("laptop_model"):
            txt_clean = clean_text(txt)
            if txt_clean and len(txt_clean) <= 60:
                structured["identity"]["laptop_model"] = txt_clean
                sources["identity.laptop_model"] = "tier2"

        elif lbl == "laptop series" and not structured["identity"].get("laptop_family"):
            txt_clean = clean_text(txt)
            if txt_clean and len(txt_clean) <= 40:
                structured["identity"]["laptop_family"] = txt_clean
                sources["identity.laptop_family"] = "tier2"

        elif lbl == "part number" and not structured["identity"].get("manufacturer_part_number"):
            v_val, err = validate_mpn(txt)
            if v_val:
                structured["identity"]["manufacturer_part_number"] = v_val
                sources["identity.manufacturer_part_number"] = "tier2"
            elif err:
                rejections.append({"field": "identity.manufacturer_part_number", "value": txt, "rule": err})

        # 2. CPU
        elif lbl == "processor model" and not structured["cpu"].get("model"):
            if not re.search(r"\b(NPU|AI Chip)\b", txt, re.I):
                txt_clean = clean_text(txt)
                if txt_clean and len(txt_clean) <= 30:
                    structured["cpu"]["model"] = txt_clean
                    sources["cpu.model"] = "tier2"

        elif lbl == "processor line" and not structured["cpu"].get("line"):
            v_line = normalize_cpu_line(txt)
            if v_line:
                structured["cpu"]["line"] = v_line
                sources["cpu.line"] = "tier2"

        elif lbl == "processor manufacturer" and not structured["cpu"].get("manufacturer"):
            txt_low = txt.lower()
            if "intel" in txt_low:
                structured["cpu"]["manufacturer"] = "Intel"
                sources["cpu.manufacturer"] = "tier2"
            elif "amd" in txt_low:
                structured["cpu"]["manufacturer"] = "AMD"
                sources["cpu.manufacturer"] = "tier2"
            elif "qualcomm" in txt_low or "snapdragon" in txt_low:
                structured["cpu"]["manufacturer"] = "Qualcomm"
                sources["cpu.manufacturer"] = "tier2"
            elif "apple" in txt_low:
                structured["cpu"]["manufacturer"] = "Apple"
                sources["cpu.manufacturer"] = "tier2"

        elif lbl == "cpu core count" and structured["cpu"].get("cores") is None:
            m = re.search(r"\d+", txt)
            if m:
                c_val, _, err = validate_cpu_cores_threads(m.group(0), None)
                if c_val:
                    structured["cpu"]["cores"] = c_val
                    sources["cpu.cores"] = "tier2"
                elif err:
                    rejections.append({"field": "cpu.cores", "value": txt, "rule": err})

        elif lbl == "cpu thread count" and structured["cpu"].get("threads") is None:
            m = re.search(r"\d+", txt)
            if m:
                _, t_val, err = validate_cpu_cores_threads(None, m.group(0))
                if t_val:
                    structured["cpu"]["threads"] = t_val
                    sources["cpu.threads"] = "tier2"
                elif err:
                    rejections.append({"field": "cpu.threads", "value": txt, "rule": err})

        elif lbl == "cpu clock speed" and not structured["cpu"].get("clock_speed"):
            if re.search(r"\b(?:GHz|MHz)\b", txt, re.I) and not re.search(r"\b\d{2,3}\s*Hz\b", txt):
                txt_clean = clean_text(txt)
                structured["cpu"]["clock_speed"] = txt_clean
                sources["cpu.clock_speed"] = "tier2"

        # 3. GPU
        elif lbl == "graphics model" and not structured["gpu"].get("model"):
            txt_clean = clean_text(txt)
            if txt_clean and len(txt_clean) <= 40:
                structured["gpu"]["model"] = txt_clean
                sources["gpu.model"] = "tier2"

        elif lbl == "graphics manufacturer" and not structured["gpu"].get("manufacturer"):
            txt_low = txt.lower()
            if "nvidia" in txt_low:
                structured["gpu"]["manufacturer"] = "NVIDIA"
                sources["gpu.manufacturer"] = "tier2"
            elif "amd" in txt_low:
                structured["gpu"]["manufacturer"] = "AMD"
                sources["gpu.manufacturer"] = "tier2"
            elif "intel" in txt_low:
                structured["gpu"]["manufacturer"] = "Intel"
                sources["gpu.manufacturer"] = "tier2"

        elif lbl in ("graphics vram", "vram") and structured["gpu"].get("vram_gb") is None:
            m_v = re.search(r"(\d+)", txt)
            if m_v:
                v_vram, err = validate_gpu_vram(int(m_v.group(1)))
                if v_vram is not None:
                    structured["gpu"]["vram_gb"] = v_vram
                    sources["gpu.vram_gb"] = "tier2"
                elif err:
                    rejections.append({"field": "gpu.vram_gb", "value": txt, "rule": err})

        elif lbl in ("gpu tdp wattage", "graphics power wattage", "tdp") and structured["gpu"].get("tdp_w") is None:
            m_w = re.search(r"(\d+)", txt)
            if m_w:
                w_val = int(m_w.group(1))
                if 20 <= w_val <= 200:
                    structured["gpu"]["tdp_w"] = w_val
                    sources["gpu.tdp_w"] = "tier2"

        # 4. Memory
        elif lbl == "ram capacity" and structured["memory"].get("capacity_gb") is None:
            m_r = re.search(r"(\d+)", txt)
            if m_r:
                v_cap, err = validate_ram_capacity(int(m_r.group(1)))
                if v_cap is not None:
                    structured["memory"]["capacity_gb"] = v_cap
                    sources["memory.capacity_gb"] = "tier2"
                elif err:
                    rejections.append({"field": "memory.capacity_gb", "value": txt, "rule": err})

        elif lbl in ("max ram capacity", "maximum memory") and structured["memory"].get("max_supported_gb") is None:
            m_mr = re.search(r"(\d+)", txt)
            if m_mr:
                v_mcap, err = validate_ram_capacity(int(m_mr.group(1)), is_max=True)
                inst_ram = structured["memory"].get("capacity_gb") or 0
                if v_mcap is not None and v_mcap >= inst_ram:
                    structured["memory"]["max_supported_gb"] = v_mcap
                    sources["memory.max_supported_gb"] = "tier2"
                elif err:
                    rejections.append({"field": "memory.max_supported_gb", "value": txt, "rule": err})

        elif lbl == "ram type" and not structured["memory"].get("memory_type"):
            v_type, err = validate_ram_type(txt)
            if v_type:
                structured["memory"]["memory_type"] = v_type
                sources["memory.memory_type"] = "tier2"
            elif err:
                rejections.append({"field": "memory.memory_type", "value": txt, "rule": err})

        elif lbl == "ram speed" and structured["memory"].get("speed") is None:
            m_sp = re.search(r"(\d{4})", txt)
            if m_sp:
                v_spd, err = validate_ram_speed(int(m_sp.group(1)))
                if v_spd is not None:
                    structured["memory"]["speed"] = v_spd
                    sources["memory.speed"] = "tier2"
                elif err:
                    rejections.append({"field": "memory.speed", "value": txt, "rule": err})

        elif lbl == "ram slot count" and structured["memory"].get("slot_count") is None:
            m_sc = re.search(r"\b([1-4])\b", txt)
            if m_sc:
                v_slots, err = validate_ram_slots(int(m_sc.group(1)))
                if v_slots is not None:
                    structured["memory"]["slot_count"] = v_slots
                    sources["memory.slot_count"] = "tier2"
                elif err:
                    rejections.append({"field": "memory.slot_count", "value": txt, "rule": err})

        # 5. Storage
        elif lbl == "storage capacity" and structured["storage"].get("capacity_gb") is None:
            m_s = re.search(r"(\d+)", txt)
            if m_s:
                val = int(m_s.group(1))
                val_gb = val * 1024 if val in (1, 2, 4, 8) and ("tb" in txt.lower() or val <= 8) else val
                v_scap, err = validate_storage_capacity(val_gb)
                if v_scap is not None:
                    structured["storage"]["capacity_gb"] = v_scap
                    sources["storage.capacity_gb"] = "tier2"
                elif err:
                    rejections.append({"field": "storage.capacity_gb", "value": txt, "rule": err})

        elif lbl == "storage type" and not structured["storage"].get("storage_type"):
            clean_st = clean_text(txt)
            if any(w in clean_st.upper() for w in ("SSD", "HDD", "EMMC")):
                structured["storage"]["storage_type"] = "SSD" if "SSD" in clean_st.upper() else clean_st
                sources["storage.storage_type"] = "tier2"

        elif lbl == "storage interface" and not structured["storage"].get("interface"):
            v_if, err = validate_storage_interface(txt)
            if v_if:
                structured["storage"]["interface"] = v_if
                sources["storage.interface"] = "tier2"
            elif err:
                rejections.append({"field": "storage.interface", "value": txt, "rule": err})

        elif lbl == "storage form factor" and not structured["storage"].get("form_factor"):
            v_ff, err = validate_storage_form_factor(txt)
            if v_ff:
                structured["storage"]["form_factor"] = v_ff
                sources["storage.form_factor"] = "tier2"
            elif err:
                rejections.append({"field": "storage.form_factor", "value": txt, "rule": err})

        elif lbl == "storage slot count" and structured["storage"].get("slot_count") is None:
            m_sl = re.search(r"\b([1-4])\b", txt)
            if m_sl:
                structured["storage"]["slot_count"] = int(m_sl.group(1))
                sources["storage.slot_count"] = "tier2"

        # 6. Display
        elif lbl == "screen size" and structured["display"].get("size_inches") is None:
            m_sz = re.search(r"(\d{2}(?:\.\d+)?)", txt)
            if m_sz:
                v_sz, err = validate_display_size(float(m_sz.group(1)))
                if v_sz is not None:
                    structured["display"]["size_inches"] = v_sz
                    sources["display.size_inches"] = "tier2"
                elif err:
                    rejections.append({"field": "display.size_inches", "value": txt, "rule": err})

        elif lbl == "screen resolution" and not structured["display"].get("resolution"):
            v_res, w, h, err = validate_resolution(txt)
            if v_res:
                structured["display"]["resolution"] = v_res
                if w and h:
                    structured["display"]["resolution_width"] = w
                    structured["display"]["resolution_height"] = h
                    if not structured["display"].get("aspect_ratio"):
                        structured["display"]["aspect_ratio"] = compute_aspect_ratio(w, h)
                sources["display.resolution"] = "tier2"
            elif err:
                rejections.append({"field": "display.resolution", "value": txt, "rule": err})

        elif lbl in ("refresh rate", "display refresh rate") and structured["display"].get("refresh_rate_hz") is None:
            m_hz = re.search(r"(\d{2,3})\s*Hz", txt, re.I)
            if m_hz:
                v_hz, err = validate_refresh_rate(int(m_hz.group(1)))
                if v_hz is not None:
                    structured["display"]["refresh_rate_hz"] = v_hz
                    sources["display.refresh_rate_hz"] = "tier2"
                elif err:
                    rejections.append({"field": "display.refresh_rate_hz", "value": txt, "rule": err})

        elif lbl in ("panel type", "display panel type") and not structured["display"].get("panel_type"):
            v_pt, err = validate_panel_type(txt)
            if v_pt:
                structured["display"]["panel_type"] = v_pt
                sources["display.panel_type"] = "tier2"
            elif err:
                rejections.append({"field": "display.panel_type", "value": txt, "rule": err})

        elif lbl == "aspect ratio" and not structured["display"].get("aspect_ratio"):
            m_ar = re.search(r"\b(16:9|16:10|3:2|4:3|21:9)\b", txt)
            if m_ar:
                structured["display"]["aspect_ratio"] = m_ar.group(1)
                sources["display.aspect_ratio"] = "tier2"

        # 7. Power & Battery
        elif lbl in ("battery capacity wh", "battery capacity") and structured["power_battery"].get("battery_capacity_wh") is None:
            m_wh = re.search(r"(\d+(?:\.\d+)?)\s*(?:Wh|W/hr)", txt, re.I)
            if m_wh:
                v_wh, err = validate_battery_capacity(float(m_wh.group(1)))
                if v_wh is not None:
                    structured["power_battery"]["battery_capacity_wh"] = v_wh
                    sources["power_battery.battery_capacity_wh"] = "tier2"
                elif err:
                    rejections.append({"field": "power_battery.battery_capacity_wh", "value": txt, "rule": err})

        elif lbl in ("power adapter wattage", "adapter") and structured["power_battery"].get("power_adapter_w") is None:
            m_pw = re.search(r"(\d+)\s*(?:W|Watt)", txt, re.I)
            if m_pw:
                v_pw, err = validate_power_adapter(int(m_pw.group(1)))
                if v_pw is not None:
                    structured["power_battery"]["power_adapter_w"] = v_pw
                    sources["power_battery.power_adapter_w"] = "tier2"
                elif err:
                    rejections.append({"field": "power_battery.power_adapter_w", "value": txt, "rule": err})

        elif lbl in ("battery cells", "cells") and structured["power_battery"].get("battery_cells") is None:
            m_c = re.search(r"\b([2-6])\s*(?:cell|cells)?", txt, re.I)
            if m_c:
                v_c, err = validate_battery_cells(int(m_c.group(1)))
                if v_c is not None:
                    structured["power_battery"]["battery_cells"] = v_c
                    sources["power_battery.battery_cells"] = "tier2"
                elif err:
                    rejections.append({"field": "power_battery.battery_cells", "value": txt, "rule": err})

        # 8. Connectivity
        elif lbl == "wifi standard" and not structured["connectivity"].get("wifi"):
            v_wifi, err = validate_wifi(txt)
            if v_wifi:
                structured["connectivity"]["wifi"] = v_wifi
                sources["connectivity.wifi"] = "tier2"
            elif err:
                rejections.append({"field": "connectivity.wifi", "value": txt, "rule": err})

        elif lbl == "bluetooth version" and not structured["connectivity"].get("bluetooth"):
            v_bt, err = validate_bluetooth(txt)
            if v_bt:
                structured["connectivity"]["bluetooth"] = v_bt
                sources["connectivity.bluetooth"] = "tier2"
            elif err:
                rejections.append({"field": "connectivity.bluetooth", "value": txt, "rule": err})

        elif lbl == "ethernet speed" and not structured["connectivity"].get("ethernet"):
            v_eth, err = validate_ethernet(txt)
            if v_eth:
                structured["connectivity"]["ethernet"] = v_eth
                sources["connectivity.ethernet"] = "tier2"
            elif err:
                rejections.append({"field": "connectivity.ethernet", "value": txt, "rule": err})

        # 9. Physical
        elif lbl == "laptop weight" and structured["physical"].get("weight_kg") is None:
            m_w = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilo)", txt, re.I)
            if m_w:
                v_wt, err = validate_weight(float(m_w.group(1)))
                if v_wt is not None:
                    structured["physical"]["weight_kg"] = v_wt
                    sources["physical.weight_kg"] = "tier2"
                elif err:
                    rejections.append({"field": "physical.weight_kg", "value": txt, "rule": err})

        elif lbl == "laptop color" and not structured["physical"].get("color"):
            v_col, err = validate_color(txt)
            if v_col:
                structured["physical"]["color"] = v_col
                sources["physical.color"] = "tier2"
            elif err:
                rejections.append({"field": "physical.color", "value": txt, "rule": err})

        # 10. Operating System
        elif lbl == "operating system name" and not structured["operating_system"].get("name"):
            v_os, err = validate_os_name(txt)
            if v_os:
                structured["operating_system"]["name"] = v_os
                sources["operating_system.name"] = "tier2"
            elif err:
                rejections.append({"field": "operating_system.name", "value": txt, "rule": err})

        # 11. Build & Security
        elif lbl == "backlit keyboard" and structured["build"].get("has_backlit_keyboard") is None:
            structured["build"]["has_backlit_keyboard"] = "yes" in txt.lower() or "backlit" in txt.lower() or "true" in txt.lower()
            sources["build.has_backlit_keyboard"] = "tier2"

        elif lbl == "fingerprint reader" and structured["build"].get("has_fingerprint") is None:
            structured["build"]["has_fingerprint"] = "yes" in txt.lower() or "fingerprint" in txt.lower() or "true" in txt.lower()
            sources["build.has_fingerprint"] = "tier2"

        # 12. Audio & Webcam
        elif lbl == "webcam resolution" and not structured["webcam"].get("resolution"):
            v_cam, err = validate_webcam(txt)
            if v_cam:
                structured["webcam"]["resolution"] = v_cam
                sources["webcam.resolution"] = "tier2"
            elif err:
                rejections.append({"field": "webcam.resolution", "value": txt, "rule": err})

        elif lbl == "microphone" and not structured["audio"].get("microphone"):
            v_mic, err = validate_microphone(txt)
            if v_mic:
                structured["audio"]["microphone"] = v_mic
                sources["audio.microphone"] = "tier2"
            elif err:
                rejections.append({"field": "audio.microphone", "value": txt, "rule": err})

        elif lbl == "speaker count" and structured["audio"].get("speaker_count") is None:
            m_spk = re.search(r"\b([1-8])\b", txt)
            if m_spk:
                val = int(m_spk.group(1))
                if 1 <= val <= 8:
                    structured["audio"]["speaker_count"] = val
                    sources["audio.speaker_count"] = "tier2"
