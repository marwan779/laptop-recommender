"""Isolated Local Model Extraction Module.

Provides 100% offline, zero-regex, schema-enforced specification extraction
from raw titles and unformatted PDP text.
"""

from .schema import LaptopSpecExtraction
from .extractor import LocalModelExtractor
from .table_extractor import (
    extract_raw_spec_table,
    format_table_for_prompt,
    reconcile_specs,
    split_power_specs,
)

__all__ = [
    "LaptopSpecExtraction",
    "LocalModelExtractor",
    "extract_raw_spec_table",
    "format_table_for_prompt",
    "reconcile_specs",
    "split_power_specs",
]
