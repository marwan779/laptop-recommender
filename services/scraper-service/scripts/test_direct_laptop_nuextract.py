"""Direct Full-Laptop NuExtract-2.0-2B Extraction Test Script.

Sends an entire laptop's raw specification text directly to NuExtract-2.0-2B in a
single inference pass (zero regex / zero heuristic extraction), extracting all 10
subsystems simultaneously (excluding CPU and GPU, which are handled by deterministic dictionaries).

Usage:
    .venv/Scripts/python scripts/test_direct_laptop_nuextract.py --index 0
    .venv/Scripts/python scripts/test_direct_laptop_nuextract.py --index 3 --device cuda
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict

# Ensure local imports work
sys.path.insert(0, os.path.abspath("."))

import torch
from transformers import AutoTokenizer, Qwen2VLForConditionalGeneration


# Full laptop schema excluding CPU and GPU
LAPTOP_FULL_TEMPLATE: Dict[str, Any] = {
    "identity": {
        "brand": "",
        "laptop_family": "",
        "laptop_model": "",
        "manufacturer_part_number": "",
        "color": "",
        "is_bundle": False,
        "warranty": "",
    },
    "memory": {
        "capacity_gb": None,
        "memory_type": "",
        "speed": None,
        "slot_count": None,
        "max_supported_gb": None,
        "is_soldered": None,
    },
    "storage": {
        "capacity_gb": None,
        "storage_type": "",
        "interface": "",
        "form_factor": "",
        "slot_count": None,
        "max_supported_gb": None,
    },
    "display": {
        "size_inches": None,
        "resolution": "",
        "panel_type": "",
        "refresh_rate_hz": None,
        "aspect_ratio": "",
        "touchscreen": None,
        "brightness_nits": None,
        "color_gamut": "",
    },
    "power_battery": {
        "battery_capacity_wh": None,
        "battery_cells": None,
        "power_adapter_w": None,
    },
    "physical": {
        "weight_kg": None,
        "width_mm": None,
        "depth_mm": None,
        "height_mm": None,
    },
    "build_security": {
        "has_backlit_keyboard": None,
        "keyboard_backlight_type": "",
        "has_fingerprint": None,
        "has_numpad": None,
    },
    "audio_webcam": {
        "speaker_count": None,
        "webcam_resolution": "",
        "has_privacy_shutter": None,
        "has_ir_camera": None,
    },
    "connectivity": {
        "wifi": "",
        "bluetooth": "",
        "ethernet": "",
        "ports": [],
    },
    "operating_system": {
        "name": "",
    },
}


def build_raw_context(item: Dict[str, Any]) -> str:
    """Format title and raw table rows into an un-extracted, raw textual context."""
    lines = [f"Product Title: {item.get('title', '')}\n", "Specifications Table:"]
    source_table = item.get("source_table", {})
    for k, v in source_table.items():
        if k and v:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def format_nuextract_prompt(template: Dict[str, Any], context: str) -> str:
    """Format input text and template into the official NuExtract-2.0 prompt."""
    template_str = json.dumps(template, indent=2)
    return (
        f"<|im_start|>user\n"
        f"# Template:\n{template_str}\n"
        f"# Context:\n{context}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Test sending an entire laptop directly to NuExtract-2.0-2B")
    parser.add_argument("--index", type=int, default=0, help="Laptop record index in pipeline_results_compumarts.json (0-123)")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"], help="Device to run inference on")
    parser.add_argument("--max_tokens", type=int, default=1536, help="Max new tokens to generate")
    parser.add_argument("--model_id", type=str, default="numind/NuExtract-2.0-2B", help="HuggingFace model ID")
    args = parser.parse_args()

    results_file = "pipeline_results_compumarts.json"
    if not os.path.exists(results_file):
        print(f"Error: {results_file} not found.")
        sys.exit(1)

    with open(results_file, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    if args.index < 0 or args.index >= len(catalog):
        print(f"Error: index {args.index} out of range [0, {len(catalog) - 1}]")
        sys.exit(1)

    laptop = catalog[args.index]
    print("=" * 80)
    print(f"TARGET LAPTOP [{args.index}]: {laptop.get('title')}")
    print(f"STORE URL: {laptop.get('url')}")
    print("=" * 80)

    # 1. Build un-extracted raw text context
    raw_context = build_raw_context(laptop)
    print(f"\n[Raw Context Built]: {len(raw_context.splitlines())} lines, {len(raw_context)} characters")

    # 2. Build full prompt
    prompt = format_nuextract_prompt(LAPTOP_FULL_TEMPLATE, raw_context)

    # 3. Load model & tokenizer
    print(f"\n[Loading Model]: {args.model_id} on {args.device}...")
    t_load_start = time.time()
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)

    dtype = torch.float16 if args.device == "cuda" else torch.float32
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        args.model_id,
        torch_dtype=dtype,
        device_map=args.device,
    )
    t_load_sec = time.time() - t_load_start
    print(f"Model loaded in {t_load_sec:.2f}s")

    if args.device == "cuda":
        mem_allocated_mb = torch.cuda.memory_allocated() / (1024 * 1024)
        mem_reserved_mb = torch.cuda.memory_reserved() / (1024 * 1024)
        print(f"GPU VRAM in use: {mem_allocated_mb:.1f} MB (reserved: {mem_reserved_mb:.1f} MB)")

    # 4. Tokenize & generate
    print(f"\n[Running Direct Inference]: Generating up to {args.max_tokens} tokens...")
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    prompt_token_count = inputs.input_ids.shape[1]
    print(f"Input Prompt Length: {prompt_token_count} tokens")

    t_infer_start = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=args.max_tokens,
            temperature=0.0,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    t_infer_sec = time.time() - t_infer_start

    generated_tokens = outputs[0][prompt_token_count:]
    generated_token_count = len(generated_tokens)
    tokens_per_sec = generated_token_count / t_infer_sec if t_infer_sec > 0 else 0

    raw_response = tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

    print("=" * 80)
    print("INFERENCE BENCHMARK RESULTS:")
    print("=" * 80)
    print(f"  Total Inference Time:    {t_infer_sec:.2f} seconds")
    print(f"  Generated Tokens:        {generated_token_count} tokens")
    print(f"  Generation Speed:        {tokens_per_sec:.1f} tokens/sec")
    print("=" * 80)

    # 5. Parse JSON
    parsed_json = None
    try:
        # Strip potential markdown fences
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        parsed_json = json.loads(cleaned)
    except Exception as e:
        print(f"\n[Warning]: Failed to parse direct JSON output: {e}")
        print("\n[Raw Model Output]:\n", raw_response)

    if parsed_json:
        print("\n[Parsed NuExtract JSON Output]:")
        print(json.dumps(parsed_json, indent=2, ensure_ascii=False))

        # 6. Compare with stored pipeline specs (for non-CPU/non-GPU fields)
        print("\n" + "=" * 80)
        print("COMPARISON: NuExtract Direct vs Rule-Based Reference Specs")
        print("=" * 80)
        stored_specs = laptop.get("specs", {})
        for subsystem in LAPTOP_FULL_TEMPLATE.keys():
            print(f"\n--- Subsystem: {subsystem.upper()} ---")
            sub_nuextract = parsed_json.get(subsystem, {})
            sub_stored = stored_specs.get(subsystem, {})
            if isinstance(sub_nuextract, dict) and isinstance(sub_stored, dict):
                for field_name in LAPTOP_FULL_TEMPLATE[subsystem].keys():
                    val_nu = sub_nuextract.get(field_name)
                    val_ref = sub_stored.get(field_name)
                    match_flag = "MATCH" if str(val_nu) == str(val_ref) else "DIFF"
                    print(f"  {field_name:28s} | NuExtract: {str(val_nu):25s} | Reference: {str(val_ref):25s} | [{match_flag}]")


if __name__ == "__main__":
    main()

