"""Atomic JSON persistence adapters (delta cache + catalog specs provider)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.infrastructure.protocols import ICatalogSpecsProvider, IDeltaCacheRepository


def _load_json_dict(path: Optional[Union[str, Path]]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json_atomic(path: Union[str, Path], data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


class JsonDeltaCacheRepository(IDeltaCacheRepository):
    """Atomic `enricher_delta_cache.json` repository."""

    def load(self, path: Optional[str]) -> Dict[str, Any]:
        return _load_json_dict(path)

    def save(self, path: str, data: Dict[str, Any]) -> None:
        _save_json_atomic(path, data)


class JsonCatalogSpecsProvider(ICatalogSpecsProvider):
    """Reads the unified catalog and exposes a canonical-id keyed lookup."""

    def load_map(self, catalog_path: Optional[str]) -> Dict[str, Any]:
        if not catalog_path or not Path(catalog_path).exists():
            return {}
        with open(catalog_path, "r", encoding="utf-8") as f:
            cat_raw = json.load(f)
        return {l["canonical_id"]: l for l in cat_raw.get("laptops", []) if "canonical_id" in l}
