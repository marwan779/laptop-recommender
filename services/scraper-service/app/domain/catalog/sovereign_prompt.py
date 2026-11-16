"""Pure domain policy for the SovereignEG dual-source extraction pipeline.

Contains no HTTP, filesystem, S3, or database code. Every function accepts and
returns in-memory dictionaries so the branching decision, prompt construction,
and spec normalization can be unit-tested without network access.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.pipeline.cpu_anchor import CPUAnchorExtractor
from app.pipeline.gpu_anchor import GPUAnchorExtractor
from app.pipeline.physical_validator import PhysicalValidator
from app.pipeline.schema import empty_laptop_specifications

CATEGORY_ORDER: tuple[str, ...] = tuple(empty_laptop_specifications().keys())

_STORE_CONTEXT_SPEC_KEYS = (
    "brand",
    "laptop_family",
    "laptop_model",
    "title",
    "mpn",
    "store_mpn",
    "retailer_sku",
)

_ICECAT_REDUNDANT_KEYS = {"raw_spec", "icecat_product_id", "icecat_url", "icecat_title"}

_CPU_ANCHOR = CPUAnchorExtractor()
_GPU_ANCHOR = GPUAnchorExtractor()

_EXPLICIT_INT_FIELDS = frozenset(
    {
        "identity.release_year",
        "identity.warranty_years",
        "cpu.cores",
        "cpu.threads",
        "cpu.cache_mb",
        "cpu.low_power_cores",
        "cpu.performance_cores",
        "cpu.efficient_cores",
        "cpu.base_power_w",
        "gpu.vram_gb",
        "gpu.boost_clock_mhz",
        "memory.capacity_gb",
        "memory.slot_count",
        "memory.max_supported_gb",
        "storage.capacity_gb",
        "storage.slot_count",
        "storage.installed_ssd_count",
        "storage.max_supported_gb",
        "display.resolution_width",
        "display.resolution_height",
        "display.refresh_rate_hz",
        "display.brightness_nits",
        "power_battery.battery_cells",
        "audio_webcam.speaker_count",
    }
)

_EXPLICIT_FLOAT_FIELDS = frozenset(
    {
        "cpu.clock_base_ghz",
        "cpu.clock_boost_ghz",
        "cpu.npu_tops",
        "gpu.tdp_w",
        "gpu.ai_tops",
        "display.size_inches",
        "display.response_time_ms",
        "power_battery.battery_capacity_wh",
        "power_battery.power_adapter_w",
        "physical.weight_kg",
        "physical.width_mm",
        "physical.depth_mm",
        "physical.height_mm",
        "physical.height_front_mm",
        "physical.height_rear_mm",
        "audio_webcam.speaker_power_w",
    }
)

_EXPLICIT_BOOL_FIELDS = frozenset(
    {
        "identity.is_bundle",
        "gpu.integrated",
        "memory.is_soldered",
        "display.touchscreen",
        "power_battery.fast_charging",
        "power_battery.usb_c_pd_charging",
        "build_security.has_backlit_keyboard",
        "build_security.has_fingerprint",
        "build_security.has_numpad",
        "build_security.has_copilot_key",
        "audio_webcam.has_privacy_shutter",
        "audio_webcam.has_ir_camera",
        "connectivity.ethernet",
        "connectivity.usb_c_displayport",
        "connectivity.usb_c_power_delivery",
        "connectivity.has_card_reader",
    }
)


def should_use_sovereign_pipeline(
    level1_count: int,
    threshold: int,
    has_key: bool,
    mode: str = "auto",
) -> bool:
    """Decide whether Pipeline B (SovereignEG) should run instead of Pipeline A.

    ``legacy`` always selects the original large-batch pipeline. ``sovereign``
    forces Pipeline B when a key exists, but safely degrades to Pipeline A when
    no key is configured. ``auto`` selects Pipeline B only for batches at or
    below the configured threshold.
    """
    normalized_mode = (mode or "auto").strip().lower()
    if normalized_mode == "legacy":
        return False
    if not has_key:
        return False
    if normalized_mode == "sovereign":
        return True
    return max(0, int(level1_count)) <= max(0, int(threshold))


def _as_mapping(laptop: Any) -> dict[str, Any]:
    if isinstance(laptop, dict):
        return laptop
    model_dump = getattr(laptop, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


def _clean_icecat_section(section: Any) -> dict[str, Any]:
    if not isinstance(section, dict):
        return {}
    return {
        key: value
        for key, value in section.items()
        if key not in _ICECAT_REDUNDANT_KEYS and value not in (None, "", [], {})
    }


def build_dual_source_payload(laptop: Any, icecat_specs: dict[str, Any] | None) -> dict[str, Any]:
    """Build the compact per-laptop payload sent to SovereignEG.

    Only high-signal inputs are included: identity tokens, the Egyptian store
    raw context, and the normalized Icecat sections that actually carry data.
    """
    lap = _as_mapping(laptop)
    raw_context = lap.get("raw_store_context") or {}
    if not isinstance(raw_context, dict):
        raw_context = {}

    identity = {
        key: lap.get(key)
        for key in ("canonical_id", "title", "brand", "laptop_family", "laptop_model", "mpn")
        if lap.get(key) not in (None, "")
    }
    for key in ("store_mpn", "retailer_sku"):
        value = lap.get(key) or raw_context.get(key)
        if value not in (None, ""):
            identity[key] = value

    store_specs = raw_context.get("source_table") or {}
    store_context = {
        "source_table": store_specs if isinstance(store_specs, dict) else {},
        "raw_description": str(raw_context.get("raw_description") or ""),
        "store_slot_count": raw_context.get("store_slot_count"),
    }

    icecat_context: dict[str, Any] = {
        "icecat_match_type": lap.get("icecat_match_type"),
        "icecat_mpn": lap.get("icecat_mpn"),
    }
    if isinstance(icecat_specs, dict):
        for category in CATEGORY_ORDER:
            cleaned = _clean_icecat_section(icecat_specs.get(category))
            if cleaned:
                icecat_context[category] = cleaned

    return {
        "identity": identity,
        "store_raw_specs": store_context,
        "icecat_context": icecat_context,
        "deterministic_specs": lap.get("specs") or {},
    }


def build_system_prompt() -> str:
    """Author the strict dual-source extraction system prompt."""
    return (
        "You are a deterministic laptop specification extractor for the Egyptian retail market.\n"
        "You receive TWO sources for a single laptop configuration and must merge them into one\n"
        "strict JSON object matching the canonical 12-category laptop schema.\n\n"
        "SOURCE HIERARCHY\n"
        "1. PRIMARY TRUTH - the Egyptian store (`store_raw_specs` + `identity.title` + `identity.store_mpn`).\n"
        "   The store ALWAYS wins when it explicitly states a value for this exact SKU:\n"
        "   - memory: capacity_gb, memory_type, speed, is_soldered, layout, slot_count, max_supported_gb.\n"
        "     When the store says 'Not upgradable' or 'On-board' with no SO-DIMM, set\n"
        "     is_soldered=true, slot_count=0, max_supported_gb=capacity_gb.\n"
        "   - storage: capacity_gb, storage_type, interface, form_factor, and slot_count.\n"
        "     Count EVERY distinct M.2 slot explicitly listed (e.g. '1 x M.2 2280 + 1 x M.2 2230'\n"
        "     or 'One M.2 2242 + One M.2 2280' => slot_count=2).\n"
        "   - connectivity: exact USB4 / Thunderbolt / USB 3.2 Gen 1/2 counts and connector types.\n"
        "   - physical height: convert cm to mm when stated in cm\n"
        "     (e.g. '1.49 ~ 1.69 cm' => height_front_mm=14.9, height_rear_mm=16.9).\n"
        "   - build_security.has_backlit_keyboard must be true when the store mentions\n"
        "     backlighting, backlit, or an RGB keyboard.\n"
        "   - display, cpu, and gpu values explicitly stated for this SKU.\n"
        "   Especially enforce Store > Icecat when `icecat_mpn` differs from `identity.store_mpn`.\n\n"
        "2. SECONDARY TRUTH - Icecat (`icecat_context`).\n"
        "   Fill fields the Egyptian store omitted ONLY when Icecat does not contradict the store:\n"
        "   battery_capacity_wh, power_adapter_w, battery_cells, gpu.tdp_w, width_mm, depth_mm,\n"
        "   weight_kg, speaker_count, webcam_resolution, wifi, bluetooth, security_features.\n\n"
        "NO HALLUCINATION\n"
        "- Never invent values that appear in neither source; return null for unknown fields.\n"
        "- Never copy an Icecat value into a field the store explicitly states differently.\n\n"
        "STRICT SCHEMA\n"
        "Return a single JSON object with exactly these top-level categories:\n"
        "identity, cpu, gpu, memory, storage, display, power_battery, physical, build_security,\n"
        "audio_webcam, connectivity, operating_system.\n"
        "Each category must use the canonical field names and value types from the provided\n"
        "`deterministic_specs` skeleton. Preserve non-null deterministic values when the sources\n"
        "are silent or agree. You may add a top-level `conflicts_resolved` array of short strings\n"
        "describing any store-vs-Icecat conflict you resolved. Output JSON only, no markdown\n"
        "fences, no commentary."
    )


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Build the OpenAI-compatible message list for one dual-source laptop."""
    import json

    return [
        {"role": "system", "content": build_system_prompt()},
        {
            "role": "user",
            "content": (
                "Extract the canonical laptop specifications from this dual-source payload.\n"
                "Return JSON only.\n\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)
            ),
        },
    ]


