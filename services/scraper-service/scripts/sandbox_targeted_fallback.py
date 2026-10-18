"""Sandbox Targeted AI Fallback Test Script.

Tests the proposed architecture where Layer 4 (Deterministic Extractor) intentionally
leaves the high-entropy / semantic fields as `None`:
    1. memory.slot_count
    2. memory.max_supported_gb
    3. memory.is_soldered
    4. storage.slot_count
    5. storage.max_supported_gb
    6. audio_webcam.has_privacy_shutter
    7. audio_webcam.has_ir_camera
    8. physical.chassis_material
    9. identity.is_bundle

And delegates them to Layer 6 (NuExtract-2.0-2B) via subsystem ComponentEnvelopes.
Results are saved to a separate sandbox file, leaving production files 100% untouched.

Usage:
    .venv/Scripts/python scripts/sandbox_targeted_fallback.py --index 0 --device cuda
    .venv/Scripts/python scripts/sandbox_targeted_fallback.py --sample --device cuda
"""

import argparse
import copy
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.abspath("."))

from pipeline.ai_fallback.nuextract import NuExtractONNXFallbackExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.deterministic import DeterministicExtractor
from pipeline.physical_validator import PhysicalValidator
from pipeline.sanitizer import TextSanitizer
from pipeline.schema import (
    ComponentEnvelope,
    ComponentEnvelopeResult,
    ExtractionEnvelope,
    RawScrapedProduct,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("sandbox")


class SandboxDeterministicExtractor(DeterministicExtractor):
    """Subclass of DeterministicExtractor that leaves hard-for-regex fields None.
    
    This simulates Layer 4 skipping regex guesswork on slots, upgrade caps,
    shutter/IR proximity, and bundle classification.
    """

    def _extract_memory(
        self,
        title: str,
        table: Dict[str, str],
        routed_table: Optional[Dict[str, List[Tuple[str, str]]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
        cpu_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super()._extract_memory(title, table, routed_table, context, specs, envelopes, cpu_context)
        # Intentionally leave hard fields None for AI fallback:
        specs["memory"]["slot_count"] = None
        specs["memory"]["max_supported_gb"] = None
        specs["memory"]["is_soldered"] = None

    def _extract_storage(
        self,
        title: str,
        table: Dict[str, str],
        routed_table: Optional[Dict[str, List[Tuple[str, str]]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        super()._extract_storage(title, table, routed_table, context, specs, envelopes)
        # Intentionally leave hard fields None for AI fallback:
        specs["storage"]["slot_count"] = None
        specs["storage"]["max_supported_gb"] = None

    def _extract_audio_webcam(
        self,
        table: Dict[str, str],
        routed_table: Optional[Dict[str, List[Tuple[str, str]]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        super()._extract_audio_webcam(table, routed_table, context, specs, envelopes)
        # Intentionally leave hard fields None for AI fallback:
        specs["audio_webcam"]["has_privacy_shutter"] = None
        specs["audio_webcam"]["has_ir_camera"] = None

    def _extract_build_security(
        self,
        title: str,
        table: Dict[str, str],
        routed_table: Optional[Dict[str, List[Tuple[str, str]]]],
        context: str,
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        super()._extract_build_security(title, table, routed_table, context, specs, envelopes)
        # Ensure materials rows are collected in raw_spec for build_security
        mat_raw = self._collect_raw_spec(
            table=table,
            target_buckets={"keyboard", "security", "pointing_device", "materials"},
            fallback_text=context,
        )
        if mat_raw:
            specs["build_security"]["raw_spec"] = mat_raw
        # Intentionally leave hard fields None for AI fallback:
        specs["build_security"]["chassis_material"] = None

    def _extract_identity(
        self,
        title: str,
        table: Dict[str, str],
        routed_table: Optional[Dict[str, List[Tuple[str, str]]]],
        specs: Dict[str, Any],
        envelopes: List[ExtractionEnvelope],
    ) -> None:
        super()._extract_identity(title, table, routed_table, specs, envelopes)
        # Intentionally leave hard fields None for AI fallback:
        specs["identity"]["is_bundle"] = None


class SandboxPhysicalValidator(PhysicalValidator):
    """Extended validator with support for slot counts, max storage, and bundle flags."""

    @classmethod
    def validate_field(
        cls,
        field_path: str,
        value: Any,
        cpu_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Any, Optional[str]]:
        if value is None:
            return True, None, None

        if field_path in ("memory.slot_count", "storage.slot_count"):
            try:
                val = int(value)
                if 0 <= val <= 8:
                    return True, val, None
                return False, None, f"slot_count_{val}_out_of_bounds"
            except (ValueError, TypeError):
                return False, None, "type_error"

        if field_path in ("memory.max_supported_gb", "storage.max_supported_gb"):
            try:
                val = int(float(value))
                if 4 <= val <= 32768:
                    return True, val, None
                return False, None, f"max_capacity_{val}_out_of_bounds"
            except (ValueError, TypeError):
                return False, None, "type_error"

        if field_path == "identity.is_bundle":
            if isinstance(value, bool):
                return True, value, None
            if str(value).lower() in ("true", "yes", "1"):
                return True, True, None
            if str(value).lower() in ("false", "no", "0"):
                return True, False, None
            return False, None, "invalid_boolean"

        if field_path == "build_security.chassis_material":
            if isinstance(value, str) and value.strip():
                return True, value.strip(), None
            return False, None, "type_error"

        return super().validate_field(field_path, value, cpu_context)


# Component definitions including all hard-for-regex target fields
SANDBOX_COMPONENT_DEFINITIONS = {
    "identity": ["laptop_family", "laptop_model", "manufacturer_part_number", "color", "warranty_years", "is_bundle"],
    "memory": ["capacity_gb", "memory_type", "speed", "slot_count", "max_supported_gb", "is_soldered"],
    "storage": ["capacity_gb", "storage_type", "interface", "form_factor", "slot_count", "max_supported_gb"],
    "display": ["size_inches", "resolution", "refresh_rate_hz", "panel_type", "aspect_ratio", "touchscreen", "brightness_nits", "color_gamut"],
    "power_battery": ["battery_capacity_wh", "power_adapter_w", "battery_cells", "fast_charging"],
    "physical": ["weight_kg", "width_mm", "depth_mm", "height_mm"],
    "audio_webcam": ["speaker_count", "webcam_resolution", "has_ir_camera", "has_privacy_shutter", "microphone"],
    "build_security": ["has_backlit_keyboard", "keyboard_backlight_type", "has_fingerprint", "has_numpad", "chassis_material"],
    "operating_system": ["name"],
}


def run_sandbox_on_product(
    raw_prod: RawScrapedProduct,
    deterministic: SandboxDeterministicExtractor,
    cpu_anchor: CPUAnchorExtractor,
    sanitizer: TextSanitizer,
    validator: SandboxPhysicalValidator,
    ai_fallback: NuExtractONNXFallbackExtractor,
) -> Dict[str, Any]:
    """Execute the sandbox pipeline on a single product."""
    t0 = time.time()
    
    # 1. Sanitizer
    sanitized_title = sanitizer.clean_text(raw_prod.title)
    sanitized_table = sanitizer.sanitize_table(raw_prod.raw_tables.get("specs", {}))
    sanitized_sections = sanitizer.sanitize_sections(raw_prod.raw_sections)

    if raw_prod.retailer_sku and "SKU" not in sanitized_table:
        sanitized_table["SKU"] = raw_prod.retailer_sku
    if raw_prod.mpn and "Part Number" not in sanitized_table:
        sanitized_table["Part Number"] = raw_prod.mpn

    # 2. CPU Anchor
    spec_text_snippets = list(sanitized_table.values()) + list(sanitized_sections.values())
    cpu_specs, cpu_context, cpu_key = cpu_anchor.extract(
        title=sanitized_title,
        spec_texts=spec_text_snippets,
    )

    # 3. Layer 4: Sandbox Deterministic Extractor (leaves target fields None)
    specs, _ = deterministic.extract(
        title=sanitized_title,
        sanitized_table=sanitized_table,
        sanitized_sections=sanitized_sections,
        cpu_context=cpu_context,
    )

    if raw_prod.retailer_sku and not specs["identity"].get("retailer_sku"):
        specs["identity"]["retailer_sku"] = raw_prod.retailer_sku
    if raw_prod.mpn and not specs["identity"].get("manufacturer_part_number"):
        specs["identity"]["manufacturer_part_number"] = raw_prod.mpn

    # Lock CPU specs
    if cpu_specs:
        cpu_raw_spec = specs.get("cpu", {}).get("raw_spec")
        specs["cpu"] = copy.deepcopy(cpu_specs)
        if cpu_raw_spec:
            specs["cpu"]["raw_spec"] = cpu_raw_spec

    t_deterministic = time.time() - t0

    # 4. Layer 5: Gate 1 Physical Validation
    for cat, cat_dict in list(specs.items()):
        if cat == "cpu":
            continue
        for f_name, f_val in list(cat_dict.items()):
            field_path = f"{cat}.{f_name}"
            is_valid, cleaned_val, _ = validator.validate_field(field_path, f_val, cpu_context)
            if is_valid:
                specs[cat][f_name] = cleaned_val

    # 5. Component Envelope Generation
    component_envelopes: List[ComponentEnvelope] = []
    for comp_name, comp_fields in SANDBOX_COMPONENT_DEFINITIONS.items():
        comp_dict = specs.get(comp_name, {})
        unresolved = [f for f in comp_fields if comp_dict.get(f) is None]
        if not unresolved:
            continue

        raw_spec = comp_dict.get("raw_spec") or ""
        if not raw_spec or raw_spec.strip() in ("", "None", "Spec: None"):
            if comp_name == "identity":
                raw_spec = sanitized_title
            elif comp_name == "power_battery":
                raw_spec = sanitized_sections.get("Battery & Power", "") or sanitized_sections.get("Power", "") or ""
            elif comp_name == "display":
                raw_spec = sanitized_sections.get("Display", "") or ""
            elif comp_name == "audio_webcam":
                raw_spec = sanitized_sections.get("Audio & Camera", "") or sanitized_sections.get("Audio", "") or sanitized_sections.get("Camera", "") or ""
            elif comp_name == "build_security":
                raw_spec = sanitized_sections.get("Design & Keyboard", "") or sanitized_sections.get("Keyboard", "") or sanitized_sections.get("Security", "") or ""
            elif comp_name == "operating_system":
                raw_spec = sanitized_sections.get("Operating System", "") or sanitized_sections.get("OS", "") or sanitized_title or ""

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
                cpu_context=cpu_context,
            )
        )

    # 6. Layer 6: AI Fallback Extraction (NuExtract-2.0-2B)
    t_ai_start = time.time()
    ai_results = []
    for env in component_envelopes:
        cr = ai_fallback.extract_component_envelope(env)
        ai_results.append(cr)
        for f_name, candidate_val in cr.extracted_fields.items():
            field_path = f"{cr.component_name}.{f_name}"
            # Layer 7: Gate 2 Validation
            is_valid, cleaned_val, _ = validator.validate_field(field_path, candidate_val, cpu_context)
            if is_valid and cleaned_val is not None:
                specs[cr.component_name][f_name] = cleaned_val

    t_ai_total = time.time() - t_ai_start
    t_total = time.time() - t0

    return {
        "title": raw_prod.title,
        "url": raw_prod.url,
        "cpu_key": cpu_key,
        "specs": specs,
        "envelopes_count": len(component_envelopes),
        "envelopes": [
            {
                "subsystem": env.component_name,
                "unresolved": [f for f, v in env.sub_schema.items() if v is None],
                "resolved_by_ai": next((cr.extracted_fields for cr in ai_results if cr.component_name == env.component_name), {}),
                "raw_context": env.raw_spec,
            }
            for env in component_envelopes
        ],
        "timing": {
            "deterministic_s": round(t_deterministic, 3),
            "ai_fallback_s": round(t_ai_total, 3),
            "total_s": round(t_total, 3),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Sandbox Targeted AI Fallback Test")
    parser.add_argument("--index", type=int, default=None, help="Single laptop index to test (0-123)")
    parser.add_argument("--sample", action="store_true", help="Run on a curated representative sample of 6 edge-case laptops")
    parser.add_argument("--all", action="store_true", help="Run on all laptops in the catalog")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of laptops to process")
    parser.add_argument("--live", action="store_true", help="Crawl live laptops directly from CompuMarts website")
    parser.add_argument("--resume", action="store_true", help="Resume from existing checkpoint file")
    parser.add_argument("--checkpoint", type=str, default="scratch/sandbox_results.checkpoint.jsonl", help="Checkpoint jsonl path")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"], help="Inference device")
    parser.add_argument("--output", type=str, default="scratch/sandbox_results.json", help="Sandbox output file")
    args = parser.parse_args()

    items_to_process = []
    
    if args.live:
        from app.stores.compumarts import CompumartsStoreScraper
        print("[Live Scraper] Discovering and scraping live in-stock laptops from CompuMarts...")
        scraper = CompumartsStoreScraper()
        live_products = scraper.scrape_catalog(level=2, limit=args.limit)
        print(f"[Live Scraper] Retrieved {len(live_products)} live laptop PDPs.")
        for idx, prod in enumerate(live_products):
            items_to_process.append({
                "index": idx,
                "title": prod.title,
                "url": prod.product_url,
                "price_egp": prod.price_egp,
                "source_table": prod.specs or {},
                "raw_sections": {"Description": prod.raw_description or ""},
                "sku": prod.sku,
                "mpn": prod.mpn,
                "baseline_specs": {},
            })
    else:
        results_file = "pipeline_results_compumarts.json"
        if not os.path.exists(results_file):
            print(f"Error: {results_file} not found.")
            sys.exit(1)

        with open(results_file, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        if args.sample:
            target_indices = [0, 3, 19, 69, 70, 78]
        elif args.index is not None:
            target_indices = [args.index]
        elif args.all:
            target_indices = list(range(len(catalog)))
        else:
            target_indices = [0]

        if args.limit is not None and not args.sample and args.index is None:
            target_indices = target_indices[:args.limit]

        for idx in target_indices:
            item = catalog[idx]
            id_raw = item.get("specs", {}).get("identity", {}).get("raw_spec", "")
            import re
            m_pn = re.search(r"\bPart Number:\s*([^|]+)", id_raw)
            mpn = m_pn.group(1).strip() if m_pn else None
            m_sku = re.search(r"\bSKU:\s*([^|]+)", id_raw)
            sku = m_sku.group(1).strip() if m_sku else None

            items_to_process.append({
                "index": idx,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "price_egp": item.get("price_egp"),
                "source_table": dict(item.get("source_table", {})),
                "raw_sections": {},
                "sku": sku,
                "mpn": mpn,
                "baseline_specs": item.get("specs", {}),
            })

    total_count = len(items_to_process)
    print("=" * 80)
    print(f"SANDBOX TARGETED AI FALLBACK BENCHMARK")
    print(f"Total laptops to evaluate: {total_count} (Mode: {'Live Scrape' if args.live else 'Catalog Replay'})")
    print(f"Device: {args.device} | Model: numind/NuExtract-2.0-2B")
    print(f"Checkpoint File: {args.checkpoint}")
    print(f"Output File:     {args.output}")
    print("=" * 80)

    # Load existing checkpoint if resume requested
    completed_keys = set()
    sandbox_outputs = []
    checkpoint_dir = os.path.dirname(args.checkpoint)
    if checkpoint_dir:
        os.makedirs(checkpoint_dir, exist_ok=True)

    if args.resume and os.path.exists(args.checkpoint):
        with open(args.checkpoint, "r", encoding="utf-8") as f_chk:
            for line in f_chk:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        k = rec.get("url") or rec.get("index")
                        if k is not None:
                            completed_keys.add(k)
                            sandbox_outputs.append(rec)
                    except json.JSONDecodeError:
                        pass
        print(f"Resuming from checkpoint: {len(completed_keys)} laptops already processed. Skipping them.")

    # Initialize components
    sanitizer = TextSanitizer()
    cpu_anchor = CPUAnchorExtractor()
    deterministic = SandboxDeterministicExtractor()
    validator = SandboxPhysicalValidator()

    print("\n[Loading NuExtract-2.0-2B for AI Fallback]...")
    ai_fallback = NuExtractONNXFallbackExtractor(
        model_id="numind/NuExtract-2.0-2B",
        execution_provider="CUDAExecutionProvider" if args.device == "cuda" else "CPUExecutionProvider",
        lazy_load=False,
    )

    t_run_start = time.time()
    processed_this_run = 0

    with open(args.checkpoint, "a", encoding="utf-8") as ckpt_f:
        for count, item in enumerate(items_to_process, 1):
            key = item.get("url") or item.get("index")
            if args.resume and key in completed_keys:
                continue

            idx = item["index"]
            title = item["title"]

            raw_prod = RawScrapedProduct(
                url=item.get("url", ""),
                store="compumarts",
                title=title,
                raw_html="",
                raw_tables={"specs": item["source_table"]},
                raw_sections=item.get("raw_sections", {}),
                price=item.get("price_egp"),
                retailer_sku=item.get("sku"),
                mpn=item.get("mpn"),
            )

            pct = (count / total_count) * 100
            print("\n" + "-" * 80)
            print(f"[{count}/{total_count}] ({pct:.1f}%) RUNNING LAPTOP [{idx}]: {title[:70]}...")
            print("-" * 80)

            res = run_sandbox_on_product(
                raw_prod=raw_prod,
                deterministic=deterministic,
                cpu_anchor=cpu_anchor,
                sanitizer=sanitizer,
                validator=validator,
                ai_fallback=ai_fallback,
            )
            res["index"] = idx
            res["baseline_specs"] = item["baseline_specs"]
            sandbox_outputs.append(res)
            processed_this_run += 1

            # Stream checkpoint write
            ckpt_f.write(json.dumps(res, ensure_ascii=False) + "\n")
            ckpt_f.flush()

            # Save periodically to final output
            if processed_this_run % 5 == 0 or count == total_count:
                out_dir = os.path.dirname(args.output)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(args.output, "w", encoding="utf-8") as out_f:
                    json.dump(sandbox_outputs, out_f, indent=2, ensure_ascii=False)

            print(f"  Envelopes Dispatched: {res['envelopes_count']}")
            print(f"  Deterministic Time:   {res['timing']['deterministic_s']}s")
            print(f"  AI Fallback Time:     {res['timing']['ai_fallback_s']}s")
            print(f"  Total Item Time:      {res['timing']['total_s']}s")

            # Brief field comparison print
            TARGET_FIELDS = [
                ("memory", "slot_count"),
                ("memory", "max_supported_gb"),
                ("memory", "is_soldered"),
                ("storage", "slot_count"),
                ("storage", "max_supported_gb"),
                ("audio_webcam", "has_privacy_shutter"),
                ("audio_webcam", "has_ir_camera"),
                ("build_security", "chassis_material"),
                ("identity", "is_bundle"),
            ]
            for cat, field_name in TARGET_FIELDS:
                ai_val = res["specs"].get(cat, {}).get(field_name)
                base_val = res["baseline_specs"].get(cat, {}).get(field_name)
                if ai_val is not None or base_val is not None:
                    raw_s = res["specs"].get(cat, {}).get("raw_spec") or ""
                    raw_disp = (raw_s[:55] + "...") if len(raw_s) > 55 else raw_s
                    print(f"    {cat}.{field_name:24s} -> AI: {str(ai_val):12s} | Base: {str(base_val):12s} | Raw: {raw_disp}")

    # Final save
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(sandbox_outputs, f, indent=2, ensure_ascii=False)

    total_elapsed = time.time() - t_run_start
    print("\n" + "=" * 80)
    print(f"SANDBOX RUN COMPLETE! Processed {processed_this_run} laptops in {total_elapsed/60:.2f} mins.")
    print(f"Results saved to:    {args.output}")
    print(f"Checkpoint saved to: {args.checkpoint}")
    print("=" * 80)


if __name__ == "__main__":
    main()

