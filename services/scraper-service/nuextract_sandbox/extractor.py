import os
import json
import re
import time
from typing import Any
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

os.environ.pop("HF_HUB_OFFLINE", None)

TARGET_SCHEMA = {
    "identity": {
        "brand": None,
        "laptop_family": None,
        "laptop_model": None,
        "manufacturer_part_number": None,
    },
    "cpu": {
        "manufacturer": None,
        "line": None,
        "model": None,
        "cores": None,
        "threads": None,
        "clock_speed": None,
        "cache_mb": None,
    },
    "gpu": {
        "manufacturer": None,
        "model": None,
        "vram_gb": None,
        "tdp_w": None,
        "integrated": None,
    },
    "memory": {
        "capacity_gb": None,
        "memory_type": None,
        "speed": None,
        "slot_count": None,
        "max_supported_gb": None,
    },
    "storage": {
        "capacity_gb": None,
        "storage_type": None,
        "interface": None,
        "form_factor": None,
        "slot_count": None,
    },
    "display": {
        "size_inches": None,
        "resolution": None,
        "refresh_rate_hz": None,
        "panel_type": None,
        "aspect_ratio": None,
        "touchscreen": None,
    },
    "power_battery": {
        "battery_capacity_wh": None,
        "power_adapter_w": None,
        "battery_cells": None,
    },
    "physical": {
        "weight_kg": None,
        "color": None,
        "width_mm": None,
        "depth_mm": None,
        "height_mm": None,
    },
    "build_security": {
        "has_backlit_keyboard": None,
        "has_fingerprint": None,
    },
    "audio_webcam": {
        "speaker_count": None,
        "microphone": None,
        "webcam_resolution": None,
    },
    "operating_system": {
        "name": None,
    },
    "connectivity": {
        "wifi": None,
        "bluetooth": None,
        "ethernet": None,
        "ports": [],
    },
}

class NuExtractor:
    """Layer 3: Generative schema-driven information extraction via NuExtract."""

    def __init__(self, model_name: str = "numind/NuExtract-v1.5", device: str | None = None):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Loading {self.model_name} on {self.device}...")
        t0 = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            dtype=torch.bfloat16 if self.device == "cpu" else torch.float16,
            low_cpu_mem_usage=True,
            trust_remote_code=False,
        )
        self.model.to(self.device)
        self.model.eval()
        print(f"Model loaded in {time.time() - t0:.2f}s")

    def _build_prompt(self, text: str, template_dict: dict[str, Any]) -> str:
        """Format input text and template into the official NuExtract prompt."""
        template_str = json.dumps(template_dict, indent=2)
        return f"""<|input|>\n### Template:\n{template_str}\n### Text:\n{text}\n<|output|>\n"""

    def extract(self, text: str, template: dict[str, Any] | None = None) -> tuple[dict[str, Any], float]:
        """Extract structured JSON from text according to the template."""
        target_template = template or TARGET_SCHEMA
        prompt = self._build_prompt(text, target_template)

        t0 = time.time()
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        input_token_count = inputs.input_ids.shape[1]

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=1500,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        gen_tokens = outputs[0][input_token_count:]
        raw_output = self.tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()
        latency_s = time.time() - t0

        # Parse JSON
        parsed = self._clean_and_parse_json(raw_output)
        return parsed, latency_s

    def _clean_and_parse_json(self, raw_str: str) -> dict[str, Any]:
        """Parse raw model string into valid dictionary, with fallback cleanup."""
        # 1. Direct parse
        try:
            return json.loads(raw_str)
        except json.JSONDecodeError:
            pass

        # 2. Extract markdown codeblock
        m_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_str)
        if m_block:
            try:
                return json.loads(m_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. Find outermost braces
        start = raw_str.find("{")
        end = raw_str.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw_str[start : end + 1])
            except json.JSONDecodeError:
                pass

        print(f"[Warning] Failed to decode JSON from NuExtract output:\n{raw_str[:300]}...")
        return {"raw_output": raw_str, "error": "json_decode_failed"}

    def extract_area_by_area(self, area_blocks: dict[str, str]) -> tuple[dict[str, Any], float]:
        """Extract each component area independently with its isolated context block and schema template."""
        structured: dict[str, Any] = {}
        total_time = 0.0

        for area, template in TARGET_SCHEMA.items():
            context_text = area_blocks.get(area, "")
            if not context_text:
                structured[area] = template
                continue

            print(f"  -> Extracting area [{area}]...")
            t0 = time.time()
            prompt = self._build_prompt(context_text, {area: template})
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            input_token_count = inputs.input_ids.shape[1]

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=350,
                    do_sample=False,
                    pad_token_id=self.tokenizer.eos_token_id,
                )

            gen_tokens = outputs[0][input_token_count:]
            raw_output = self.tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()
            elapsed = time.time() - t0
            total_time += elapsed

            parsed = self._clean_and_parse_json(raw_output)
            # Unpack {area: {...}} or direct {...}
            if isinstance(parsed, dict):
                if area in parsed and isinstance(parsed[area], dict):
                    structured[area] = parsed[area]
                else:
                    structured[area] = parsed
            else:
                structured[area] = template

            print(f"     done in {elapsed:.2f}s")

        return structured, total_time


