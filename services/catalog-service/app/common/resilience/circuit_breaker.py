"""Dynamic Batch Circuit Breaker for Catalog Ingestion and Processing."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CircuitBreakerTrippedError(Exception):
    """Raised when an operation is attempted while the circuit breaker is tripped."""

    def __init__(self, target_key: str, failure_rate_pct: float, threshold_pct: float, reason: str) -> None:
        self.target_key = target_key
        self.failure_rate_pct = failure_rate_pct
        self.threshold_pct = threshold_pct
        self.reason = reason
        super().__init__(
            f"Circuit breaker tripped for target '{target_key}': "
            f"failure rate {failure_rate_pct:.1f}% exceeded safety threshold {threshold_pct:.1f}%. "
            f"Reason: {reason}"
        )


class BatchCircuitBreaker:
    """Evaluates error density during batch processing and trips when unhealthy."""

    def __init__(
        self,
        target_key: str = "default",
        failure_threshold_pct: float = 20.0,
        min_items_threshold: int = 5,
        consecutive_failure_limit: int = 10,
    ) -> None:
        self.target_key = target_key
        self.failure_threshold_pct = float(failure_threshold_pct)
        self.min_items_threshold = int(min_items_threshold)
        self.consecutive_failure_limit = int(consecutive_failure_limit)

        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failures = 0
        self._is_tripped = False
        self._tripped_reason: str | None = None

    @property
    def is_tripped(self) -> bool:
        return self._is_tripped

    @property
    def tripped_reason(self) -> str | None:
        return self._tripped_reason

    @property
    def total_processed(self) -> int:
        return self._success_count + self._failure_count

    @property
    def failure_rate_pct(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return (self._failure_count / self.total_processed) * 100.0

    def record_success(self) -> None:
        if self._is_tripped:
            return
        self._success_count += 1
        self._consecutive_failures = 0

    def record_failure(self, reason: str = "Error recorded") -> bool:
        if self._is_tripped:
            return True

        self._failure_count += 1
        self._consecutive_failures += 1

        if self._consecutive_failures >= self.consecutive_failure_limit:
            self._trip(
                f"Consecutive failure limit reached: {self._consecutive_failures} >= {self.consecutive_failure_limit}"
            )
            return True

        if self.total_processed >= self.min_items_threshold and self.failure_rate_pct >= self.failure_threshold_pct:
            self._trip(
                f"Failure rate {self.failure_rate_pct:.1f}% exceeded threshold {self.failure_threshold_pct:.1f}%"
            )
            return True

        return False

    def _trip(self, reason: str) -> None:
        self._is_tripped = True
        self._tripped_reason = reason
        logger.error(
            "Circuit breaker tripped for '%s': %s (Processed: %d, Failures: %d)",
            self.target_key,
            reason,
            self.total_processed,
            self._failure_count,
        )

    def check_circuit(self) -> None:
        if self._is_tripped:
            raise CircuitBreakerTrippedError(
                target_key=self.target_key,
                failure_rate_pct=self.failure_rate_pct,
                threshold_pct=self.failure_threshold_pct,
                reason=self._tripped_reason or "Circuit breaker is open",
            )

    def reset(self) -> None:
        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failures = 0
        self._is_tripped = False
        self._tripped_reason = None

    def get_health_metrics(self) -> dict[str, Any]:
        return {
            "target_key": self.target_key,
            "is_tripped": self._is_tripped,
            "tripped_reason": self._tripped_reason,
            "total_processed": self.total_processed,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "failure_rate_pct": round(self.failure_rate_pct, 2),
            "consecutive_failures": self._consecutive_failures,
            "threshold_pct": self.failure_threshold_pct,
        }
