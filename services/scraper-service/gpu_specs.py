"""Canonical GPU specification schema and database loader.

Defines:
- GPUTDPLimits: Pydantic model for discrete GPU TDP/TGP envelope bounds.
- GPUFeatures: Pydantic model for modern GPU hardware features (RT, Frame Gen, AV1).
- GPUSpecificationEntry: Full Pydantic model for GPU ground-truth silicon specifications.
- GPU_SPECS: Pre-loaded dictionary of all canonical GPU specifications.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class GPUTDPLimits(BaseModel):
    min_w: int = Field(..., ge=20, le=175)
    max_w: int = Field(..., ge=35, le=200)
    base_max_w: int | None = Field(None, ge=20, le=175)
    dynamic_boost_w: int | None = Field(None, ge=0, le=50)

    @model_validator(mode="after")
    def validate_bounds(self) -> GPUTDPLimits:
        if self.min_w > self.max_w:
            raise ValueError(f"min_w ({self.min_w}) cannot exceed max_w ({self.max_w})")
        return self


class GPUFeatures(BaseModel):
    ray_tracing: bool
    frame_generation: bool
    av1_encoding: bool


class GPUSpecificationEntry(BaseModel):
    manufacturer: Literal["NVIDIA", "AMD", "Intel", "Apple", "Qualcomm"]
    model: str
    series: str
    variant: Literal["Laptop GPU", "Integrated GPU", "SoC Integrated"]
    chip_codename: str | None = None
    architecture: str
    process_node_nm: int | None = None
    integrated: bool

    vram_gb: int | list[int] | None = None
    memory_type: str
    bus_width_bits: int | None = None
    memory_speed_gbps: float | None = None

    cuda_cores: int | None = None
    tensor_cores: int | None = None
    rt_cores: int | None = None
    ai_tops: int | None = None

    tdp_limits: GPUTDPLimits | None = None
    features: GPUFeatures
    match_patterns: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def enforce_discrete_vs_integrated(self) -> GPUSpecificationEntry:
        if not self.integrated:
            # Discrete GPU Rules
            if self.vram_gb is None:
                raise ValueError(f"Discrete GPU '{self.model}' must specify 'vram_gb'")
            if self.bus_width_bits is None:
                raise ValueError(f"Discrete GPU '{self.model}' must specify 'bus_width_bits'")
            if self.tdp_limits is None:
                raise ValueError(f"Discrete GPU '{self.model}' must specify 'tdp_limits'")
        else:
            # Integrated GPU Rules
            if self.vram_gb is not None:
                raise ValueError(f"Integrated GPU '{self.model}' cannot have dedicated 'vram_gb'")
            if self.tdp_limits is not None:
                raise ValueError(f"Integrated GPU '{self.model}' cannot have dedicated 'tdp_limits'")
        return self


def load_gpu_specs() -> dict[str, dict]:
    """Load canonical GPU specifications dictionary from json file."""
    candidates = [
        Path(__file__).parent / "pipeline" / "data" / "gpu_specs.json",
        Path(__file__).resolve().parent / "pipeline" / "data" / "gpu_specs.json",
        Path(__file__).parent / "data" / "gpu_specs.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"Could not locate gpu_specs.json in candidates: {candidates}")


GPU_SPECS: dict[str, dict] = load_gpu_specs()
