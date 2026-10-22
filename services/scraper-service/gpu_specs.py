"""Backward-compatibility proxy for app.pipeline.data.gpu_specs."""

from app.pipeline.data.gpu_specs import (
    GPU_SPECS,
    GPUFeatures,
    GPUSpecificationEntry,
    GPUTDPLimits,
    load_gpu_specs,
)

__all__ = [
    "GPU_SPECS",
    "GPUFeatures",
    "GPUSpecificationEntry",
    "GPUTDPLimits",
    "load_gpu_specs",
]
