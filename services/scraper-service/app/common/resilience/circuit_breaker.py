"""Dynamic Batch Circuit Breaker for Catalog Crawling and Processing.

Prevents microservice waste and ban risks by halting catalog processing
if the failure rate exceeds a safety threshold (default: 20%).
"""

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
    """Evaluates error density during catalog processing and trips when unhealthy.

    Attributes:
        target_key: Target store or brand identifier.
        failure_threshold_pct: Failure percentage (0.0 to 100.0) that trips the breaker (default: 20.0%).
        min_items_threshold: Minimum items processed before failure rate triggers a trip (default: 5).
        consecutive_failure_limit: Number of consecutive failures that immediately trips (default: 10).
    """

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
        """Return True if circuit breaker has been tripped."""
        return self._is_tripped

    @property
    def tripped_reason(self) -> str | None:
        """Return diagnostic explanation of why circuit breaker tripped."""
        return self._tripped_reason

    @property
    def total_attempted(self) -> int:
        """Total items attempted (successes + failures)."""
        return self._success_count + self._failure_count

    @property
    def failure_rate_pct(self) -> float:
        """Current failure rate expressed as a percentage (0.0 - 100.0)."""
        total = self.total_attempted
        if total == 0:
            return 0.0
        return (self._failure_count / total) * 100.0

    def record_success(self) -> None:
        """Register a successfully processed item."""
        if self._is_tripped:
            return
        self._success_count += 1
        self._consecutive_failures = 0

    def record_failure(self, reason: str | None = None) -> bool:
        """Register a failed item and re-evaluate circuit breaker health.

        Returns True if this failure caused the circuit breaker to trip.
        """
        if self._is_tripped:
            return True

        self._failure_count += 1
        self._consecutive_failures += 1

        # Check condition 1: Consecutive failure limit hit
        if self._consecutive_failures >= self.consecutive_failure_limit:
            self._trip(
                reason
                or (
                    f"Consecutive failure limit of {self.consecutive_failure_limit} reached "
                    f"({self._failure_count}/{self.total_attempted} total failed)"
                )
            )
            return True

        # Check condition 2: Failure rate exceeds threshold after min items
        if self.total_attempted >= self.min_items_threshold:
            rate = self.failure_rate_pct
            if rate > self.failure_threshold_pct:
                self._trip(
                    reason
                    or (
                        f"Failure rate {rate:.1f}% exceeded safety threshold "
                        f"{self.failure_threshold_pct:.1f}% ({self._failure_count}/{self.total_attempted} failed)"
                    )
                )
                return True

        return False

    def check_circuit(self) -> None:
        """Raise CircuitBreakerTrippedError if the circuit is tripped."""
        if self._is_tripped:
            raise CircuitBreakerTrippedError(
                target_key=self.target_key,
                failure_rate_pct=self.failure_rate_pct,
                threshold_pct=self.failure_threshold_pct,
                reason=self._tripped_reason or "Threshold exceeded",
            )

    def _trip(self, reason: str) -> None:
        self._is_tripped = True
        self._tripped_reason = reason
        logger.error(
            "[CircuitBreaker] ⚠️ Circuit breaker TRIPPED for target '%s': %s (Threshold: %.1f%%)",
            self.target_key,
            reason,
            self.failure_threshold_pct,
        )

    def reset(self) -> None:
        """Reset internal metrics to clean initial state."""
        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failures = 0
        self._is_tripped = False
        self._tripped_reason = None

    def stats(self) -> dict[str, Any]:
        """Return diagnostic metrics snapshot."""
        return {
            "target_key": self.target_key,
            "total_attempted": self.total_attempted,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "consecutive_failures": self._consecutive_failures,
            "failure_rate_pct": round(self.failure_rate_pct, 2),
            "threshold_pct": self.failure_threshold_pct,
            "is_tripped": self._is_tripped,
            "tripped_reason": self._tripped_reason,
        }