def build_batch_messages(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build an OpenAI-compatible message list for a micro-batch of 1-5 laptops."""
    import json

    if len(items) == 1:
        return build_messages(items[0])

    return [
        {"role": "system", "content": build_system_prompt()},
        {
            "role": "user",
            "content": (
                "Extract canonical specifications for EACH laptop in `laptops` below.\n"
                "Return a single JSON object with one top-level key `results` mapping each\n"
                "`identity.canonical_id` string to its 12-category spec object (plus optional\n"
                "`conflicts_resolved`). Output JSON only.\n\n"
                + json.dumps({"laptops": items}, ensure_ascii=False, sort_keys=True)
            ),
        },
    ]


def extract_batch_results(parsed: dict[str, Any] | None, expected_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Extract `{canonical_id: spec_payload}` from either single-item or micro-batch JSON."""
    if not isinstance(parsed, dict) or not expected_ids:
        return {}

    if len(expected_ids) == 1 and any(cat in parsed for cat in CATEGORY_ORDER):
        return {expected_ids[0]: parsed}

    results_node = parsed.get("results")
    if isinstance(results_node, dict):
        matched: dict[str, dict[str, Any]] = {}
        for cid in expected_ids:
            val = results_node.get(cid)
            if isinstance(val, dict):
                matched[cid] = val
        return matched

    if isinstance(results_node, list):
        by_id: dict[str, dict[str, Any]] = {}
        for item in results_node:
            if not isinstance(item, dict):
                continue
            cid = item.get("canonical_id") or (item.get("identity") or {}).get("canonical_id")
            if isinstance(cid, str) and cid in expected_ids:
                by_id[cid] = item
        return by_id

    # Direct top-level map fallback if model omitted the `results` wrapper
    direct: dict[str, dict[str, Any]] = {}
    for cid in expected_ids:
        val = parsed.get(cid)
        if isinstance(val, dict):
            direct[cid] = val
    return direct


def _coerce_like(base: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(base, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
        return base
    if isinstance(base, int) and not isinstance(base, bool):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return value
    if isinstance(base, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if isinstance(base, list) and not isinstance(value, list):
        return [value] if value not in (None, "") else base
    return value


def _canonicalize_silicon(specs: dict[str, Any], title: str, store_text: list[str]) -> None:
    cpu = specs.setdefault("cpu", {})
    cpu_candidate = " ".join(str(part) for part in (cpu.get("full_name"), cpu.get("model"), title) if part).strip()
    cpu_match = _CPU_ANCHOR.match(cpu_candidate, store_text)
    if cpu_match:
        _, entry = cpu_match
        anchor = _CPU_ANCHOR.populate_cpu_specs(entry)
        for key, value in anchor.items():
            if cpu.get(key) in (None, "") and value not in (None, ""):
                cpu[key] = value

    gpu = specs.setdefault("gpu", {})
    gpu_candidate = " ".join(str(part) for part in (gpu.get("model"), gpu.get("variant"), title) if part).strip()
    gpu_match = _GPU_ANCHOR.match(gpu_candidate, store_text)
    if gpu_match:
        _, entry = gpu_match
        anchor = _GPU_ANCHOR.populate_gpu_specs(entry)
        for key, value in anchor.items():
            if key == "tdp_w":
                continue
            if gpu.get(key) in (None, "") and value not in (None, ""):
                gpu[key] = value


def _coerce_typed_field(field_path: str, base: Any, value: Any) -> Any:
    if value is None:
        return None
    if field_path in _EXPLICIT_BOOL_FIELDS or isinstance(base, bool):
        return _coerce_like(False, value)
    if field_path in _EXPLICIT_INT_FIELDS or (isinstance(base, int) and not isinstance(base, bool)):
        return _coerce_like(0, value)
    if field_path in _EXPLICIT_FLOAT_FIELDS or isinstance(base, float):
        return _coerce_like(0.0, value)
    return _coerce_like(base, value)


def _validate_category(
    category: str,
    merged: dict[str, Any],
    deterministic: dict[str, Any],
) -> None:
    for field_name, base_value in merged.items():
        if field_name == "raw_spec":
            continue
        field_path = f"{category}.{field_name}"
        raw_value = merged.get(field_name)
        if raw_value is None:
            continue
        ok, normalized, _reason = PhysicalValidator.validate_field(field_path, raw_value)
        if ok:
            merged[field_name] = _coerce_typed_field(field_path, base_value, normalized)
        else:
            fallback = deterministic.get(field_name)
            merged[field_name] = deepcopy(fallback) if fallback is not None else None


def validate_and_normalize_extracted_specs(
    extracted: dict[str, Any] | None,
    deterministic_specs: dict[str, Any] | None = None,
    title: str = "",
    icecat_specs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, normalize, and anchor an LLM extraction against the canonical schema.

    ``deterministic_specs`` supplies verified fallbacks for null or invalid
    fields. ``icecat_specs`` is only used for CPU/GPU grounding context, never
    for blindly overwriting a store-conflicting field.
    """
    skeleton = empty_laptop_specifications()
    deterministic = deterministic_specs if isinstance(deterministic_specs, dict) else {}
    payload = extracted if isinstance(extracted, dict) else {}

    merged_specs: dict[str, Any] = {}
    store_text: list[str] = []

    for category in CATEGORY_ORDER:
        base_category = deterministic.get(category) or {}
        if not isinstance(base_category, dict):
            base_category = {}
        candidate_category = payload.get(category) or {}
        if not isinstance(candidate_category, dict):
            candidate_category = {}

        merged_category: dict[str, Any] = {}
        for field_name, empty_value in skeleton[category].items():
            det_value = base_category.get(field_name)
            raw_value = candidate_category.get(field_name)
            chosen = raw_value if raw_value not in (None, "", [], {}) else det_value
            merged_category[field_name] = _coerce_typed_field(
                f"{category}.{field_name}",
                det_value if det_value is not None else empty_value,
                chosen,
            )
        merged_specs[category] = merged_category

        raw_text = base_category.get("raw_spec")
        if isinstance(raw_text, str) and raw_text.strip():
            store_text.append(raw_text)

    _validate_category("memory", merged_specs["memory"], deterministic.get("memory") or {})
    _validate_category("storage", merged_specs["storage"], deterministic.get("storage") or {})
    _validate_category("display", merged_specs["display"], deterministic.get("display") or {})
    _validate_category("power_battery", merged_specs["power_battery"], deterministic.get("power_battery") or {})
    _validate_category("physical", merged_specs["physical"], deterministic.get("physical") or {})
    _validate_category("build_security", merged_specs["build_security"], deterministic.get("build_security") or {})
    _validate_category("audio_webcam", merged_specs["audio_webcam"], deterministic.get("audio_webcam") or {})
    _validate_category("connectivity", merged_specs["connectivity"], deterministic.get("connectivity") or {})
    _validate_category("cpu", merged_specs["cpu"], deterministic.get("cpu") or {})
    _validate_category("gpu", merged_specs["gpu"], deterministic.get("gpu") or {})
    _validate_category("identity", merged_specs["identity"], deterministic.get("identity") or {})
    _validate_category(
        "operating_system", merged_specs["operating_system"], deterministic.get("operating_system") or {}
    )

    if isinstance(icecat_specs, dict):
        ice_title = icecat_specs.get("identity") or {}
        if isinstance(ice_title, dict):
            for value in ice_title.values():
                if isinstance(value, str) and value.strip():
                    store_text.append(value)

    _canonicalize_silicon(merged_specs, title, store_text)

    conflicts = payload.get("conflicts_resolved")
    if isinstance(conflicts, list):
        merged_specs["conflicts_resolved"] = [str(item) for item in conflicts if str(item).strip()]

    return merged_specs


__all__ = [
    "CATEGORY_ORDER",
    "build_batch_messages",
    "build_dual_source_payload",
    "build_messages",
    "build_system_prompt",
    "extract_batch_results",
    "should_use_sovereign_pipeline",
    "validate_and_normalize_extracted_specs",
]
