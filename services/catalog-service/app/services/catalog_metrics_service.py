"""Catalog Metrics Enrichment Service.

Reads scraping input catalog JSON, enriches each laptop with the 6 hardware metrics,
and updates the catalog file in-place.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
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
        start_time = time.perf_counter()

        if not catalog_path.exists():
            raise FileNotFoundError(f"Catalog file not found at: {catalog_path}")

        logger.info("Loading catalog from %s", catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            catalog_data = json.load(f)

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

            metrics = calculate_all_hardware_metrics(
                laptop=laptop,
                cpu_benchmarks=cpu_benchmarks,
                gpu_benchmarks=gpu_benchmarks,
            )
            laptop["hardware_metrics"] = metrics
            processed_count += 1

            gpu_scores.append(metrics["silicon"]["effective_gpu_score"])
            cpu_scores.append(metrics["silicon"]["effective_cpu_score"])
            display_scores.append(metrics["display"]["display_score"])
            portability_scores.append(metrics["mobility"]["portability_score"])
            upgradeability_scores.append(metrics["longevity"]["upgradeability_score"])

        # Update metadata
        catalog_data["metrics_calculated_at"] = datetime.now(UTC).isoformat()
        catalog_data["metrics_version"] = "1.0.0"

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
                json.dump(catalog_data, tf, indent=2, ensure_ascii=False)
                temp_name = tf.name

            # Atomically replace target file
            os.replace(temp_name, catalog_path)
            logger.info("Successfully updated catalog in-place at %s", catalog_path)

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

        return summary
