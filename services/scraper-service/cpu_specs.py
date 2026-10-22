"""Backward-compatibility proxy for app.pipeline.data.cpu_specs."""

from app.pipeline.data.cpu_specs import (
    CPU_SPECS,
    BrandType,
    CPUSpecEntry,
    CoreClusterSpec,
)

__all__ = [
    "CPU_SPECS",
    "BrandType",
    "CPUSpecEntry",
    "CoreClusterSpec",
]
