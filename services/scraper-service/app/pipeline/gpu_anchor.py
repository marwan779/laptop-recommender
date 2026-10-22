"""Layer 3.5: GPU Anchor Extraction Layer.

Uses the ground-truth GPU_SPECS dictionary to identify the exact GPU SKU,
populate canonical GPU specifications, and enforce physical hardware constraints
and strict TDP handling rules.

TDP Handling Protocol:
- Unlike CPU base power (which is fixed silicon spec), laptop GPU TDP is OEM-configurable
  per chassis (e.g., RTX 4050 configured between 35W and 140W).
- Store Provided TDP: If the retailer/PDP specifies the actual TGP/TDP (e.g., 105W or 140W),
  we extract it, validate that min_w <= tdp_w <= max_w, and preserve the store's configured value.
- Store Absent TDP: If the store does NOT specify TDP, we keep tdp_w = None and do NOT
  generate an AI fallback envelope or invent a default.
"""

from __future__ import annotations

import re
from typing import Any

from app.pipeline.data.gpu_specs import GPU_SPECS


class GPUAnchorExtractor:
    """Extracts and populates GPU specifications using GPU_SPECS as ground truth."""

    def __init__(self, specs_db: dict[str, dict] | None = None) -> None:
        self.specs_db: dict[str, dict] = specs_db or GPU_SPECS
        self._discrete_patterns: list[tuple[str, re.Pattern, dict]] = []
        self._integrated_patterns: list[tuple[str, re.Pattern, dict]] = []
        self._build_index()

    def _build_index(self) -> None:
        """Compile regex patterns for model names and aliases sorted by specificity."""
        discrete_entries = []
        integrated_entries = []
        for key, entry in self.specs_db.items():
            candidates = [entry["model"].lower()] + [p.lower() for p in entry.get("match_patterns", [])]
            seen = set()
            is_int = entry.get("integrated", False)
            for cand in candidates:
                cand_clean = cand.strip()
                if cand_clean and cand_clean not in seen:
                    seen.add(cand_clean)
                    pattern_str = r"(?<![a-zA-Z0-9])" + re.escape(cand_clean) + r"(?![a-zA-Z0-9])"
                    pattern = re.compile(pattern_str, re.IGNORECASE)
                    target_list = integrated_entries if is_int else discrete_entries
                    target_list.append((len(cand_clean), key, pattern, entry))

        # Sort by length descending so longer/more specific aliases match first
        # (e.g. 'rtx 3050 6gb' before 'rtx 3050', 'rtx 4070 ti' before 'rtx 4070')
        discrete_entries.sort(key=lambda x: x[0], reverse=True)
        integrated_entries.sort(key=lambda x: x[0], reverse=True)
        self._discrete_patterns = [(key, pat, entry) for _, key, pat, entry in discrete_entries]
        self._integrated_patterns = [(key, pat, entry) for _, key, pat, entry in integrated_entries]
        self._compiled_patterns = self._discrete_patterns + self._integrated_patterns

    def match(
        self,
        title: str,
        spec_texts: list[str] | None = None,
        cpu_context: dict[str, Any] | None = None,
    ) -> tuple[str, dict] | None:
        """Match the GPU SKU from product title and specification texts.

        Discrete GPUs are ALWAYS searched and prioritized first so dedicated gaming/creator
        GPUs (e.g. RTX 4050) are never masked by CPU integrated graphics (e.g. Intel UHD Graphics).
        Supports VRAM disambiguation for SKUs with multiple capacities (e.g. RTX 3050 4GB vs 6GB)
        and integrated GPU resolution via CPU context.
        """
        search_targets = [title] + (spec_texts or [])
        combined_text = " ".join([t for t in search_targets if t])

        # 1. First pass: Search discrete GPUs across title and specs
        matched: tuple[str, dict] | None = None
        for key, pattern, entry in self._discrete_patterns:
            if pattern.search(combined_text):
                matched = (key, entry)
                break

        # 2. VRAM Disambiguation for discrete GPUs
        if matched:
            key, entry = matched
            base_model = entry.get("model")
            if base_model and not entry.get("integrated"):
                # Search for explicit VRAM in text (e.g. "6GB", "4GB", "8GB", "16GB")
                vram_match = re.search(r"\b([12468]|12|16|24)\s*gb\b", combined_text, re.IGNORECASE)
                if vram_match:
                    extracted_vram = int(vram_match.group(1))
                    if extracted_vram != entry.get("vram_gb"):
                        # Look for alternate SKU with matching model and vram_gb
                        for alt_key, alt_entry in self.specs_db.items():
                            if alt_entry.get("model") == base_model and alt_entry.get("vram_gb") == extracted_vram:
                                return alt_key, alt_entry
            return key, entry

        # 3. Second pass: If NO discrete GPU matched, search integrated GPUs
        for key, pattern, entry in self._integrated_patterns:
            if pattern.search(combined_text):
                return key, entry

        # 4. If still not matched, check CPU context for integrated GPU
        if cpu_context and cpu_context.get("integrated_gpu"):
            igpu_name = cpu_context["integrated_gpu"]
            igpu_lower = igpu_name.lower()
            for key, pattern, entry in self._integrated_patterns:
                if pattern.search(igpu_lower):
                    return key, entry

        return None

    def validate_tdp(self, cand_w: int, entry: dict) -> tuple[bool, int | None, str | None]:
        """Validate a candidate TDP/TGP against the GPU's physical silicon envelope.

        Returns:
            (is_valid, validated_tdp_w, rejection_reason)
        """
        if entry.get("integrated"):
            return False, None, f"Integrated GPU '{entry.get('model')}' has no dedicated TDP"

        tdp_limits = entry.get("tdp_limits")
        if not tdp_limits:
            return True, cand_w, None

        min_w = tdp_limits.get("min_w", 20)
        max_w = tdp_limits.get("max_w", 200)

        if min_w <= cand_w <= max_w:
            return True, cand_w, None

        return (
            False,
            None,
            f"TDP {cand_w}W outside physical limits [{min_w}W, {max_w}W] for {entry.get('model')}",
        )

    def extract_tdp(self, text: str, entry: dict) -> int | None:
        """Extract and validate store-provided TGP/TDP from text.

        Strict Rule:
        - If the store provides an explicit TGP (e.g., 'TGP 105W', '140W TGP'),
          we extract and validate it against the physical envelope.
        - If the store does NOT provide TGP, we return None. We NEVER fallback
          or default to silicon bounds.
        """
        if entry.get("integrated"):
            return None

        # Pattern 1: TGP/TDP XX W or TGP: XXW or TGP up to XXW or Max TGP
        m1 = re.search(
            r"\b(?:max(?:imum)?\s*)?(?:tgp|tdp)\s*(?:up\s*to\s*)?[:=]?\s*(\d{2,3})\s*w\b", text, re.IGNORECASE
        )
        if m1:
            cand = int(m1.group(1))
            valid, clean_w, _ = self.validate_tdp(cand, entry)
            if valid:
                return clean_w

        # Pattern 2: XX W TGP/TDP or XX W Max TGP
        m2 = re.search(r"\b(\d{2,3})\s*w\s*(?:max(?:imum)?\s*)?(?:tgp|tdp)\b", text, re.IGNORECASE)
        if m2:
            cand = int(m2.group(1))
            valid, clean_w, _ = self.validate_tdp(cand, entry)
            if valid:
                return clean_w

        # Pattern 3: Maximum Graphics Power / Graphics Power XX W
        m3 = re.search(
            r"\b(?:maximum\s*graphics\s*power|graphics\s*power|gpu\s*power)\s*[:=]?\s*(\d{2,3})\s*w\b",
            text,
            re.IGNORECASE,
        )
        if m3:
            cand = int(m3.group(1))
            valid, clean_w, _ = self.validate_tdp(cand, entry)
            if valid:
                return clean_w

        return None

    def extract_boost_clock(self, text: str) -> int | None:
        """Extract GPU boost clock in MHz if explicitly published."""
        m = re.search(r"\b([12]\d{3})\s*mhzx?\b", text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1000 <= val <= 3000:
                return val
        return None

    def populate_gpu_specs(
        self,
        entry: dict,
        raw_tdp: int | None = None,
        raw_boost: int | None = None,
    ) -> dict[str, Any]:
        """Populate canonical structured GPU specification fields from ground truth.

        Strict TDP Rule:
        - If raw_tdp was explicitly provided by the store and valid, it is preserved.
        - If raw_tdp was absent, tdp_w remains None.
        """
        tdp_w = None
        if raw_tdp is not None and not entry.get("integrated"):
            valid, clean_w, _ = self.validate_tdp(raw_tdp, entry)
            if valid:
                tdp_w = clean_w

        return {
            "manufacturer": entry["manufacturer"],
            "model": entry["model"],
            "variant": entry.get("variant"),
            "vram_gb": entry.get("vram_gb"),
            "tdp_w": tdp_w,
            "boost_clock_mhz": raw_boost,
            "ai_tops": entry.get("ai_tops"),
            "integrated": entry.get("integrated", False),
            "raw_spec": None,
        }

    def get_hardware_constraints(self, entry: dict) -> dict[str, Any]:
        """Extract hardware boundaries and capabilities used downstream."""
        return {
            "gpu_key": entry.get("model", "").lower().replace(" ", "_"),
            "manufacturer": entry.get("manufacturer"),
            "model": entry.get("model"),
            "series": entry.get("series"),
            "variant": entry.get("variant"),
            "chip_codename": entry.get("chip_codename"),
            "architecture": entry.get("architecture"),
            "process_node_nm": entry.get("process_node_nm"),
            "integrated": entry.get("integrated", False),
            "vram_gb": entry.get("vram_gb"),
            "memory_type": entry.get("memory_type"),
            "bus_width_bits": entry.get("bus_width_bits"),
            "memory_speed_gbps": entry.get("memory_speed_gbps"),
            "cuda_cores": entry.get("cuda_cores"),
            "tensor_cores": entry.get("tensor_cores"),
            "rt_cores": entry.get("rt_cores"),
            "ai_tops": entry.get("ai_tops"),
            "tdp_limits": entry.get("tdp_limits"),
            "features": entry.get("features", {}),
        }

    def extract(
        self,
        title: str,
        spec_texts: list[str] | None = None,
        raw_tgp_text: str | None = None,
        cpu_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
        """Perform full GPU identification, TDP bounds validation, and constraint extraction.

        Returns:
            (canonical_gpu_dict, hardware_constraints_dict, matched_key)
        """
        match_result = self.match(title, spec_texts, cpu_context=cpu_context)
        if not match_result:
            return None, None, None

        key, entry = match_result
        all_text = " ".join([title] + (spec_texts or []) + ([raw_tgp_text] if raw_tgp_text else []))

        # Check for store-provided TGP
        raw_tdp = self.extract_tdp(all_text, entry)

        # Check for store-provided boost clock
        raw_boost = self.extract_boost_clock(all_text)

        return (
            self.populate_gpu_specs(entry, raw_tdp=raw_tdp, raw_boost=raw_boost),
            self.get_hardware_constraints(entry),
            key,
        )
