"""Matching, Deduplication, and Catalog Consolidation Package."""

from app.matching.combiner import CatalogCombiner
from app.matching.disjoint_set import DisjointSet
from app.matching.fingerprint import (
    are_hardware_compatible,
    generate_hardware_fingerprint,
    normalize_mpn,
)
from app.matching.fusion import merge_specifications
from app.matching.models import (
    CanonicalLaptop,
    StoreOffer,
    UnifiedCatalog,
)
from app.matching.normalizer import ModelNormalizer

__all__ = [
    "CanonicalLaptop",
    "CatalogCombiner",
    "DisjointSet",
    "ModelNormalizer",
    "StoreOffer",
    "UnifiedCatalog",
    "are_hardware_compatible",
    "generate_hardware_fingerprint",
    "merge_specifications",
    "normalize_mpn",
]
