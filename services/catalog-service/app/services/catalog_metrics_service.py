"""Catalog Metrics Enrichment Service.

Reads scraping input catalog JSON, enriches each laptop with the 6 hardware metrics,
and updates the catalog file in-place or in-memory.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from app.services.metrics_engine import (
    calculate_all_hardware_metrics,
    is_laptop_verified_for_metrics,
)

logger = logging.getLogger("catalog.metrics_service")

# Default service file locations relative to service root
SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT_FILE = SERVICE_ROOT / "scraping input" / "unified_catalog_latest.json"
DEFAULT_CPU_BENCHMARKS = SERVICE_ROOT / "data" / "cpu_benchmarks.json"
DEFAULT_GPU_BENCHMARKS = SERVICE_ROOT / "data" / "gpu_benchmarks.json"


class CatalogMetricsService:
    """Orchestrates loading, metric calculation, and atomic catalog persistence."""

    def __init__(
        self,
        cpu_benchmarks_path: Path = DEFAULT_CPU_BENCHMARKS,
        gpu_benchmarks_path: Path = DEFAULT_GPU_BENCHMARKS,
    ) -> None:
        self.cpu_benchmarks_path = cpu_benchmarks_path
        self.gpu_benchmarks_path = gpu_benchmarks_path
        self._cpu_benchmarks: dict[str, Any] | None = None
        self._gpu_benchmarks: dict[str, Any] | None = None

    def load_benchmarks(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Load CPU and GPU benchmark dictionaries from service data directory."""
        if self._cpu_benchmarks is None:
            if not self.cpu_benchmarks_path.exists():
                logger.warning(
                    "CPU benchmarks file not found at %s. Using empty reference.",
                    self.cpu_benchmarks_path,
                )
                self._cpu_benchmarks = {}
            else:
                with open(self.cpu_benchmarks_path, encoding="utf-8") as f:
                    self._cpu_benchmarks = json.load(f)

        if self._gpu_benchmarks is None:
            if not self.gpu_benchmarks_path.exists():
                logger.warning(
                    "GPU benchmarks file not found at %s. Using empty reference.",
                    self.gpu_benchmarks_path,
                )
                self._gpu_benchmarks = {}
            else:
                with open(self.gpu_benchmarks_path, encoding="utf-8") as f:
                    self._gpu_benchmarks = json.load(f)

        return self._cpu_benchmarks, self._gpu_benchmarks

    @staticmethod
    def _incoming_review_intelligence(
        laptop: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, float | None]:
        """Extract community review intelligence before derived metrics are recomputed.

        Returns the ``community_reviews`` mapping (when present) and the best
        available NLP score, preferring the review block over the TOPSIS input.
        """
        existing = laptop.get("derived_metrics") or {}
        if not isinstance(existing, dict):
            return None, None

        community_reviews = existing.get("community_reviews")
        if not isinstance(community_reviews, dict) or not community_reviews:
            community_reviews = None

        topsis = existing.get("topsis_inputs") or {}
        nlp_score = topsis.get("community_nlp_score") if isinstance(topsis, dict) else None
        if community_reviews and community_reviews.get("community_nlp_score") is not None:
            nlp_score = community_reviews.get("community_nlp_score")

        return community_reviews, nlp_score

    def enrich_catalog_dict(
        self,
        catalog_data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Enrich an in-memory catalog dictionary with hardware metrics and TOPSIS inputs.

        Args:
            catalog_data: Catalog dictionary with a list of 'laptops'.

        Returns:
            Tuple of (enriched_catalog_data, summary_dict).
        """
        start_time = time.perf_counter()
        laptops = catalog_data.get("laptops")
        if not isinstance(laptops, list):
            raise ValueError(f"Invalid catalog schema: expected 'laptops' list, got {type(laptops)}")

        cpu_benchmarks, gpu_benchmarks = self.load_benchmarks()
        total_laptops = len(laptops)
        processed_count = 0

        logger.info(
            "Calculating 6 hardware metrics for %d laptops (using %d CPUs, %d GPUs)",
            total_laptops,
            len(cpu_benchmarks),
            len(gpu_benchmarks),
        )

        gpu_scores: list[float] = []
        cpu_scores: list[float] = []
        display_scores: list[float] = []
        portability_scores: list[float] = []
        upgradeability_scores: list[float] = []

        skipped_unverified = 0

        for laptop in laptops:
            if not is_laptop_verified_for_metrics(laptop):
                laptop["hardware_metrics"] = None
                skipped_unverified += 1
                continue

            community_reviews, community_nlp_score = self._incoming_review_intelligence(laptop)

            metrics = calculate_all_hardware_metrics(
                laptop=laptop,
                cpu_benchmarks=cpu_benchmarks,
                gpu_benchmarks=gpu_benchmarks,
            )

            # Preserve review intelligence: recomputing hardware metrics must not
            # wipe the community review block or reset the NLP score to neutral.
            if community_reviews is not None:
                metrics["community_reviews"] = community_reviews
            if community_nlp_score is not None:
                metrics.setdefault("topsis_inputs", {})["community_nlp_score"] = community_nlp_score

            laptop["hardware_metrics"] = metrics
            laptop["derived_metrics"] = metrics
            processed_count += 1

            gpu_scores.append(metrics["silicon"]["effective_gpu_score"])
            cpu_scores.append(metrics["silicon"]["effective_cpu_score"])
            display_scores.append(metrics["display"]["display_score"])
            portability_scores.append(metrics["mobility"]["portability_score"])
            upgradeability_scores.append(metrics["longevity"]["upgradeability_score"])

        catalog_data["metrics_calculated_at"] = datetime.now(UTC).isoformat()
        catalog_data["metrics_version"] = "1.0.0"

        elapsed = time.perf_counter() - start_time

        summary = {
            "total_laptops": total_laptops,
            "processed_successfully": processed_count,
            "skipped_unverified": skipped_unverified,
            "elapsed_seconds": round(elapsed, 3),
            "averages": {
                "effective_gpu_score": round(sum(gpu_scores) / len(gpu_scores), 2) if gpu_scores else 0.0,
                "effective_cpu_score": round(sum(cpu_scores) / len(cpu_scores), 2) if cpu_scores else 0.0,
                "display_score": round(sum(display_scores) / len(display_scores), 2) if display_scores else 0.0,
                "portability_score": round(sum(portability_scores) / len(portability_scores), 2)
                if portability_scores
                else 0.0,
                "upgradeability_score": round(sum(upgradeability_scores) / len(upgradeability_scores), 2)
                if upgradeability_scores
                else 0.0,
            },
        }

        logger.info(
            "Metrics calculation completed: %d laptops in %.3fs (avg GPU: %.2f, avg CPU: %.2f)",
            processed_count,
            elapsed,
            summary["averages"]["effective_gpu_score"],
            summary["averages"]["effective_cpu_score"],
        )

        return catalog_data, summary

    def enrich_catalog(
        self,
        catalog_path: Path = DEFAULT_INPUT_FILE,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Read catalog JSON, compute 6 hardware metrics for each laptop, and save in-place.

        Args:
            catalog_path: Path to unified_catalog_latest.json
            overwrite: Whether to overwrite the input file in-place

        Returns:
            Execution summary dictionary with timing and aggregated statistics.
        """
        if not catalog_path.exists():
            raise FileNotFoundError(f"Catalog file not found at: {catalog_path}")

        logger.info("Loading catalog from %s", catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            catalog_data = json.load(f)

        enriched_data, summary = self.enrich_catalog_dict(catalog_data)

        # Atomic file write to prevent corruption
        if overwrite:
            target_dir = catalog_path.parent
            with tempfile.NamedTemporaryFile(
                "w",
                dir=target_dir,
                delete=False,
                encoding="utf-8",
                suffix=".tmp",
            ) as tf:
                json.dump(enriched_data, tf, indent=2, ensure_ascii=False)
                temp_name = tf.name

            # Atomically replace target file
            os.replace(temp_name, catalog_path)
            logger.info("Successfully updated catalog in-place at %s", catalog_path)

        return summary
