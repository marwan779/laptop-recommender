"""Envelope Prompt Normalizer Layer.

Acts as a pre-AI prompt adapter that intercepts ComponentEnvelopes before they reach
Layer 6 (NuExtract-2.0-2B).

Strictly scopes to 'storage' and 'memory' envelopes only.
Uses non-destructive semantic annotation: detects colloquial hardware idioms
(e.g., "1TB SSD (Extra M.2 Slot Available)" or "8GB Soldered + 8GB SO-DIMM")
and appends an explicit [Hardware Summary] to the raw context so that extractive
models can extract accurate integer counts and boolean flags without arithmetic errors.
"""

from __future__ import annotations

import copy
import logging
import re

from pipeline.schema import ComponentEnvelope

logger = logging.getLogger("envelope_normalizer")


class EnvelopePromptNormalizer:
    """Pre-processes storage and memory envelopes to clarify hardware structures for LLM extraction."""

    def normalize_envelope(self, envelope: ComponentEnvelope) -> ComponentEnvelope:
        """Inspect and conditionally annotate an envelope's raw_spec before AI inference."""
        if envelope.component_name not in ("storage", "memory"):
            return envelope

        raw_spec = envelope.raw_spec or ""
        if not raw_spec.strip():
            return envelope

        if envelope.component_name == "storage":
            enhanced_spec = self._normalize_storage(raw_spec, envelope)
        elif envelope.component_name == "memory":
            enhanced_spec = self._normalize_memory(raw_spec, envelope)
        else:
            enhanced_spec = raw_spec

        if enhanced_spec != raw_spec:
            new_env = copy.copy(envelope)
            new_env.raw_spec = enhanced_spec
            return new_env

        return envelope

    def _normalize_storage(self, raw_spec: str, envelope: ComponentEnvelope) -> str:
        """Analyze storage context and append standardized structural summary."""
        annotations = []
        text_lower = raw_spec.lower()

        # Check if slot_count is an unresolved target
        unresolved = [k for k, v in envelope.sub_schema.items() if v is None]
        needs_slots = "slot_count" in unresolved
        needs_max = "max_supported_gb" in unresolved

        if needs_slots:
            # 1. Compound multi-slot pattern: "1x ... slot and 1x ... slot" or "1x ... slot, 1x ... slot"
            m_and_slots = re.findall(
                r"\b1\s*[xX×]?\s*(?:pcie|m\.2|nvme|sata)[^,\n;]*?slot",
                text_lower,
                re.IGNORECASE,
            )
            if len(m_and_slots) >= 2:
                annotations.append(
                    f"Total physical storage slots: {len(m_and_slots)} ({len(m_and_slots)} separate drive slots)."
                )
            # 2. Additive Expansion Pattern: installed drive + extra / expansion / secondary slot
            elif re.search(
                r"\b(?:extra\s+(?:m\.2|slot|bay)|second\s+m\.2|plus\s+1x|additional\s+(?:m\.2|storage|slot)|with\s+an\s+extra|expansion\s+slot|free\s+m\.2\s+slot|extra\s+m\.2\s+2230\s+slot)\b",
                text_lower,
                re.I,
            ):
                # Verify that a primary drive is also installed or mentioned
                has_installed = bool(re.search(r"\b(?:\d+\s*tb|\d{3,4}\s*gb|ssd|nvme|pcie)\b", text_lower, re.I))
                if has_installed:
                    annotations.append(
                        "Total physical storage slots: 2 (1 primary installed drive + 1 extra expansion slot/bay available)."
                    )
            # 3. Explicit Multi-Slot count: "2x M.2 slots" / "two M.2 slots" / "2 M.2 slots"
            elif re.search(r"\b(?:2x\s*m\.2|two\s+m\.2|2\s*(?:m\.2\s*)?slots?)\b", text_lower, re.I):
                annotations.append("Total physical storage slots: 2.")
            # 4. Explicit Single Slot only
            elif re.search(
                r"\b(?:only\s+one\s+m\.2|single\s+m\.2|one\s+m\.2\s+slot|no\s+expansion\s+slot)\b", text_lower, re.I
            ):
                annotations.append("Total physical storage slots: 1 (single slot only, no expansion).")

        if needs_max:
            # Maximum storage ceiling: e.g. "Up to 2TB" or "Up to 4TB"
            m_max_tb = re.search(
                r"\b(?:up\s+to|supports\s+up\s+to|expandable\s+up\s+to)\s*([1-8])\s*tb\b", text_lower, re.I
            )
            if m_max_tb:
                cap_gb = int(m_max_tb.group(1)) * 1024
                annotations.append(f"Maximum supported storage capacity: {cap_gb} GB.")
            else:
                m_max_gb = re.search(
                    r"\b(?:up\s+to|supports\s+up\s+to|expandable\s+up\s+to)\s*(\d{3,4})\s*gb\b", text_lower, re.I
                )
                if m_max_gb:
                    cap_gb = int(m_max_gb.group(1))
                    annotations.append(f"Maximum supported storage capacity: {cap_gb} GB.")

        if annotations:
            summary_block = f"\n[Storage Summary: {' '.join(annotations)}]"
            return raw_spec + summary_block

        return raw_spec

    def _normalize_memory(self, raw_spec: str, envelope: ComponentEnvelope) -> str:
        """Analyze memory context and append standardized structural summary."""
        annotations = []
        text_lower = raw_spec.lower()

        unresolved = [k for k, v in envelope.sub_schema.items() if v is None]
        needs_slots = "slot_count" in unresolved
        needs_soldered = "is_soldered" in unresolved
        needs_max = "max_supported_gb" in unresolved

        # 1. Hybrid Soldered + SO-DIMM configuration
        is_hybrid = bool(
            re.search(
                r"(?:soldered|onboard).*?(?:so-?dimm|slot)|(?:so-?dimm|slot).*?(?:soldered|onboard)",
                text_lower,
                re.I,
            )
        )
        if is_hybrid:
            if needs_slots:
                annotations.append("Total memory expansion slots: 1 SO-DIMM slot.")
            if needs_soldered:
                annotations.append("Soldered memory: true (hybrid onboard + SO-DIMM slot).")
        else:
            # 2. 100% Soldered / On-board memory (LPDDR / non-upgradable)
            is_pure_soldered = bool(
                re.search(
                    r"\b(?:lpddr[45]x?|unified\s+memory|soldered\s+memory|on-?board\s+memory|non-?upgradable|memory\s+is\s+soldered)\b",
                    text_lower,
                    re.I,
                )
            )
            if is_pure_soldered:
                if needs_slots:
                    annotations.append("Total memory expansion slots: 0 (100% soldered on-board).")
                if needs_soldered:
                    annotations.append("Soldered memory: true.")
            else:
                # 3. Dual SO-DIMM discrete slots: e.g. "2x SO-DIMM" or "(2x 8GB)" or "(2 x 16GB)"
                is_dual_sodimm = bool(
                    re.search(
                        r"\b(?:2\s*[xX×]\s*(?:so-?dimm|sodimm|slots?)|two\s+(?:so-?dimm|sodimm)\s*slots?|\(\s*2\s*[xX×]\s*\d+\s*gb\s*\))\b",
                        text_lower,
                        re.I,
                    )
                )
                if is_dual_sodimm:
                    if needs_slots:
                        annotations.append("Total memory slots: 2 discrete SO-DIMM sockets.")
                    if needs_soldered:
                        annotations.append("Soldered memory: false.")
                else:
                    # Single SO-DIMM slot
                    is_single_sodimm = bool(
                        re.search(
                            r"\b(?:1\s*[xX×]\s*so-?dimm|one\s+so-?dimm\s*slot)\b",
                            text_lower,
                            re.I,
                        )
                    )
                    if is_single_sodimm:
                        if needs_slots:
                            annotations.append("Total memory slots: 1 SO-DIMM socket.")
                        if needs_soldered:
                            annotations.append("Soldered memory: false.")

        # Maximum Supported RAM
        if needs_max:
            m_max_ram = re.search(
                r"\b(?:up\s+to|supports\s+up\s+to|expandable\s+up\s+to|maximum\s+(?:supported\s+)?memory:?\s*(?:up\s+to\s*)?)\s*(\d{2,3})\s*gb\b",
                text_lower,
                re.I,
            )
            if m_max_ram:
                max_gb = int(m_max_ram.group(1))
                annotations.append(f"Maximum supported memory: {max_gb} GB.")

        if annotations:
            summary_block = f"\n[Memory Summary: {' '.join(annotations)}]"
            return raw_spec + summary_block

        return raw_spec
