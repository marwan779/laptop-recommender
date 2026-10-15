"""GLiNER AI Fallback implementation with ONNX Runtime acceleration.

Loads onnx-community/gliner_large-v2.1 using ONNX Runtime (int8 / fp16 / fp32)
to achieve ~35ms latency and low memory footprint.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

from pipeline.ai_fallback.base import IAIFallbackExtractor
from pipeline.schema import EnvelopeResult, ExtractionEnvelope

logger = logging.getLogger(__name__)

# Field path to specialized GLiNER prompt labels
FIELD_LABELS_MAP: Dict[str, List[str]] = {
    "gpu.vram_gb": ["vram capacity", "video memory", "gpu memory"],
    "gpu.model": ["graphics card", "gpu model", "nvidia geforce rtx"],
    "display.size_inches": ["screen size", "display size", "screen diagonal"],
    "display.refresh_rate_hz": ["refresh rate", "display refresh rate"],
    "display.panel_type": ["panel type", "display technology", "screen panel"],
    "power_battery.battery_capacity_wh": ["battery capacity", "battery watt hours", "wh capacity"],
    "power_battery.power_adapter_w": ["power adapter", "charger wattage", "ac adapter"],
    "memory.capacity_gb": ["ram capacity", "system memory"],
    "memory.memory_type": ["ram generation", "memory type", "ddr type"],
    "storage.capacity_gb": ["storage capacity", "ssd capacity", "hard drive capacity"],
    "physical.weight_kg": ["laptop weight", "weight"],
    "identity.laptop_family": ["laptop family", "product line", "sub-brand"],
    "identity.laptop_model": ["laptop model", "model name"],
    "identity.manufacturer_part_number": ["part number", "model number", "sku"],
}


class GLiNERONNXFallbackExtractor(IAIFallbackExtractor):
    """Zero-shot NER extractor powered by GLiNER and ONNX Runtime."""

    def __init__(
        self,
        model_id: str = "onnx-community/gliner_large-v2.1",
        load_onnx_model: bool = True,
        onnx_model_file: str = "onnx/model_int8.onnx",
        threshold: float = 0.4,
        lazy_load: bool = True,
    ) -> None:
        self._model_id = model_id
        self._load_onnx_model = load_onnx_model
        self._onnx_model_file = onnx_model_file
        self.threshold = threshold
        self._model = None
        
        if not lazy_load:
            self._ensure_loaded()

    @property
    def model_name(self) -> str:
        backend = "onnx" if self._load_onnx_model else "pytorch"
        return f"{self._model_id} ({backend}:{self._onnx_model_file})"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        from gliner import GLiNER

        logger.info("Initializing GLiNER model: %s (onnx=%s)", self._model_id, self._load_onnx_model)
        kwargs = {}
        if self._load_onnx_model:
            kwargs["load_onnx_model"] = True
            kwargs["onnx_model_file"] = self._onnx_model_file

            # Optimization: If downloading from onnx-community, download ONLY the requested ONNX file
            # and configs (~620MB) rather than the entire 5.5GB repository (all 7 precision formats)
            if "/" in self._model_id and not os.path.exists(self._model_id):
                try:
                    from huggingface_hub import snapshot_download
                    target_file = self._onnx_model_file or "onnx/model_int8.onnx"
                    logger.info("Fetching target ONNX checkpoint (%s) and configs...", target_file)
                    local_dir = snapshot_download(
                        repo_id=self._model_id,
                        allow_patterns=[target_file, "*.json", "README.md"],
                    )
                    self._model = GLiNER.from_pretrained(
                        local_dir,
                        load_onnx_model=True,
                        onnx_model_file=target_file,
                    )
                    return
                except Exception as e:
                    logger.warning("Targeted ONNX snapshot download failed (%s), falling back to standard loader...", e)

        self._model = GLiNER.from_pretrained(self._model_id, **kwargs)

    def health_check(self) -> bool:
        """Verify model can execute a basic inference pass."""
        try:
            self._ensure_loaded()
            test_res = self._model.predict_entities(
                "Display: 16-inch 165Hz IPS", ["screen size"], threshold=0.3
            )
            return isinstance(test_res, list)
        except Exception as e:
            logger.error("GLiNER health check failed: %s", e)
            return False

    def extract_envelope(self, envelope: ExtractionEnvelope) -> EnvelopeResult:
        """Extract a single unresolved field from its section context."""
        self._ensure_loaded()
        labels = FIELD_LABELS_MAP.get(envelope.field_path, [envelope.field_description])

        if not envelope.raw_context or not envelope.raw_context.strip():
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=None,
                confidence=0.0,
                model_name=self.model_name,
            )

        try:
            entities = self._model.predict_entities(
                envelope.raw_context, labels, threshold=self.threshold
            )
        except Exception as e:
            logger.warning("GLiNER prediction failed for %s: %s", envelope.field_path, e)
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=None,
                confidence=0.0,
                model_name=self.model_name,
            )

        if not entities:
            return EnvelopeResult(
                field_path=envelope.field_path,
                extracted_value=None,
                confidence=0.0,
                model_name=self.model_name,
            )

        # Pick top scoring entity
        best_entity = max(entities, key=lambda x: x.get("score", 0.0))
        span_text = best_entity.get("text", "")
        confidence = float(best_entity.get("score", 1.0))

        # Convert extracted text span to expected type
        parsed_value = self._parse_span_to_type(span_text, envelope)

        return EnvelopeResult(
            field_path=envelope.field_path,
            extracted_value=parsed_value,
            raw_span=span_text,
            confidence=confidence,
            model_name=self.model_name,
        )

    def batch_extract_envelopes(
        self, envelopes: Sequence[ExtractionEnvelope]
    ) -> List[EnvelopeResult]:
        """Process envelopes sequentially or in batches."""
        return [self.extract_envelope(env) for env in envelopes]

    def _parse_span_to_type(self, text: str, envelope: ExtractionEnvelope) -> Any:
        """Parse raw entity text span into canonical typed field value."""
        text_clean = text.strip()
        if not text_clean:
            return None

        exp_type = envelope.expected_type.lower()
        if "int" in exp_type:
            nums = re.findall(r"\d+", text_clean)
            if nums:
                return int(nums[0])
            return None
        elif "float" in exp_type:
            nums = re.findall(r"\d+(?:\.\d+)?", text_clean)
            if nums:
                return float(nums[0])
            return None
        elif "str" in exp_type:
            if envelope.allowed_values:
                for cand in envelope.allowed_values:
                    if cand.lower() in text_clean.lower():
                        return cand
            return text_clean
        elif "bool" in exp_type:
            return any(pos in text_clean.lower() for pos in ["yes", "true", "supported"])

        return text_clean

