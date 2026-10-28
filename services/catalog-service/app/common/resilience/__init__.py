"""Common Resilience Subsystem for the Catalog Microservice."""

from app.common.resilience.boundary import (
    BoundaryContext,
    extract_status_code,
    resilient_boundary,
    resilient_step,
)
from app.common.resilience.circuit_breaker import (
    BatchCircuitBreaker,
    CircuitBreakerTrippedError,
)
from app.common.resilience.models import (
    DeadLetterQuarantineReport,
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction,
    ServiceErrorRecord,
    utcnow_str,
)
from app.common.resilience.quarantine import DeadLetterQuarantine

__all__ = [
    "BatchCircuitBreaker",
    "BoundaryContext",
    "CircuitBreakerTrippedError",
    "DeadLetterQuarantine",
    "DeadLetterQuarantineReport",
    "ErrorCategory",
    "ErrorSeverity",
    "RecoveryAction",
    "ServiceErrorRecord",
    "extract_status_code",
    "resilient_boundary",
    "resilient_step",
    "utcnow_str",
]

