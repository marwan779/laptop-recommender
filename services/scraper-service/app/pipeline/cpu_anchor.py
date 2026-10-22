"""Layer 3: CPU Anchor Extraction Layer.

Uses the ground-truth CPU_SPECS dictionary to identify the exact CPU SKU,
populate canonical CPU specifications, and provide hardware constraints
(supported memory types, maximum memory capacity, TDP, integrated GPU)
for downstream deterministic extraction and physical validation.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from app.pipeline.data.cpu_specs import CPU_SPECS, CPUSpecEntry
except ImportError:
    from app.pipeline.data.cpu_specs import CPU_SPECS, CPUSpecEntry


class CPUAnchorExtractor:
    """Extracts and populates CPU specifications using CPU_SPECS as ground truth."""

    def __init__(self, specs_db: dict[str, CPUSpecEntry] | None = None) -> None:
        self.specs_db: dict[str, CPUSpecEntry] = specs_db or CPU_SPECS
        self._compiled_aliases: list[tuple[str, re.Pattern, CPUSpecEntry]] = []
        self._build_index()

    def _build_index(self) -> None:
        """Compile regex patterns for model names and aliases sorted by specificity."""
        entries = []
        for key, entry in self.specs_db.items():
            candidates = [entry["model"].lower()] + [a.lower() for a in entry.get("aliases", [])]
            # De-duplicate while preserving order
            seen = set()
            for cand in candidates:
                cand_clean = cand.strip()
                if cand_clean and cand_clean not in seen:
                    seen.add(cand_clean)
                    # Escape special regex chars, ensure word boundaries
                    pattern_str = r"(?<![a-zA-Z0-9])" + re.escape(cand_clean) + r"(?![a-zA-Z0-9])"
                    pattern = re.compile(pattern_str, re.IGNORECASE)
                    entries.append((len(cand_clean), key, pattern, entry))

        # Sort by length descending so longer/more specific aliases match first (e.g. 13620H before 620)
        entries.sort(key=lambda x: x[0], reverse=True)
        self._compiled_aliases = [(key, pat, entry) for _, key, pat, entry in entries]

    def match(
        self,
        title: str,
        spec_texts: list[str] | None = None,
    ) -> tuple[str, CPUSpecEntry] | None:
        """Match the CPU SKU from the product title and specification texts.

        Returns:
            Tuple of (cpu_key, cpu_entry) or None if no match found.
        """
        search_targets = [title] + (spec_texts or [])
        combined_text = " ".join([t for t in search_targets if t])

        for key, pattern, entry in self._compiled_aliases:
            if pattern.search(combined_text):
                return key, entry

        return None

    def populate_cpu_specs(self, entry: CPUSpecEntry) -> dict[str, Any]:
        """Populate the canonical structured CPU specification fields from ground truth."""
        return {
            "manufacturer": entry["brand"],
            "line": entry["family"],
            "model": entry["model"],
            "series": entry.get("generation"),
            "full_name": f"{entry['brand']} {entry['model']}",
            "cores": entry["total_cores"],
            "threads": entry["total_threads"],
            "clock_base_ghz": entry.get("base_clock_ghz"),
            "clock_boost_ghz": entry.get("boost_clock_ghz"),
            "cache_mb": entry.get("cache_mb"),
            "microarchitecture": entry["microarchitecture"],
            "microarchitecture_code": entry.get("microarchitecture_code"),
            "low_power_cores": entry.get("low_power_cores"),
            "performance_cores": entry.get("performance_cores"),
            "efficient_cores": entry.get("efficient_cores"),
            "npu_tops": entry.get("npu_tops"),
            "base_power_w": entry.get("base_power_w"),
            "raw_spec": None,
        }

    def get_hardware_constraints(self, entry: CPUSpecEntry) -> dict[str, Any]:
        """Extract hardware boundaries used to validate memory, power, and GPU."""
        return {
            "cpu_key": entry["model"].lower().replace(" ", "_"),
            "supported_memory": entry.get("supported_memory", []),
            "max_memory_gb": entry.get("max_memory_gb"),
            "base_power_w": entry.get("base_power_w"),
            "integrated_gpu": entry.get("integrated_gpu"),
            "npu_tops": entry.get("npu_tops"),
        }

    def extract(
        self,
        title: str,
        spec_texts: list[str] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
        """Perform full CPU identification and constraint extraction.

        Returns:
            (canonical_cpu_dict, hardware_constraints_dict, matched_key)
        """
        match_result = self.match(title, spec_texts)
        if not match_result:
            return None, None, None

        key, entry = match_result
        return self.populate_cpu_specs(entry), self.get_hardware_constraints(entry), key
