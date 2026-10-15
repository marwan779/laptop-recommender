"""Pipeline Provenance and Audit Logging Layer.

Tracks complete field-level data lineage and layer-by-layer diagnostic traces:
- What was extracted at each layer.
- Where each field came from (table row name, title regex, CPU ground truth, AI model).
- Why accepted or rejected.
- Exact causality for empty (null) fields (NOT_PRESENT_IN_SOURCE, AI_UNRESOLVED, GATE_1_REJECTED, GATE_2_REJECTED).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from pipeline.schema import (
    ComponentEnvelope,
    ComponentEnvelopeResult,
    EnvelopeResult,
    ExtractionEnvelope,
    RawScrapedProduct,
    empty_laptop_specifications,
)


class ProvenanceTracker:
    """Builds a complete, audit-grade provenance and execution trace for a laptop extraction."""

    # Keywords to test if source context even mentions a given category
    CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "identity": ["model", "series", "brand", "part number", "sku", "color"],
        "cpu": ["cpu", "processor", "intel", "amd", "ryzen", "core"],
        "gpu": ["gpu", "graphic", "vga", "nvidia", "rtx", "gtx", "radeon", "geforce"],
        "memory": ["ram", "memory", "ddr", "lpddr"],
        "storage": ["storage", "ssd", "hdd", "nvme", "hard disk", "drive"],
        "display": ["display", "screen", "panel", "hz", "resolution", "fhd", "qhd", "uhd", "oled", "ips"],
        "power_battery": ["battery", "wh", "watt", "adapter", "power", "charger"],
        "physical": ["weight", "dimension", "dimensions", "width", "height", "depth", "kg"],
        "build_security": ["keyboard", "backlit", "fingerprint", "security", "touchpad"],
        "audio_webcam": ["audio", "speaker", "speakers", "microphone", "mic", "webcam", "camera"],
        "connectivity": ["wifi", "wi-fi", "bluetooth", "ethernet", "lan", "port", "ports", "usb", "hdmi"],
        "operating_system": ["os", "operating system", "windows", "dos", "freedos", "linux", "macos"],
    }

    @classmethod
    def build_trace(
        cls,
        raw_product: RawScrapedProduct,
        sanitized_title: str,
        sanitized_table: Dict[str, str],
        sanitized_sections: Dict[str, str],
        cpu_key: Optional[str],
        cpu_specs: Optional[Dict[str, Any]],
        cpu_context: Optional[Dict[str, Any]],
        deterministic_specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
        gate1_rejections: List[Dict[str, Any]],
        ai_results: List[EnvelopeResult],
        gate2_rejections: List[Dict[str, Any]],
        final_specs: Dict[str, Any],
        elapsed_s: float = 0.0,
    ) -> Dict[str, Any]:
        """Construct the complete provenance and diagnostic record."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Build layer execution timeline
        timeline = cls._build_layer_timeline(
            raw_product=raw_product,
            sanitized_title=sanitized_title,
            sanitized_table=sanitized_table,
            sanitized_sections=sanitized_sections,
            cpu_key=cpu_key,
            cpu_context=cpu_context,
            deterministic_specs=deterministic_specs,
            envelopes=envelopes,
            gate1_rejections=gate1_rejections,
            ai_results=ai_results,
            gate2_rejections=gate2_rejections,
            elapsed_s=elapsed_s,
        )

        # Build field-by-field lineage manifest
        field_provenance = cls._build_field_provenance(
            raw_product=raw_product,
            sanitized_table=sanitized_table,
            sanitized_sections=sanitized_sections,
            cpu_key=cpu_key,
            deterministic_specs=deterministic_specs,
            envelopes=envelopes,
            gate1_rejections=gate1_rejections,
            ai_results=ai_results,
            gate2_rejections=gate2_rejections,
            final_specs=final_specs,
        )

        # Compute summary metrics
        total_fields = len(field_provenance)
        populated_count = sum(1 for f in field_provenance.values() if f["status"] == "populated")
        unpopulated_count = total_fields - populated_count

        return {
            "url": raw_product.url,
            "store": raw_product.store,
            "title": raw_product.title,
            "timestamp": timestamp,
            "elapsed_s": round(elapsed_s, 3),
            "cpu_key": cpu_key,
            "summary": {
                "total_fields": total_fields,
                "populated_fields": populated_count,
                "unpopulated_fields": unpopulated_count,
                "envelopes_count": len(envelopes),
                "ai_resolved_count": len(ai_results),
                "gate1_rejections_count": len(gate1_rejections),
                "gate2_rejections_count": len(gate2_rejections),
            },
            "layer_timeline": timeline,
            "field_provenance": field_provenance,
        }

    @classmethod
    def _build_layer_timeline(
        cls,
        raw_product: RawScrapedProduct,
        sanitized_title: str,
        sanitized_table: Dict[str, str],
        sanitized_sections: Dict[str, str],
        cpu_key: Optional[str],
        cpu_context: Optional[Dict[str, Any]],
        deterministic_specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
        gate1_rejections: List[Dict[str, Any]],
        ai_results: List[EnvelopeResult],
        gate2_rejections: List[Dict[str, Any]],
        elapsed_s: float,
    ) -> List[Dict[str, Any]]:
        """Log key actions taken at each of the 7 layers."""
        return [
            {
                "layer": 1,
                "name": "Scrape & Ingest",
                "status": "success",
                "details": {
                    "url": raw_product.url,
                    "store": raw_product.store,
                    "raw_table_keys_count": len(raw_product.raw_tables.get("specs", {})),
                    "raw_sections_count": len(raw_product.raw_sections),
                    "price_egp": raw_product.price,
                },
            },
            {
                "layer": 2,
                "name": "Text Sanitizer",
                "status": "success",
                "details": {
                    "original_title_len": len(raw_product.title),
                    "sanitized_title_len": len(sanitized_title),
                    "sanitized_table_rows_count": len(sanitized_table),
                    "sanitized_sections_count": len(sanitized_sections),
                },
            },
            {
                "layer": 3,
                "name": "CPU Silicon Anchor",
                "status": "matched" if cpu_key else "unmatched",
                "details": {
                    "cpu_key": cpu_key,
                    "silicon_bounds": {
                        "max_memory_gb": (cpu_context or {}).get("max_memory_gb"),
                        "supported_memory": (cpu_context or {}).get("supported_memory"),
                        "base_power_w": (cpu_context or {}).get("base_power_w"),
                    },
                },
            },
            {
                "layer": 4,
                "name": "Deterministic Extractor",
                "status": "success",
                "details": {
                    "envelopes_generated_count": len(envelopes),
                    "envelope_fields": [e.field_path for e in envelopes],
                },
            },
            {
                "layer": 5,
                "name": "Physical Validation Gate 1",
                "status": "rejections_detected" if gate1_rejections else "all_passed",
                "details": {
                    "rejections_count": len(gate1_rejections),
                    "rejections": gate1_rejections,
                },
            },
            {
                "layer": 6,
                "name": "AI Fallback Layer",
                "status": "executed" if ai_results else "skipped",
                "details": {
                    "envelopes_sent": len(envelopes),
                    "results_returned": len(ai_results),
                    "ai_predictions": [
                        {
                            "field_path": r.field_path,
                            "extracted_value": r.extracted_value,
                            "raw_span": r.raw_span,
                            "confidence": round(r.confidence, 3),
                            "model_name": r.model_name,
                        }
                        for r in ai_results
                    ],
                },
            },
            {
                "layer": 7,
                "name": "Physical Validation Gate 2",
                "status": "rejections_detected" if gate2_rejections else "all_passed",
                "details": {
                    "rejections_count": len(gate2_rejections),
                    "rejections": gate2_rejections,
                },
            },
        ]

    @classmethod
    def _build_field_provenance(
        cls,
        raw_product: RawScrapedProduct,
        sanitized_table: Dict[str, str],
        sanitized_sections: Dict[str, str],
        cpu_key: Optional[str],
        deterministic_specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
        gate1_rejections: List[Dict[str, Any]],
        ai_results: List[EnvelopeResult],
        gate2_rejections: List[Dict[str, Any]],
        final_specs: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Inspect every schema field to determine resolution origin or failure cause."""
        schema_skel = empty_laptop_specifications()
        provenance: Dict[str, Dict[str, Any]] = {}

        gate1_rejection_map = {r["field_path"]: r for r in gate1_rejections}
        gate2_rejection_map = {r["field_path"]: r for r in gate2_rejections}
        ai_result_map = {r.field_path: r for r in ai_results}
        envelope_field_set = {e.field_path for e in envelopes}

        # Combine source text for keyword presence checks
        all_source_text = (
            f"{raw_product.title} "
            + " ".join(sanitized_table.keys())
            + " "
            + " ".join(sanitized_table.values())
            + " "
            + " ".join(sanitized_sections.values())
        ).lower()

        for cat, cat_dict in schema_skel.items():
            for f_name in cat_dict.keys():
                field_path = f"{cat}.{f_name}"
                val = final_specs.get(cat, {}).get(f_name)

                # Determine if populated
                is_populated = False
                if val is not None:
                    if isinstance(val, (list, dict)):
                        is_populated = len(val) > 0
                    elif isinstance(val, bool):
                        is_populated = True  # explicitly determined boolean flag
                    else:
                        is_populated = True

                if is_populated:
                    # Case 1: CPU specs populated via Layer 3 CPU Anchor
                    if cat == "cpu":
                        provenance[field_path] = {
                            "status": "populated",
                            "value": val,
                            "resolved_at": "L3_CPU_Anchor",
                            "source": f"cpu_specs:{cpu_key}",
                            "decision": "silicon_ground_truth_anchor",
                        }
                    # Case 2: Populated via Layer 6 AI Fallback
                    elif (
                        field_path in ai_result_map
                        and ai_result_map[field_path].extracted_value is not None
                        and field_path not in gate2_rejection_map
                    ):
                        ai_res = ai_result_map[field_path]
                        provenance[field_path] = {
                            "status": "populated",
                            "value": val,
                            "resolved_at": "L6_AI_Fallback",
                            "source": f"ai_model:{ai_res.model_name}",
                            "raw_evidence": ai_res.raw_span,
                            "confidence": round(ai_res.confidence, 3),
                            "decision": "validated_at_gate2",
                        }
                    # Case 3: Populated via Layer 4 Deterministic Extractor
                    else:
                        source_detail = cls._find_deterministic_source(
                            cat, f_name, sanitized_table, raw_product.title
                        )
                        provenance[field_path] = {
                            "status": "populated",
                            "value": val,
                            "resolved_at": "L4_Deterministic",
                            "source": source_detail.get("source", "deterministic_parser"),
                            "raw_evidence": source_detail.get("evidence"),
                            "decision": "deterministic_match_passed_gate1",
                        }
                else:
                    # Case 4: Field is UNPOPULATED (null) - determine exact causality
                    causality = cls._determine_unpopulated_cause(
                        field_path=field_path,
                        cat=cat,
                        f_name=f_name,
                        all_source_text=all_source_text,
                        envelope_field_set=envelope_field_set,
                        ai_result_map=ai_result_map,
                        gate1_rejection_map=gate1_rejection_map,
                        gate2_rejection_map=gate2_rejection_map,
                    )
                    provenance[field_path] = causality

        return provenance

    @classmethod
    def _find_deterministic_source(
        cls, cat: str, f_name: str, table: Dict[str, str], title: str
    ) -> Dict[str, str]:
        """Identify which table key or title pattern produced the value."""
        if f_name == "raw_spec":
            return {"source": "aggregated_raw_spec", "evidence": None}

        # Try specific sub-field terms first (e.g. "capacity" for capacity_gb)
        sub_terms = [t for t in f_name.split("_") if len(t) > 3]
        for k, v in table.items():
            kl = k.lower()
            if cat == "memory" and any(bad in kl for bad in ["graphic", "graphics", "gpu", "vga", "video", "dedicated"]):
                continue
            if cat == "identity" and any(bad in kl for bad in ["processor", "cpu", "gpu", "graphic", "video"]):
                continue
            if any(term in kl for term in sub_terms):
                return {"source": f"table_key: '{k}'", "evidence": v}

        # Fallback to general category key
        for k, v in table.items():
            kl = k.lower()
            if cat == "memory" and any(bad in kl for bad in ["graphic", "graphics", "gpu", "vga", "video", "dedicated"]):
                continue
            if cat == "identity" and any(bad in kl for bad in ["processor", "cpu", "gpu", "graphic", "video"]):
                continue
            if cat in kl:
                return {"source": f"table_key: '{k}'", "evidence": v}

        return {"source": "title_or_table_pattern", "evidence": None}

    @classmethod
    def _determine_unpopulated_cause(
        cls,
        field_path: str,
        cat: str,
        f_name: str,
        all_source_text: str,
        envelope_field_set: Set[str],
        ai_result_map: Dict[str, EnvelopeResult],
        gate1_rejection_map: Dict[str, Dict[str, Any]],
        gate2_rejection_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Diagnose why an unpopulated field is empty."""
        # 1. Was it rejected at Gate 2 (AI hallucination/invalid)?
        if field_path in gate2_rejection_map:
            rej = gate2_rejection_map[field_path]
            return {
                "status": "unpopulated",
                "value": None,
                "reason": "GATE_2_REJECTED",
                "last_layer_attempted": "L7_Physical_Gate2",
                "details": f"AI candidate '{rej.get('rejected_value')}' rejected: {rej.get('reason')}",
            }

        # 2. Was an envelope sent to AI, but AI produced nothing / below threshold?
        if field_path in ai_result_map:
            ai_res = ai_result_map[field_path]
            if ai_res.extracted_value is None:
                return {
                    "status": "unpopulated",
                    "value": None,
                    "reason": "AI_UNRESOLVED",
                    "last_layer_attempted": "L6_AI_Fallback",
                    "details": f"Model {ai_res.model_name} found no matching entity span in envelope context",
                }

        # 3. Was it rejected at Gate 1 (Deterministic physics failure)?
        if field_path in gate1_rejection_map:
            rej = gate1_rejection_map[field_path]
            return {
                "status": "unpopulated",
                "value": None,
                "reason": "GATE_1_REJECTED",
                "last_layer_attempted": "L5_Physical_Gate1",
                "details": f"Deterministic value '{rej.get('rejected_value')}' rejected: {rej.get('reason')}",
            }

        # 4. Did the retailer provide ANY data for this category?
        cat_keywords = cls.CATEGORY_KEYWORDS.get(cat, [cat])
        has_category_context = any(kw in all_source_text for kw in cat_keywords)

        if not has_category_context:
            return {
                "status": "unpopulated",
                "value": None,
                "reason": "NOT_PRESENT_IN_SOURCE",
                "last_layer_attempted": "L1_Scrape_Source",
                "details": f"Retailer provided no mentions of '{cat}' hardware specs on product page",
            }

        # 5. Context exists, but deterministic parser found no matching pattern
        return {
            "status": "unpopulated",
            "value": None,
            "reason": "DETERMINISTIC_NO_MATCH",
            "last_layer_attempted": "L4_Deterministic",
            "details": f"Source text contains general {cat} keywords, but specific {f_name} was not specified",
        }

    @classmethod
    def format_envelope_text_report(
        cls,
        raw_product: RawScrapedProduct,
        envelopes: List[ExtractionEnvelope],
        ai_results: List[EnvelopeResult],
        validation_rejections: List[Dict[str, Any]],
        final_specs: Dict[str, Any],
        product_index: Optional[int] = None,
        total_products: Optional[int] = None,
    ) -> str:
        """Format an exhaustive, human-readable audit text block for all envelopes of a laptop."""
        lines: List[str] = []
        idx_str = f" [{product_index}/{total_products}]" if product_index and total_products else ""
        lines.append("=" * 80)
        lines.append(f"LAPTOP{idx_str}: {raw_product.title}")
        lines.append(f"URL: {raw_product.url}")
        lines.append(f"STORE: {raw_product.store}")
        if raw_product.price:
            lines.append(f"PRICE: {raw_product.price:,.2f} {raw_product.currency or 'EGP'}")
        lines.append(f"TOTAL ENVELOPES: {len(envelopes)}")
        lines.append("=" * 80)

        if not envelopes:
            lines.append("No unresolved envelopes were generated for this product.")
            lines.append("All canonical hardware fields were deterministically resolved or confirmed absent.")
            lines.append("=" * 80)
            return "\n".join(lines)

        ai_map = {r.field_path: r for r in ai_results}
        gate2_rej_map = {r["field_path"]: r for r in validation_rejections if r.get("gate") == 2}

        for i, env in enumerate(envelopes, 1):
            lines.append("")
            lines.append("-" * 80)
            lines.append(f"[ENVELOPE {i}/{len(envelopes)}] TARGET FIELD: {env.field_path}")
            lines.append("-" * 80)
            parts = env.field_path.split(".", 1)
            cat = parts[0] if len(parts) == 2 else "general"
            f_name = parts[1] if len(parts) == 2 else env.field_path

            lines.append(f"Target Category     : {cat}")
            lines.append(f"Field Name          : {f_name}")
            lines.append(f"Field Description   : {env.field_description}")
            lines.append(f"Expected Type       : {env.expected_type}")
            lines.append(f"Failure Reason      : {env.failure_reason}")
            lines.append(f"Section Name        : {env.section_name or 'N/A'}")
            lines.append(f"Allowed Values      : {env.allowed_values if env.allowed_values else 'None (unconstrained)'}")
            if env.cpu_context:
                cpu_info = ", ".join(f"{k}={v}" for k, v in env.cpu_context.items() if v is not None)
                lines.append(f"CPU Constraints     : {cpu_info}")
            else:
                lines.append("CPU Constraints     : N/A")

            lines.append("")
            lines.append("--- [FULL RAW CONTEXT PROVIDED TO AI] ---")
            raw_ctx = env.raw_context.strip() if env.raw_context else "<EMPTY CONTEXT>"
            lines.append(raw_ctx)
            lines.append("-----------------------------------------")

            ai_res = ai_map.get(env.field_path)
            lines.append("")
            lines.append("--- [AI FALLBACK RESOLUTION] ---")
            if ai_res:
                lines.append(f"AI Model            : {ai_res.model_name}")
                lines.append(f"Extracted Value     : {ai_res.extracted_value!r}")
                lines.append(f"Extracted Raw Span  : {ai_res.raw_span!r}")
                lines.append(f"Confidence Score    : {ai_res.confidence:.3f}")
                if ai_res.metadata:
                    lines.append(f"Model Metadata      : {json.dumps(ai_res.metadata)}")
            else:
                lines.append("AI Fallback         : SKIPPED / NOT CONFIGURED")

            lines.append("")
            lines.append("--- [GATE 2 PHYSICAL VALIDATION] ---")
            if env.field_path in gate2_rej_map:
                rej = gate2_rej_map[env.field_path]
                lines.append("Validation Status   : REJECTED")
                lines.append(f"Rejected Candidate  : {rej.get('rejected_value')!r}")
                lines.append(f"Rejection Reason    : {rej.get('reason')}")
                lines.append("Final Schema Value  : null (rejection prevented invalid data)")
            elif ai_res and ai_res.extracted_value is not None:
                final_val = final_specs.get(cat, {}).get(f_name)
                lines.append("Validation Status   : ACCEPTED")
                lines.append(f"Cleaned Value       : {final_val!r}")
                lines.append(f"Final Schema Value  : {final_val!r}")
            else:
                lines.append("Validation Status   : UNRESOLVED")
                lines.append("Final Schema Value  : null (model returned no extraction)")

        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)

    @classmethod
    def format_component_envelope_text_report(
        cls,
        raw_product: RawScrapedProduct,
        component_envelopes: List[ComponentEnvelope],
        component_results: List[ComponentEnvelopeResult],
        validation_rejections: List[Dict[str, Any]],
        final_specs: Dict[str, Any],
        product_index: Optional[int] = None,
        total_products: Optional[int] = None,
    ) -> str:
        """Format an exhaustive audit text block for all component-level envelopes of a laptop."""
        lines: List[str] = []
        idx_str = f" [{product_index}/{total_products}]" if product_index and total_products else ""
        lines.append("=" * 80)
        lines.append(f"LAPTOP{idx_str}: {raw_product.title}")
        lines.append(f"URL: {raw_product.url}")
        lines.append(f"STORE: {raw_product.store}")
        if raw_product.price:
            lines.append(f"PRICE: {raw_product.price:,.2f} {raw_product.currency or 'EGP'}")
        lines.append(f"TOTAL COMPONENT ENVELOPES: {len(component_envelopes)}")
        lines.append("=" * 80)

        if not component_envelopes:
            lines.append("No component envelopes were generated for this product.")
            lines.append("All canonical hardware fields were deterministically resolved or confirmed absent.")
            lines.append("=" * 80)
            return "\n".join(lines)

        comp_res_map = {r.component_name: r for r in component_results}
        gate2_rej_map = {r["field_path"]: r for r in validation_rejections if r.get("gate") == 2}

        for i, env in enumerate(component_envelopes, 1):
            lines.append("")
            lines.append("-" * 80)
            lines.append(f"[COMPONENT ENVELOPE {i}/{len(component_envelopes)}] SUBSYSTEM: {env.component_name.upper()}")
            lines.append("-" * 80)
            lines.append(f"Subsystem Category : {env.component_name}")

            locked_strs = [f"{k}={env.sub_schema[k]!r}" for k in env.locked_fields]
            unresolved_strs = [k for k, v in env.sub_schema.items() if v is None]

            lines.append(f"Pre-filled Anchors : {', '.join(locked_strs) if locked_strs else 'None'}")
            lines.append(f"Unresolved Targets : {', '.join(unresolved_strs) if unresolved_strs else 'None'}")
            if env.cpu_context:
                cpu_info = ", ".join(f"{k}={v}" for k, v in env.cpu_context.items() if v is not None)
                lines.append(f"CPU Constraints    : {cpu_info}")

            lines.append("")
            lines.append("--- [RAW SPECIFICATION CONTEXT PROVIDED TO AI] ---")
            raw_ctx = env.raw_spec.strip() if env.raw_spec else "<EMPTY CONTEXT>"
            lines.append(raw_ctx)
            lines.append("--------------------------------------------------")

            lines.append("")
            lines.append("--- [SUB-SCHEMA TEMPLATE SENT TO AI] ---")
            template_repr = json.dumps({env.component_name: env.sub_schema}, indent=2)
            lines.append(template_repr)
            lines.append("----------------------------------------")

            c_res = comp_res_map.get(env.component_name)
            lines.append("")
            lines.append("--- [AI MODEL RESOLUTION] ---")
            if c_res:
                lines.append(f"AI Model           : {c_res.model_name}")
                if c_res.raw_output:
                    lines.append(f"Raw Model Output   : {c_res.raw_output.strip()}")
                lines.append(f"Extracted Fields   : {json.dumps(c_res.extracted_fields)}")
            else:
                lines.append("AI Fallback        : SKIPPED / NOT CONFIGURED")

            lines.append("")
            lines.append("--- [GATE 2 PHYSICAL VALIDATION] ---")
            for target_field in unresolved_strs:
                full_path = f"{env.component_name}.{target_field}"
                if full_path in gate2_rej_map:
                    rej = gate2_rej_map[full_path]
                    lines.append(f"  * {full_path}: REJECTED candidate={rej.get('rejected_value')!r} (reason: {rej.get('reason')}) -> Final: null")
                elif c_res and target_field in c_res.extracted_fields and c_res.extracted_fields[target_field] is not None:
                    final_val = final_specs.get(env.component_name, {}).get(target_field)
                    lines.append(f"  * {full_path}: ACCEPTED candidate={c_res.extracted_fields[target_field]!r} -> Final: {final_val!r}")
                else:
                    lines.append(f"  * {full_path}: UNRESOLVED / null (model returned no extraction)")

        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)

