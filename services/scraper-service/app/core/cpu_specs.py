"""CPU Specifications interface proxy.
Re-exports canonical CPU_SPECS and helper functions from root cpu_specs module.
"""

from cpu_specs import (
    CPU_SPECS,
    CPU_ALIASES,
    AMBIGUOUS_CPU_TOKENS,
    clean_cpu_string,
    normalize_cpu_name,
    lookup_cpu,
    enrich_cpu_specs,
    get_cpu_summary_stats,
)

__all__ = [
    "CPU_SPECS",
    "CPU_ALIASES",
    "AMBIGUOUS_CPU_TOKENS",
    "clean_cpu_string",
    "normalize_cpu_name",
    "lookup_cpu",
    "enrich_cpu_specs",
    "get_cpu_summary_stats",
]

