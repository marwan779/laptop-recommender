"""Master Pipeline Orchestrator.

Wires all 7 layers together into a coherent, robust extraction pipeline:
1. Scraping using Scrapling base engine & raw archival.
2. Text sanitizer layer.
3. CPU Extraction using ground-truth CPU_SPECS.
4. Deterministic extractor layer (with Section-Level envelope capture).
5. Physical validation layer (Gate 1 - deterministic evaluation).
6. AI Fallback layer (via unified IAIFallbackExtractor contract).
7. Physical validation layer (Gate 2 - AI fallback evaluation).
"""

from __future__ import annotations

import json
from common.logger import get_logger
import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.engine.scrapling_engine import ScraplingEngine
from app.pipeline.ai_fallback.base import IAIFallbackExtractor
from app.pipeline.cpu_anchor import CPUAnchorExtractor
from app.pipeline.deterministic import DeterministicExtractor
from app.pipeline.envelope_normalizer import EnvelopePromptNormalizer
from app.pipeline.physical_validator import PhysicalValidator
from app.pipeline.provenance import ProvenanceTracker
from app.pipeline.raw_storage import RawScrapeStorage
from app.pipeline.sanitizer import TextSanitizer
from app.pipeline.schema import (
    ComponentEnvelope,
    ComponentEnvelopeResult,
    EnvelopeResult,
    ExtractionEnvelope,
    RawScrapedProduct,
)

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    """End-to-end extraction result with full auditability."""

    specs: dict[str, Any]
    cpu_key: str | None
    envelopes_generated: list[ExtractionEnvelope] = field(default_factory=list)
    component_envelopes_generated: list[ComponentEnvelope] = field(default_factory=list)
    component_results: list[ComponentEnvelopeResult] = field(default_factory=list)
    ai_results: list[EnvelopeResult] = field(default_factory=list)
    validation_rejections: list[dict[str, Any]] = field(default_factory=list)
    raw_product: RawScrapedProduct | None = None
    provenance_record: dict[str, Any] | None = None


