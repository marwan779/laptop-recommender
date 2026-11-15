#!/usr/bin/env python3
"""Offline CLI script for batch-computing hardware metrics and static TOPSIS persona scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from app.domain.metrics.scoring import compute_laptop_metrics
from app.domain.recommendation.topsis import apply_persona_scores_to_catalog


def enrich_catalog_with_metrics_and_personas(
    input_path: str,
    output_path: str,
    *,
    with_metrics: bool = True,
    with_personas: bool = True,
) -> Dict[str, Any]:
    catalog = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if with_metrics:
        for lap in catalog.get("laptops", []):
            lap["derived_metrics"] = compute_laptop_metrics(lap)
    if with_personas:
        apply_persona_scores_to_catalog(catalog)

    Path(output_path).write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute catalog derived_metrics and persona_scores")
    parser.add_argument("--input", default="unified_catalog_final_v6.json")
    parser.add_argument("--output", default="unified_catalog_topsis_ready_v6.json")
    parser.add_argument("--skip-metrics", action="store_true")
    parser.add_argument("--skip-personas", action="store_true")
    args = parser.parse_args()

    out = enrich_catalog_with_metrics_and_personas(
        args.input,
        args.output,
        with_metrics=not args.skip_metrics,
        with_personas=not args.skip_personas,
    )
    print(f"Processed {len(out.get('laptops', []))} laptops -> {args.output}")
