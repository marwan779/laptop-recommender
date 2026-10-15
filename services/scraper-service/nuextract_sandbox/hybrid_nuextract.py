import json
import re
import time
from typing import Any

from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.validators import (
    clean_text,
    validate_battery_capacity,
    validate_battery_cells,
    validate_bluetooth,
    validate_brand,
    validate_color,
    validate_consistency,
    validate_cpu_cache,
    validate_cpu_cores_threads,
    validate_display_size,
    validate_ethernet,
    validate_gpu_vram,
    validate_microphone,
    validate_mpn,
    normalize_dimensions,
    validate_os_name,
    validate_panel_type,
    validate_power_adapter,
    validate_ram_capacity,
    validate_ram_slots,
    validate_ram_speed,
    validate_ram_type,
    validate_refresh_rate,
    validate_resolution,
    validate_storage_capacity,
    validate_storage_form_factor,
    validate_webcam,
    validate_weight,
)
from nuextract_sandbox.combiner import SpecCombiner
from nuextract_sandbox.extractor import NuExtractor


class HybridNuExtractPipeline:
    """Production-grade hybrid pipeline: Tier 1 Deterministic + NuExtract Fallback + Strict Validators."""

    def __init__(self, model_name: str = "numind/NuExtract-v1.5"):
        print("[Init] Initializing Tier 1 CompumartsExtractor...")
        self.tier1 = CompumartsExtractor()
        self.combiner = SpecCombiner()
        self.nuextract_model_name = model_name
        self._nuextractor: NuExtractor | None = None

    @property
    def nuextractor(self) -> NuExtractor:
        if self._nuextractor is None:
            print(f"[Init] Lazy loading {self.nuextract_model_name}...")
            self._nuextractor = NuExtractor(model_name=self.nuextract_model_name)
        return self._nuextractor

    def run(
        self,
        raw_specs: dict[str, Any],
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Execute Tier 1 deterministic extraction, then targeted NuExtract fallback for missing fields."""
        t0 = time.time()

        # ---------------------------------------------------------------------
        # Stage 1: Tier 1 Deterministic Extraction (0ms, 100% precision)
        # ---------------------------------------------------------------------
        t0_t1 = time.time()
        structured, _ = self.tier1.extract(raw_specs, title, metadata=metadata)
        t1_latency = time.time() - t0_t1
        print(f"[Tier 1] Deterministic extraction complete in {t1_latency * 1000:.2f}ms")

        # ---------------------------------------------------------------------
        # Stage 2: Identify Missing / Unresolved Fields per Domain
        # ---------------------------------------------------------------------
        missing_by_area: dict[str, list[str]] = {}

        # Physical dimensions
        phys = structured.get("physical", {})
        missing_phys = []
        if phys.get("height_mm") is None:
            missing_phys.append("height_mm")
        if phys.get("width_mm") is None:
            missing_phys.append("width_mm")
        if phys.get("depth_mm") is None:
            missing_phys.append("depth_mm")
        if phys.get("weight_kg") is None:
            missing_phys.append("weight_kg")
        if not phys.get("color"):
            missing_phys.append("color")
        if missing_phys:
            missing_by_area["physical"] = missing_phys

        # Audio & Webcam
        audio = structured.get("audio", {})
        webcam = structured.get("webcam", {})
        missing_audio = []
        if audio.get("speaker_count") is None:
            missing_audio.append("speaker_count")
        if not audio.get("microphone"):
            missing_audio.append("microphone")
        if not webcam.get("resolution"):
            missing_audio.append("webcam_resolution")
        if missing_audio:
            missing_by_area["audio_webcam"] = missing_audio

        # Build & Security
        build = structured.get("build", {})
        missing_build = []
        if build.get("has_backlit_keyboard") is None:
            missing_build.append("has_backlit_keyboard")
        if build.get("has_fingerprint") is None:
            missing_build.append("has_fingerprint")
        if missing_build:
            missing_by_area["build_security"] = missing_build

        # Power & Battery
        pwr = structured.get("power_battery", {})
        missing_pwr = []
        if pwr.get("battery_capacity_wh") is None:
            missing_pwr.append("battery_capacity_wh")
        if pwr.get("power_adapter_w") is None:
            missing_pwr.append("power_adapter_w")
        if pwr.get("battery_cells") is None:
            missing_pwr.append("battery_cells")
        if missing_pwr:
            missing_by_area["power_battery"] = missing_pwr

        # Storage Slots
        st = structured.get("storage", {})
        if st.get("slot_count") is None:
            missing_by_area["storage"] = ["slot_count"]

        # Memory Slots
        mem = structured.get("memory", {})
        if mem.get("slot_count") is None or mem.get("max_supported_gb") is None:
            missing_mem = []
            if mem.get("slot_count") is None:
                missing_mem.append("slot_count")
            if mem.get("max_supported_gb") is None:
                missing_mem.append("max_supported_gb")
            if missing_mem:
                missing_by_area["memory"] = missing_mem

        # CPU Cache
        cpu_obj = structured.get("cpu", {})
        if cpu_obj.get("cache_mb") is None:
            missing_by_area["cpu"] = ["cache_mb"]

        print(f"[Tier 2 Evaluation] Missing areas for NuExtract fallback: {list(missing_by_area.keys())}")

        # ---------------------------------------------------------------------
        # Stage 3: Targeted NuExtract Fallback & Strict Validation Gate
        # ---------------------------------------------------------------------
        area_blocks = self.combiner.combine_area_blocks({
            "title": title,
            "raw_specs": raw_specs,
            "metadata": metadata or {},
        })

        nuextract_calls = 0
        t0_nuextract = time.time()
        meta = structured.setdefault("extraction_meta", {})
        field_sources = meta.setdefault("field_sources", {})
        rejections = meta.setdefault("rejected", [])

        for area, fields in missing_by_area.items():
            context_text = area_blocks.get(area, "")
            # Only trigger NuExtract if there is actual context to extract from
            if not context_text or context_text == f"Product Title: {title}":
                continue

            # Build minimal target sub-template
            sub_template = {f: None for f in fields}
            print(f"  -> NuExtract micro-fallback on [{area}] for fields {fields}...")
            nuextract_calls += 1

            raw_cand, _ = self.nuextractor.extract(context_text, template={area: sub_template})
            extracted_fields = raw_cand.get(area, {}) if isinstance(raw_cand, dict) and area in raw_cand else raw_cand

            if not isinstance(extracted_fields, dict):
                continue

            # Apply strict validator gate to each NuExtract candidate value
            self._apply_validated_nuextract(
                area=area,
                extracted=extracted_fields,
                structured=structured,
                field_sources=field_sources,
                rejections=rejections,
                title=title,
            )

        nuextract_latency = time.time() - t0_nuextract if nuextract_calls > 0 else 0.0

        # ---------------------------------------------------------------------
        # Stage 4: Cross-Field Consistency Gate
        # ---------------------------------------------------------------------
        validate_consistency(structured, raw_specs=raw_specs)

        total_latency = time.time() - t0
        exec_metrics = {
            "total_latency_seconds": round(total_latency, 2),
            "tier1_latency_seconds": round(t1_latency, 4),
            "nuextract_latency_seconds": round(nuextract_latency, 2),
            "nuextract_calls_count": nuextract_calls,
            "missing_areas_targeted": list(missing_by_area.keys()),
        }

        return structured, exec_metrics

    def _apply_validated_nuextract(
        self,
        area: str,
        extracted: dict[str, Any],
        structured: dict[str, Any],
        field_sources: dict[str, str],
        rejections: list[dict[str, Any]],
        title: str,
    ) -> None:
        """Route NuExtract values through strict validators.py before writing to structured dict."""

        # 1. Physical Dimensions & Weight
        if area == "physical":
            phys = structured.setdefault("physical", {})
            raw_dim_strings = [str(extracted.get(d, "")) for d in ("height_mm", "width_mm", "depth_mm")]
            is_cm_context = any("cm" in s.lower() for s in raw_dim_strings)

            for dim in ("height_mm", "width_mm", "depth_mm"):
                val = extracted.get(dim)
                if val is not None and phys.get(dim) is None:
                    # Clean numerical representation (e.g. "23.5 mm" -> 23.5)
                    m_num = re.search(r"(\d+(?:\.\d+)?)", str(val))
                    if m_num:
                        f_val = float(m_num.group(1))
                        val_str = str(val).lower()
                        # Detect cm and convert to mm
                        if is_cm_context or "cm" in val_str:
                            f_val = round(f_val * 10.0, 2)
                        elif dim in ("width_mm", "depth_mm") and f_val < 60.0:
                            f_val = round(f_val * 10.0, 2)
                        elif dim == "height_mm" and f_val < 5.0:
                            f_val = round(f_val * 10.0, 2)
                        elif "m" in val_str and "mm" not in val_str and f_val < 1.0:
                            f_val = round(f_val * 1000.0, 2)

                        # Sanity check: laptop dimensions must be between 5mm and 500mm
                        if 5.0 <= f_val <= 500.0:
                            phys[dim] = f_val
                            field_sources[f"physical.{dim}"] = "nuextract"
                        else:
                            rejections.append({"field": f"physical.{dim}", "value": val, "rule": "dimension_out_of_bounds"})

            # If all 3 dimensions exist, normalize axes (width >= depth >= height)
            if phys.get("width_mm") and phys.get("depth_mm") and phys.get("height_mm"):
                nw, nd, nh = normalize_dimensions(phys["width_mm"], phys["depth_mm"], phys["height_mm"])
                if nw and nd and nh:
                    phys["width_mm"], phys["depth_mm"], phys["height_mm"] = nw, nd, nh

            if extracted.get("weight_kg") is not None and phys.get("weight_kg") is None:
                v_wt, err = validate_weight(extracted["weight_kg"])
                if v_wt:
                    phys["weight_kg"] = v_wt
                    field_sources["physical.weight_kg"] = "nuextract"
                elif err:
                    rejections.append({"field": "physical.weight_kg", "value": extracted["weight_kg"], "rule": err})

            if extracted.get("color") and not phys.get("color"):
                v_col, err = validate_color(extracted["color"], model_name=title)
                if v_col:
                    phys["color"] = v_col
                    field_sources["physical.color"] = "nuextract"

        # 2. Audio & Webcam
        elif area == "audio_webcam":
            audio = structured.setdefault("audio", {})
            webcam = structured.setdefault("webcam", {})

            if extracted.get("speaker_count") is not None and audio.get("speaker_count") is None:
                val_sc = str(extracted["speaker_count"]).strip()
                val_sc_low = val_sc.lower()
                count = None
                if "quad" in val_sc_low:
                    count = 4
                elif "dual" in val_sc_low or "stereo" in val_sc_low:
                    count = 2
                else:
                    m_sp = re.search(r"(?:x\s*([1-8])|([1-8])\s*x|\b([1-8])\s*(?:speakers?|w\b)|\b([1-8])\b)", val_sc, re.I)
                    if m_sp:
                        c_str = m_sp.group(1) or m_sp.group(2) or m_sp.group(3) or m_sp.group(4)
                        count = int(c_str)

                if count is not None and not any(bad in val_sc_low for bad in ["mp", "hz", "ram", "gb"]):
                    audio["speaker_count"] = count
                    field_sources["audio.speaker_count"] = "nuextract"
                else:
                    rejections.append({"field": "audio.speaker_count", "value": extracted["speaker_count"], "rule": "invalid_speaker_count"})

            if extracted.get("microphone") and not audio.get("microphone"):
                v_mic, err = validate_microphone(extracted["microphone"])
                if v_mic:
                    audio["microphone"] = v_mic
                    audio["has_microphone"] = True
                    field_sources["audio.microphone"] = "nuextract"
                elif err:
                    rejections.append({"field": "audio.microphone", "value": extracted["microphone"], "rule": err})

            if extracted.get("webcam_resolution") and not webcam.get("resolution"):
                v_cam, err = validate_webcam(extracted["webcam_resolution"])
                if v_cam:
                    webcam["resolution"] = v_cam
                    field_sources["webcam.resolution"] = "nuextract"
                elif err:
                    rejections.append({"field": "webcam.resolution", "value": extracted["webcam_resolution"], "rule": err})

        # 3. Build & Security
        elif area == "build_security":
            build = structured.setdefault("build", {})
            if extracted.get("has_backlit_keyboard") is not None and build.get("has_backlit_keyboard") is None:
                s_b = str(extracted["has_backlit_keyboard"]).lower()
                if any(w in s_b for w in ["yes", "true", "backlit", "amber", "rgb", "white"]):
                    build["has_backlit_keyboard"] = True
                    field_sources["build.has_backlit_keyboard"] = "nuextract"
                elif any(w in s_b for w in ["no", "false", "non-backlit"]):
                    build["has_backlit_keyboard"] = False
                    field_sources["build.has_backlit_keyboard"] = "nuextract"

            if extracted.get("has_fingerprint") is not None and build.get("has_fingerprint") is None:
                s_fp = str(extracted["has_fingerprint"]).lower()
                if any(w in s_fp for w in ["yes", "true"]) and "no" not in s_fp:
                    build["has_fingerprint"] = True
                    field_sources["build.has_fingerprint"] = "nuextract"
                elif any(w in s_fp for w in ["no", "false"]):
                    build["has_fingerprint"] = False
                    field_sources["build.has_fingerprint"] = "nuextract"

        # 4. Power & Battery
        elif area == "power_battery":
            pwr = structured.setdefault("power_battery", {})
            if extracted.get("battery_capacity_wh") is not None and pwr.get("battery_capacity_wh") is None:
                v_wh, err = validate_battery_capacity(extracted["battery_capacity_wh"])
                if v_wh:
                    pwr["battery_capacity_wh"] = v_wh
                    field_sources["power_battery.battery_capacity_wh"] = "nuextract"
                elif err:
                    rejections.append({"field": "power_battery.battery_capacity_wh", "value": extracted["battery_capacity_wh"], "rule": err})

            if extracted.get("power_adapter_w") is not None and pwr.get("power_adapter_w") is None:
                v_ad, err = validate_power_adapter(extracted["power_adapter_w"])
                if v_ad:
                    pwr["power_adapter_w"] = v_ad
                    field_sources["power_battery.power_adapter_w"] = "nuextract"
                elif err:
                    rejections.append({"field": "power_battery.power_adapter_w", "value": extracted["power_adapter_w"], "rule": err})

            if extracted.get("battery_cells") is not None and pwr.get("battery_cells") is None:
                v_c, err = validate_battery_cells(extracted["battery_cells"])
                if v_c:
                    pwr["battery_cells"] = v_c
                    field_sources["power_battery.battery_cells"] = "nuextract"
                elif err:
                    rejections.append({"field": "power_battery.battery_cells", "value": extracted["battery_cells"], "rule": err})

        # 5. CPU
        elif area == "cpu":
            cpu = structured.setdefault("cpu", {})
            if extracted.get("cache_mb") is not None and cpu.get("cache_mb") is None:
                v_cache, err = validate_cpu_cache(extracted["cache_mb"])
                if v_cache:
                    cpu["cache_mb"] = v_cache
                    field_sources["cpu.cache_mb"] = "nuextract"
                elif err:
                    rejections.append({"field": "cpu.cache_mb", "value": extracted["cache_mb"], "rule": err})

