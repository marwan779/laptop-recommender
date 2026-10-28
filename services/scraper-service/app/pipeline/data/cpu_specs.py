"""Canonical CPU specification schema, database loader, and matching helpers.

Defines:
- CoreClusterSpec: TypedDict for CPU performance and efficient core clusters.
- CPURawBenchmarks: TypedDict for raw synthetic benchmark scores.
- CPUNormalizedScores: TypedDict for normalized 0-100 persona ratings.
- CPUSpecEntry: Full TypedDict schema for CPU ground-truth silicon specifications.
- CPU_SPECS: Pre-loaded dictionary of all canonical CPU specifications loaded from cpu_specs.json.
- Matching and lookup helpers.
"""

import json
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

BrandType = Literal["Intel", "AMD", "Apple", "Qualcomm"]


class CoreClusterSpec(TypedDict):
    count: int
    base_clock_ghz: float | None
    boost_clock_ghz: float | None


class CPURawBenchmarks(TypedDict, total=False):
    geekbench6_single: int | None
    geekbench6_multi: int | None
    cinebench_r23_single: int | None
    cinebench_r23_multi: int | None
    passmark_cpu_mark: int | None


class CPUNormalizedScores(TypedDict, total=False):
    single_core_rating: float | None
    multi_core_rating: float | None
    efficiency_rating: float | None


class CPUSpecEntry(TypedDict):
    brand: BrandType
    model: str
    family: str
    generation: str | None
    microarchitecture: str
    microarchitecture_code: str | None
    total_cores: int
    performance_cores: CoreClusterSpec | None
    super_cores: NotRequired[CoreClusterSpec]
    efficient_cores: CoreClusterSpec | None
    low_power_cores: int | None
    total_threads: int
    base_clock_ghz: float | None
    boost_clock_ghz: float | None
    cache_mb: int | None  # L3 only; Intel Smart Cache is the equivalent metric.
    integrated_gpu: str | None
    npu_tops: float | None
    base_power_w: int | None
    supported_memory: list[str]
    max_memory_gb: int | None
    aliases: list[str]
    source_url: str
    max_memory_gb_by_type: NotRequired[dict[str, int]]
    raw_benchmarks: NotRequired[CPURawBenchmarks]
    normalized_scores: NotRequired[CPUNormalizedScores]


def load_cpu_specs() -> dict[str, CPUSpecEntry]:
    """Load canonical CPU specifications dictionary from json file."""
    candidates = [
        Path(__file__).parent / "cpu_specs.json",
        Path(__file__).parent / "pipeline" / "data" / "cpu_specs.json",
        Path(__file__).resolve().parent / "pipeline" / "data" / "cpu_specs.json",
        Path(__file__).parent / "data" / "cpu_specs.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"Could not locate cpu_specs.json in candidates: {candidates}")


CPU_SPECS: dict[str, CPUSpecEntry] = load_cpu_specs()


# --- Validation and Schema Consistency Integrity Checks ---
assert len(CPU_SPECS) == 84, f"Expected 84 CPU records, got {len(CPU_SPECS)}"
_required_cpu_fields = set(CPUSpecEntry.__required_keys__)
_optional_cpu_fields = set(CPUSpecEntry.__optional_keys__)

for _cpu_name, _cpu in CPU_SPECS.items():
    assert _required_cpu_fields <= set(_cpu) <= _required_cpu_fields | _optional_cpu_fields, (
        f"{_cpu_name} does not match CPUSpecEntry"
    )

    _core_clusters = [
        _cpu.get("performance_cores"),
        _cpu.get("super_cores"),
        _cpu.get("efficient_cores"),
    ]
    _core_clusters = [cluster for cluster in _core_clusters if cluster is not None]
    if _core_clusters:
        _expected_core_count = sum(cluster["count"] for cluster in _core_clusters) + (_cpu.get("low_power_cores") or 0)
        assert _cpu["total_cores"] == _expected_core_count, (
            f"{_cpu_name}: total_cores does not match the defined core clusters"
        )

    _base_clock = _cpu.get("base_clock_ghz")
    _boost_clock = _cpu.get("boost_clock_ghz")
    if isinstance(_base_clock, (int, float)) and isinstance(_boost_clock, (int, float)):
        assert _base_clock <= _boost_clock, f"{_cpu_name}: base_clock_ghz exceeds boost_clock_ghz"

    _aliases = _cpu["aliases"]
    assert all(isinstance(_alias, str) and _alias == _alias.lower() for _alias in _aliases), (
        f"{_cpu_name}: aliases must be lowercase strings"
    )
    assert len(_aliases) == len(set(_aliases)), f"{_cpu_name}: aliases must be unique"

    _memory_limits_by_type = _cpu.get("max_memory_gb_by_type")
    if _memory_limits_by_type is not None:
        assert all(_limit > 0 for _limit in _memory_limits_by_type.values()), (
            f"{_cpu_name}: per-type memory limits must be positive"
        )
        assert _cpu["max_memory_gb"] == max(_memory_limits_by_type.values()), (
            f"{_cpu_name}: max_memory_gb must be the highest per-type memory limit"
        )


# --- Helper Query Methods ---
def get_cpu_spec(key: str) -> CPUSpecEntry | None:
    """Retrieve canonical CPU specification by key."""
    return CPU_SPECS.get(key.lower().strip())


def find_cpu_by_alias(text: str) -> tuple[str, CPUSpecEntry] | None:
    """Find a canonical CPU specification by matching against known aliases."""
    normalized = text.lower().strip()
    for cpu_key, entry in CPU_SPECS.items():
        if normalized == cpu_key or normalized in entry.get("aliases", []):
            return cpu_key, entry
    return None


# --- Helper Query Methods ---
def get_cpu_spec(key: str) -> CPUSpecEntry | None:
    """Retrieve canonical CPU specification by key."""
    return CPU_SPECS.get(key.lower().strip())


def find_cpu_by_alias(text: str) -> tuple[str, CPUSpecEntry] | None:
    """Find a canonical CPU specification by matching against known aliases."""
    normalized = text.lower().strip()
    for cpu_key, entry in CPU_SPECS.items():
        if normalized == cpu_key or normalized in entry.get("aliases", []):
            return cpu_key, entry
    return None