class LaptopExtractionPipeline:
    """Full 7-layer scraping and hardware extraction pipeline."""

    def __init__(
        self,
        ai_fallback: IAIFallbackExtractor | None = None,
        scraper_engine: ScraplingEngine | None = None,
        raw_storage: RawScrapeStorage | None = None,
        log_envelopes: bool = False,
    ) -> None:
        self.ai_fallback = ai_fallback
        self.scraper_engine = scraper_engine or ScraplingEngine()
        self.raw_storage = raw_storage or RawScrapeStorage()
        self.sanitizer = TextSanitizer()
        self.cpu_anchor = CPUAnchorExtractor()
        self.deterministic = DeterministicExtractor()
        self.validator = PhysicalValidator()
        self.prompt_normalizer = EnvelopePromptNormalizer()
        self.log_envelopes = log_envelopes

    def process_raw_product(self, product: RawScrapedProduct) -> PipelineResult:
        """Run extraction layers 2 through 7 on a raw scraped product."""
        t0 = time.time()
        # --- Layer 2: Text Sanitizer ---
        sanitized_title = self.sanitizer.clean_text(product.title)
        sanitized_table = self.sanitizer.sanitize_table(product.raw_tables.get("specs", {}))
        sanitized_sections = self.sanitizer.sanitize_sections(product.raw_sections)

        # Flatten all tables into table dict if nested
        for tbl_name, tbl_rows in product.raw_tables.items():
            if tbl_name != "specs":
                cleaned_rows = self.sanitizer.sanitize_table(tbl_rows)
                for k, v in cleaned_rows.items():
                    if k not in sanitized_table:
                        sanitized_table[k] = v

        # Inject product-level SKU / MPN if present on product artifact
        if getattr(product, "retailer_sku", None) and "SKU" not in sanitized_table:
            sanitized_table["SKU"] = product.retailer_sku
        if getattr(product, "mpn", None) and "Part Number" not in sanitized_table:
            sanitized_table["Part Number"] = product.mpn

        # --- Layer 3: CPU Anchor Extraction ---
        spec_text_snippets = list(sanitized_table.values()) + list(sanitized_sections.values())
        cpu_specs, cpu_context, cpu_key = self.cpu_anchor.extract(
            title=sanitized_title,
            spec_texts=spec_text_snippets,
        )

        # --- Layer 4: Deterministic Extractor ---
        specs, envelopes = self.deterministic.extract(
            title=sanitized_title,
            sanitized_table=sanitized_table,
            sanitized_sections=sanitized_sections,
            cpu_context=cpu_context,
        )

        # Fallback to product-level SKU/MPN if still missing
        if getattr(product, "retailer_sku", None) and not specs["identity"].get("retailer_sku"):
            specs["identity"]["retailer_sku"] = product.retailer_sku
        if getattr(product, "mpn", None) and not specs["identity"].get("manufacturer_part_number"):
            specs["identity"]["manufacturer_part_number"] = product.mpn

        # Merge CPU ground-truth specs (Option A: absolute ground truth)
        if cpu_specs:
            cpu_raw_spec = specs.get("cpu", {}).get("raw_spec")
            specs["cpu"] = copy.deepcopy(cpu_specs)
            if cpu_raw_spec:
                specs["cpu"]["raw_spec"] = cpu_raw_spec

                # Align with explicit OEM cache specification if declared in raw spec
                m_cache = re.search(r"\b(\d+)\s*MB\s*Cache\b|Cache:\s*(\d+)\s*MB\b", cpu_raw_spec, re.IGNORECASE)
                if m_cache:
                    specs["cpu"]["cache_mb"] = int(m_cache.group(1) or m_cache.group(2))

                # Align with explicit OEM boost clock specification if declared in raw spec
                m_boost = re.search(
                    r"\b(?:up\s+to|max\s+boost\s+clock|turbo\s+boost\s+up\s+to|boost\s+clock)\s*:?\s*(\d+(?:\.\d+)?)\s*GHz\b",
                    cpu_raw_spec,
                    re.IGNORECASE,
                )
                if m_boost:
                    b_ghz = float(m_boost.group(1))
                    specs["cpu"]["clock_boost_ghz"] = b_ghz
                    if (
                        isinstance(specs["cpu"].get("performance_cores"), dict)
                        and specs["cpu"]["performance_cores"] is not None
                    ):
                        specs["cpu"]["performance_cores"]["boost_clock_ghz"] = b_ghz

        deterministic_specs = copy.deepcopy(specs)

        # --- Layer 5: Physical Validation Gate 1 (Deterministic specs) ---
        validation_rejections: list[dict[str, Any]] = []
        for cat, cat_dict in list(specs.items()):
            if cat == "cpu":
                continue  # CPU is already verified ground truth
            for f_name, f_val in list(cat_dict.items()):
                field_path = f"{cat}.{f_name}"
                is_valid, cleaned_val, reason = self.validator.validate_field(
                    field_path=field_path,
                    value=f_val,
                    cpu_context=cpu_context,
                )
                if not is_valid:
                    validation_rejections.append(
                        {
                            "gate": 1,
                            "field_path": field_path,
                            "rejected_value": f_val,
                            "reason": reason,
                        }
                    )
                    # Clear invalid deterministic value
                    specs[cat][f_name] = None
                    # Package into envelope for AI resolution
                    if cat == "identity":
                        raw_context = self.deterministic.clean_laptop_name(sanitized_title)
                        allowed_vals = (
                            self.deterministic.CANONICAL_FAMILIES.get(specs.get("identity", {}).get("brand", ""), [])
                            if field_path == "identity.laptop_family"
                            else None
                        )
                    else:
                        raw_context = sanitized_sections.get(cat.capitalize(), "") or str(sanitized_table)
                        allowed_vals = None

                    envelopes.append(
                        ExtractionEnvelope(
                            field_path=field_path,
                            field_description=f"Hardware spec for {field_path}",
                            raw_context=raw_context,
                            failure_reason="validation_failed",
                            expected_type="str" if isinstance(f_val, str) else "float",
                            cpu_context=cpu_context,
                            allowed_values=allowed_vals,
                        )
                    )
                else:
                    specs[cat][f_name] = cleaned_val

        # --- Component Envelope Packaging ---
        COMPONENT_DEFINITIONS = {
            "identity": ["laptop_family", "laptop_model", "manufacturer_part_number", "color", "warranty_years"],
            "gpu": ["model", "vram_gb", "tdp_w", "integrated"],
            "memory": ["capacity_gb", "memory_type", "speed", "slot_count", "max_supported_gb", "is_soldered"],
            "storage": ["capacity_gb", "storage_type", "interface", "form_factor", "slot_count"],
            "display": [
                "size_inches",
                "resolution",
                "refresh_rate_hz",
                "panel_type",
                "aspect_ratio",
                "touchscreen",
                "brightness_nits",
                "color_gamut",
                "response_time_ms",
            ],
            "power_battery": ["battery_capacity_wh", "power_adapter_w", "battery_cells", "fast_charging"],
            "physical": ["weight_kg", "width_mm", "depth_mm", "height_mm"],
            "connectivity": [
                "wifi",
                "bluetooth",
                "ethernet",
                "has_card_reader",
                "card_reader_type",
                "thunderbolt_version",
            ],
            "audio_webcam": [
                "speaker_count",
                "webcam_resolution",
                "has_ir_camera",
                "has_privacy_shutter",
                "microphone",
            ],
            "build_security": [
                "has_backlit_keyboard",
                "keyboard_backlight_type",
                "has_fingerprint",
                "has_numpad",
                "chassis_material",
            ],
            "operating_system": ["name"],
        }

        COMPONENT_ENUMS = {
            "display": {
                "panel_type": ["IPS", "OLED", "AMOLED", "TN", "VA", "Mini-LED"],
            },
            "memory": {
                "memory_type": ["DDR4", "DDR5", "LPDDR4", "LPDDR4X", "LPDDR5", "LPDDR5X"],
            },
            "storage": {
                "storage_type": ["SSD", "HDD", "eMMC"],
                "interface": ["PCIe NVMe", "SATA"],
                "form_factor": ["M.2 2280", "M.2 2242", "2.5-inch"],
            },
            "connectivity": {
                "card_reader_type": [
                    "MicroSD",
                    "SD Card Reader",
                    "SD Express",
                    "4-in-1 Card Reader",
                    "3-in-1 Card Reader",
                ],
                "thunderbolt_version": ["Thunderbolt 3", "Thunderbolt 4", "Thunderbolt 5"],
            },
            "build_security": {
                "keyboard_backlight_type": [
                    "Single Color (White)",
                    "Single Color (Blue)",
                    "RGB 4-Zone",
                    "Per-Key RGB",
                    "RGB",
                ],
            },
            "operating_system": {
                "name": ["Windows 11 Home", "Windows 11 Pro", "FreeDOS", "macOS", "Ubuntu", "ChromeOS"],
            },
        }

        component_envelopes: list[ComponentEnvelope] = []
        for comp_name, comp_fields in COMPONENT_DEFINITIONS.items():
            comp_dict = specs.get(comp_name, {})
            unresolved = [f for f in comp_fields if comp_dict.get(f) is None]
            if not unresolved:
                continue

            # Strict TDP Protocol Rule:
            # - Integrated GPU: vram_gb and tdp_w are not applicable (shared system memory/power).
            # - Discrete GPU: if model and vram_gb are identified, tdp_w is OEM-configurable.
            #   If omitted by the retailer, we keep tdp_w=None and NEVER dispatch an AI envelope.
            if comp_name == "gpu":
                if comp_dict.get("integrated"):
                    unresolved = [f for f in unresolved if f not in ("vram_gb", "tdp_w")]
                elif comp_dict.get("model") is not None:
                    unresolved = [f for f in unresolved if f != "tdp_w"]
                if not unresolved:
                    continue

            raw_spec = comp_dict.get("raw_spec") or ""
            if not raw_spec or raw_spec.strip() in ("", "None", "Spec: None"):
                if comp_name == "identity":
                    raw_spec = sanitized_title
                elif comp_name == "power_battery":
                    raw_spec = (
                        sanitized_sections.get("Battery & Power", "") or sanitized_sections.get("Power", "") or ""
                    )
                elif comp_name == "display":
                    raw_spec = sanitized_sections.get("Display", "") or ""
                elif comp_name == "gpu":
                    raw_spec = sanitized_sections.get("Graphics", "") or sanitized_sections.get("GPU", "") or ""
                elif comp_name == "connectivity":
                    raw_spec = (
                        sanitized_sections.get("Connectivity", "")
                        or sanitized_sections.get("Ports", "")
                        or sanitized_sections.get("I/O Ports", "")
                        or ""
                    )
                elif comp_name == "audio_webcam":
                    raw_spec = (
                        sanitized_sections.get("Audio & Camera", "")
                        or sanitized_sections.get("Audio", "")
                        or sanitized_sections.get("Camera", "")
                        or ""
                    )
                elif comp_name == "build_security":
                    raw_spec = (
                        sanitized_sections.get("Design & Keyboard", "")
                        or sanitized_sections.get("Keyboard", "")
                        or sanitized_sections.get("Security", "")
                        or ""
                    )
                elif comp_name == "operating_system":
                    raw_spec = (
                        sanitized_sections.get("Operating System", "")
                        or sanitized_sections.get("OS", "")
                        or sanitized_title
                        or ""
                    )

            # Rule: If raw_spec is empty, skip envelope
            if not raw_spec or not raw_spec.strip():
                continue

            sub_schema = {f: comp_dict.get(f) for f in comp_fields}
            locked_fields = {f for f in comp_fields if comp_dict.get(f) is not None}

            component_envelopes.append(
                ComponentEnvelope(
                    component_name=comp_name,
                    raw_spec=raw_spec,
                    sub_schema=sub_schema,
                    locked_fields=locked_fields,
                    enum_constraints=COMPONENT_ENUMS.get(comp_name, {}),
                    cpu_context=cpu_context,
                )
            )

        # Log dispatched component envelopes
        if self.log_envelopes:
            if component_envelopes:
                logger.info("[COMPONENT ENVELOPE] Dispatched %d envelope(s) to AI fallback:", len(component_envelopes))
                for c_env in component_envelopes:
                    unresolved_targets = [k for k, v in c_env.sub_schema.items() if v is None]
                    ctx_snippet = (c_env.raw_spec or "").replace("\n", " ").strip()
                    if len(ctx_snippet) > 80:
                        ctx_snippet = ctx_snippet[:77] + "..."
                    logger.info(
                        "  -> [ENVELOPE] subsystem=%s | targets=%s | context=%r",
                        c_env.component_name,
                        unresolved_targets,
                        ctx_snippet,
                    )
            else:
                logger.info("[COMPONENT ENVELOPE] 0 component envelopes generated (all covered or source absent).")

        # --- Pre-AI: Envelope Prompt Normalization (Storage & Memory) ---
        if component_envelopes:
            component_envelopes = [self.prompt_normalizer.normalize_envelope(env) for env in component_envelopes]

        # --- Layer 6: AI Fallback Layer ---
        ai_results: list[EnvelopeResult] = []
        component_results: list[ComponentEnvelopeResult] = []
        if component_envelopes and self.ai_fallback:
            try:
                component_results = self.ai_fallback.batch_extract_component_envelopes(component_envelopes)
            except Exception as e:
                logger.error("AI Fallback execution error: %s", e)

            if self.log_envelopes and component_results:
                logger.info(
                    "[AI RESULT] Received %d component prediction(s) from %s:",
                    len(component_results),
                    self.ai_fallback.model_name,
                )
                for cr in component_results:
                    logger.info(
                        "  -> [AI RESULT] subsystem=%s | extracted=%s",
                        cr.component_name,
                        json.dumps(cr.extracted_fields),
                    )
        elif self.log_envelopes and component_envelopes and not self.ai_fallback:
            logger.info("[AI RESULT] Skipped AI fallback (no fallback model configured).")

        # --- Layer 7: Physical Validation Gate 2 (AI Candidate evaluation) ---
        for cr in component_results:
            c_env = next((e for e in component_envelopes if e.component_name == cr.component_name), None)
            locked = c_env.locked_fields if c_env else set()

            for f_name, candidate_val in cr.extracted_fields.items():
                # Guard 1: Never overwrite locked Layer 4 fields!
                if f_name in locked:
                    continue

                # Guard 2: Only accept fields that were explicitly declared unresolved targets in the envelope sub_schema!
                valid_targets = {k for k, v in c_env.sub_schema.items() if v is None} if c_env else set()
                if f_name not in valid_targets:
                    continue

                field_path = f"{cr.component_name}.{f_name}"
                if candidate_val is None:
                    ai_results.append(
                        EnvelopeResult(
                            field_path=field_path,
                            extracted_value=None,
                            confidence=0.0,
                            model_name=cr.model_name,
                        )
                    )
                    continue
                is_valid, cleaned_val, reason = self.validator.validate_field(
                    field_path=field_path,
                    value=candidate_val,
                    cpu_context=cpu_context,
                )

                if is_valid and cleaned_val is not None:
                    specs[cr.component_name][f_name] = cleaned_val
                    ai_results.append(
                        EnvelopeResult(
                            field_path=field_path,
                            extracted_value=cleaned_val,
                            confidence=cr.confidence,
                            model_name=cr.model_name,
                        )
                    )
                    if self.log_envelopes:
                        logger.info(
                            "  -> [GATE 2] %s: candidate=%r -> ACCEPTED (value=%r)",
                            field_path,
                            candidate_val,
                            cleaned_val,
                        )
                else:
                    rej_reason = reason or "invalid_candidate"
                    validation_rejections.append(
                        {
                            "gate": 2,
                            "field_path": field_path,
                            "rejected_value": candidate_val,
                            "model": cr.model_name,
                            "reason": rej_reason,
                        }
                    )
                    ai_results.append(
                        EnvelopeResult(
                            field_path=field_path,
                            extracted_value=None,
                            confidence=0.0,
                            model_name=cr.model_name,
                        )
                    )
                    if self.log_envelopes:
                        logger.warning(
                            "  -> [GATE 2] %s: candidate=%r -> REJECTED (reason=%s)",
                            field_path,
                            candidate_val,
                            rej_reason,
                        )

        # Build complete provenance & lineage audit record
        elapsed = time.time() - t0
        provenance_record = ProvenanceTracker.build_trace(
            raw_product=product,
            sanitized_title=sanitized_title,
            sanitized_table=sanitized_table,
            sanitized_sections=sanitized_sections,
            cpu_key=cpu_key,
            cpu_specs=cpu_specs,
            cpu_context=cpu_context,
            deterministic_specs=deterministic_specs,
            envelopes=envelopes,
            gate1_rejections=[r for r in validation_rejections if r.get("gate") == 1],
            ai_results=ai_results,
            gate2_rejections=[r for r in validation_rejections if r.get("gate") == 2],
            final_specs=specs,
            elapsed_s=elapsed,
        )

        return PipelineResult(
            specs=specs,
            cpu_key=cpu_key,
            envelopes_generated=envelopes,
            component_envelopes_generated=component_envelopes,
            component_results=component_results,
            ai_results=ai_results,
            validation_rejections=validation_rejections,
            raw_product=product,
            provenance_record=provenance_record,
        )

    def parse_html(
        self,
        html_text: str,
        url: str = "",
        store_name: str = "compumarts",
    ) -> RawScrapedProduct:
        """Parse raw HTML into a structured RawScrapedProduct using PatternEngine."""
        from bs4 import BeautifulSoup
        from app.core.patterns.engine import PatternEngine

        soup = BeautifulSoup(html_text, "html.parser")
        title_elem = soup.select_one(
            "h1.product-title, h1.product__title, .product-meta__title, h1, .product-details h1"
        )
        title = title_elem.get_text(strip=True) if title_elem else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=title,
            store_key=store_name.lower(),
        )

        # Extract dedicated SKU / MPN header tags if present
        sku_val_elem = soup.select_one(".product-sku__value")
        if sku_val_elem:
            sku_text = sku_val_elem.get_text(strip=True)
        else:
            sku_elem = soup.select_one("[data-sku], .product-sku, .sku")
            sku_text = sku_elem.get_text(strip=True) if sku_elem else None
            if sku_text:
                sku_text = re.sub(r"^[\s|–—\xa0]+", "", sku_text).strip()
                if sku_text.upper().startswith("SKU:"):
                    sku_text = sku_text[4:].strip()
                sku_text = sku_text.strip(" |–—\t\r\n")

        final_sku = sku_text or getattr(spec_res, "mpn", None)
        final_mpn = getattr(spec_res, "mpn", None) or sku_text

        specs_dict = dict(spec_res.specs)
        if final_sku and "SKU" not in specs_dict:
            specs_dict["SKU"] = final_sku
        if final_mpn and "Part Number" not in specs_dict:
            specs_dict["Part Number"] = final_mpn

        return RawScrapedProduct(
            url=url,
            store=store_name,
            title=title,
            raw_html=html_text,
            raw_tables={"specs": specs_dict},
            raw_sections={"Description": spec_res.raw_description or ""},
            price=spec_res.price_val,
            retailer_sku=final_sku,
            mpn=final_mpn,
        )

    def extract_from_url(
        self,
        url: str,
        store_name: str = "compumarts",
        stealth: bool = False,
    ) -> PipelineResult:
        """Fetch URL with ScraplingEngine, archive raw HTML, and run full extraction."""
        # 1. Scrape via Scrapling
        scraped_doc = self.scraper_engine.fetch(url, stealth=stealth)

        # 2. Package raw product using PatternEngine
        raw_product = self.parse_html(
            html_text=scraped_doc.html,
            url=url,
            store_name=store_name,
        )

        # 3. Archive raw HTML for audits
        self.raw_storage.save(raw_product)

        # 4. Run pipeline
        return self.process_raw_product(raw_product)
