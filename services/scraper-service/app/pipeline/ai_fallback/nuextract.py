"""NuExtract AI Fallback implementation using Transformers and ONNX Runtime.

Implements IAIFallbackExtractor using NuMind's NuExtract models (defaulting to
NuExtract-2.0-2B, with backward compatibility for NuExtract-v1.5 and NuExtract-2.0-4B)
optimized for structured JSON extraction on CUDA GPU and server CPU environments.
"""

from __future__ import annotations

import json
from app.common.logger import get_logger
import os
import re
from typing import Any
from collections.abc import Sequence

from app.pipeline.ai_fallback.base import IAIFallbackExtractor
from app.pipeline.schema import (
    ComponentEnvelope,
    ComponentEnvelopeResult,
    EnvelopeResult,
    ExtractionEnvelope,
)

logger = get_logger(__name__)


class NuExtractONNXFallbackExtractor(IAIFallbackExtractor):
    """Structured extraction fallback powered by numind/NuExtract models via Transformers / ONNX Runtime."""

    def __init__(
        self,
        model_id: str = "numind/NuExtract-2.0-2B",
        onnx_model_dir: str | None = None,
        execution_provider: str = "CPUExecutionProvider",
        max_new_tokens: int = 256,
        lazy_load: bool = True,
    ) -> None:
        self._model_id = model_id
        self._onnx_model_dir = onnx_model_dir
        self.execution_provider = execution_provider
        self.max_new_tokens = max_new_tokens

        self._genai_model: Any | None = None
        self._genai_tokenizer: Any | None = None
        self._hf_model: Any | None = None
        self._hf_tokenizer: Any | None = None
        self._backend: str = "uninitialized"

        if not lazy_load:
            self._ensure_loaded()

    @property
    def model_name(self) -> str:
        return f"{self._model_id} (onnx:{self._backend})"

    def _ensure_loaded(self) -> None:
        if self._genai_model is not None or self._hf_model is not None:
            return

        # 1. Try loading via onnxruntime-genai if onnx_model_dir is specified and exists
        if self._onnx_model_dir and os.path.isdir(self._onnx_model_dir):
            try:
                import onnxruntime_genai as og

                logger.info("Loading NuExtract ONNX GenAI model from: %s", self._onnx_model_dir)
                self._genai_model = og.Model(self._onnx_model_dir)
                self._genai_tokenizer = og.Tokenizer(self._genai_model)
                self._backend = "onnx-genai"
                logger.info("NuExtract ONNX GenAI model initialized successfully")
                return
            except Exception as e:
                logger.warning(
                    "Failed to initialize onnxruntime-genai model from %s: %s",
                    self._onnx_model_dir,
                    e,
                )

        # 2. Check for local ONNX cache or PyTorch transformers fallback
        try:
            import torch
            from transformers import AutoConfig, AutoTokenizer

            logger.info("Initializing NuExtract via Transformers: %s", self._model_id)
            self._hf_tokenizer = AutoTokenizer.from_pretrained(self._model_id, trust_remote_code=False)

            # Auto-detect vision-language architecture (Qwen2-VL / Qwen2.5-VL) vs CausalLM (Phi-3)
            try:
                cfg = AutoConfig.from_pretrained(self._model_id, trust_remote_code=False)
                is_vlm = getattr(cfg, "model_type", "") in ("qwen2_vl", "qwen2_5_vl")
            except Exception:
                is_vlm = "2.0" in self._model_id or "qwen" in self._model_id.lower()

            if is_vlm:
                from transformers import Qwen2VLForConditionalGeneration

                model_cls = Qwen2VLForConditionalGeneration
            else:
                from transformers import AutoModelForCausalLM

                model_cls = AutoModelForCausalLM

            device = (
                "cuda" if torch.cuda.is_available() and self.execution_provider != "CPUExecutionProvider" else "cpu"
            )
            model_kwargs: dict[str, Any] = {
                "low_cpu_mem_usage": True,
                "trust_remote_code": False,
            }

            if device == "cuda":
                total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                # 2B models require ~4.1 GB in FP16, which fits natively and at maximum accuracy on 6GB+ GPUs.
                # Use 4-bit quantization only when GPU VRAM < 6GB or for larger models (>3B).
                use_4bit = total_vram_gb < 5.5 or (not is_vlm and total_vram_gb <= 12.0)
                if use_4bit:
                    try:
                        from transformers import BitsAndBytesConfig

                        quantization_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_compute_dtype=torch.float16,
                            bnb_4bit_use_double_quant=True,
                        )
                        model_kwargs["quantization_config"] = quantization_config
                        model_kwargs["device_map"] = "auto"
                        logger.info("Enabling 4-bit NF4 quantization for GPU (%.1f GB VRAM detected)", total_vram_gb)
                    except Exception as q_err:
                        logger.warning(
                            "Could not enable bitsandbytes 4-bit quantization (%s). Falling back to float16.", q_err
                        )
                        model_kwargs["torch_dtype"] = torch.float16
                else:
                    model_kwargs["torch_dtype"] = torch.float16
                    model_kwargs["device_map"] = "auto"
                    logger.info(
                        "Using native float16 precision for %s on GPU (%.1f GB VRAM detected)",
                        self._model_id,
                        total_vram_gb,
                    )

                self._hf_model = model_cls.from_pretrained(
                    self._model_id,
                    **model_kwargs,
                )
                if "device_map" not in model_kwargs:
                    self._hf_model = self._hf_model.to(device)
            else:
                model_kwargs["torch_dtype"] = torch.float32
                self._hf_model = model_cls.from_pretrained(
                    self._model_id,
                    **model_kwargs,
                ).to("cpu")

            self._hf_model.eval()
            self._backend = f"transformers-{device}"
            logger.info("NuExtract model loaded on %s (%s)", device, model_cls.__name__)
        except Exception as e:
            logger.error("Could not load NuExtract model weights: %s", e)
            self._backend = "unavailable"
            raise e

    def health_check(self) -> bool:
        """Verify model weights or runtime backend can execute inference."""
        try:
            self._ensure_loaded()
            return self._genai_model is not None or self._hf_model is not None
        except Exception:
            return False

    @staticmethod
    def format_prompt(text: str, field_name: str, model_id: str | None = None) -> str:
        """Format input text and template into the official NuExtract prompt."""
        template = {field_name: None}
        template_str = json.dumps(template, indent=2)
        if model_id and ("2.0" in model_id or "qwen" in model_id.lower() or "nuextract3" in model_id.lower()):
            return (
                f"<|im_start|>user\n# Template:\n{template_str}\n# Context:\n{text}<|im_end|>\n<|im_start|>assistant\n"
            )
        return f"<|input|>\n### Template:\n{template_str}\n### Text:\n{text}\n\n<|output|>\n"

    def _generate_onnx_genai(self, prompt: str) -> str:
        """Run text generation using onnxruntime-genai with temperature=0.0."""
        import onnxruntime_genai as og

        input_tokens = self._genai_tokenizer.encode(prompt)
        params = og.GeneratorParams(self._genai_model)
        params.set_search_options(
            max_length=len(input_tokens) + self.max_new_tokens,
            temperature=0.0,
        )
        generator = og.Generator(self._genai_model, params)
        generator.append_tokens(input_tokens)

        while not generator.is_done():
            generator.generate_next_token()

        out_tokens = generator.get_sequence(0)
        full_text = self._genai_tokenizer.decode(out_tokens)
        if "<|output|>" in full_text:
            return full_text.split("<|output|>")[-1].strip()
        if "<|im_start|>assistant" in full_text:
            return full_text.split("<|im_start|>assistant")[-1].strip()
        return full_text.strip()

    def _generate_transformers(self, prompt: str) -> str:
        """Run greedy text generation using transformers with temperature=0.0."""
        import torch

        inputs = self._hf_tokenizer(prompt, return_tensors="pt").to(self._hf_model.device)
        input_len = inputs.input_ids.shape[1]
        with torch.no_grad():
            outputs = self._hf_model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                temperature=0.0,
                do_sample=False,
                pad_token_id=self._hf_tokenizer.eos_token_id,
            )
        generated_tokens = outputs[0][input_len:]
        return self._hf_tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

    @staticmethod
    def _parse_extracted_value(raw_output: str, field_name: str) -> Any | None:
        """Parse structured output emitted by NuExtract into target scalar value."""
        if not raw_output or not raw_output.strip():
            return None

        cleaned = raw_output.strip()
        # Strip markdown fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # 1. Attempt standard JSON parsing
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                if field_name in data and data[field_name] is not None:
                    return data[field_name]
                if "value" in data and data["value"] is not None:
                    return data["value"]
                for v in data.values():
                    if v is not None:
                        return v
            elif data is not None:
                return data
        except Exception:
            pass

        # 2. Fallback: extract the first valid JSON dict in text
        m_json = re.search(r"\{[^{}]*\}", cleaned)
        if m_json:
            try:
                data = json.loads(m_json.group(0))
                if isinstance(data, dict):
                    if field_name in data and data[field_name] is not None:
                        return data[field_name]
                    for v in data.values():
                        if v is not None:
                            return v
            except Exception:
                pass

        # 3. Fallback: regex search for key-value
        m_kv = re.search(
            r'"(?:' + re.escape(field_name) + r'|value)"\s*:\s*"([^"]+)"',
            cleaned,
            re.IGNORECASE,
        )
        if m_kv:
            return m_kv.group(1).strip()

        return None

    def extract_envelope(self, envelope: ExtractionEnvelope) -> EnvelopeResult:
        """Process a single field extraction envelope using NuExtract ONNX."""
        if not envelope.raw_context or not envelope.raw_context.strip():
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=None,
                confidence=0.0,
                model_name=self.model_name,
            )

        try:
            self._ensure_loaded()
        except Exception as e:
            logger.warning("NuExtract model not available for extraction: %s", e)
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=None,
                confidence=0.0,
                model_name=self.model_name,
            )

        f_name = envelope.field_path.split(".")[-1]
        prompt = self.format_prompt(text=envelope.raw_context, field_name=f_name, model_id=self._model_id)

        try:
            if self._genai_model is not None:
                raw_output = self._generate_onnx_genai(prompt)
            elif self._hf_model is not None:
                raw_output = self._generate_transformers(prompt)
            else:
                return EnvelopeResult(
                    field_path=envelope.field_path,
                    extracted_value=None,
                    confidence=0.0,
                    model_name=self.model_name,
                )

            val = self._parse_extracted_value(raw_output, field_name=f_name)
            conf = 0.9 if val is not None else 0.0
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=val,
                confidence=conf,
                model_name=self.model_name,
            )
        except Exception as e:
            logger.warning("NuExtract extraction failed for %s: %s", envelope.field_path, e)
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=None,
                confidence=0.0,
                model_name=self.model_name,
            )

    def batch_extract_envelopes(self, envelopes: Sequence[ExtractionEnvelope]) -> list[EnvelopeResult]:
        """Process a batch of envelopes sequentially."""
        return [self.extract_envelope(env) for env in envelopes]

    @staticmethod
    def format_component_prompt(envelope: ComponentEnvelope, model_id: str | None = None) -> str:
        """Format a ComponentEnvelope into official NuExtract hierarchical template prompt."""
        template = {envelope.component_name: envelope.sub_schema}
        template_str = json.dumps(template, indent=2)
        if model_id and ("2.0" in model_id or "qwen" in model_id.lower() or "nuextract3" in model_id.lower()):
            return f"<|im_start|>user\n# Template:\n{template_str}\n# Context:\n{envelope.raw_spec}<|im_end|>\n<|im_start|>assistant\n"
        return f"<|input|>\n### Template:\n{template_str}\n### Text:\n{envelope.raw_spec}\n\n<|output|>\n"

    @staticmethod
    def _parse_component_output(raw_output: str, component_name: str, locked_fields: set[str]) -> dict[str, Any]:
        """Safely parse NuExtract multi-field JSON output, rejecting modifications to locked fields."""
        if not raw_output or not raw_output.strip():
            return {}

        cleaned = raw_output.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        data = None
        try:
            data = json.loads(cleaned)
        except Exception:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    pass

        if not isinstance(data, dict):
            return {}

        comp_data = data.get(component_name, data)
        if not isinstance(comp_data, dict):
            comp_data = data

        extracted = {}
        for k, v in comp_data.items():
            # Crucial: Never overwrite locked Layer 4 fields!
            if k in locked_fields:
                continue
            if v is not None:
                extracted[k] = v

        return extracted

    def extract_component_envelope(self, envelope: ComponentEnvelope) -> ComponentEnvelopeResult:
        """Process a ComponentEnvelope using NuExtract native multi-field JSON generation."""
        if not envelope.raw_spec or not envelope.raw_spec.strip():
            return ComponentEnvelopeResult(
                component_name=envelope.component_name,
                extracted_fields={},
                model_name=self.model_name,
            )

        try:
            self._ensure_loaded()
        except Exception as e:
            logger.warning("NuExtract model not available: %s", e)
            return ComponentEnvelopeResult(
                component_name=envelope.component_name,
                extracted_fields={},
                model_name=self.model_name,
            )

        prompt = self.format_component_prompt(envelope, model_id=self._model_id)

        try:
            if self._genai_model is not None:
                raw_output = self._generate_onnx_genai(prompt)
            elif self._hf_model is not None:
                raw_output = self._generate_transformers(prompt)
            else:
                return ComponentEnvelopeResult(
                    component_name=envelope.component_name,
                    extracted_fields={},
                    model_name=self.model_name,
                )

            extracted = self._parse_component_output(raw_output, envelope.component_name, envelope.locked_fields)
            conf = 0.9 if extracted else 0.0
            return ComponentEnvelopeResult(
                component_name=envelope.component_name,
                extracted_fields=extracted,
                model_name=self.model_name,
                confidence=conf,
                raw_output=raw_output,
            )
        except Exception as e:
            logger.error("NuExtract component extraction error for %s: %s", envelope.component_name, e)
            return ComponentEnvelopeResult(
                component_name=envelope.component_name,
                extracted_fields={},
                model_name=self.model_name,
            )

    def batch_extract_component_envelopes(
        self, envelopes: Sequence[ComponentEnvelope]
    ) -> list[ComponentEnvelopeResult]:
        """Process a batch of component envelopes sequentially."""
        return [self.extract_component_envelope(env) for env in envelopes]


# Backward-compatible alias
NuExtractFallbackExtractor = NuExtractONNXFallbackExtractor
