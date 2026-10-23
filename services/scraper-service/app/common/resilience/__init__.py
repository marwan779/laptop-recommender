"""Common Resilience Subsystem for the Scraper Microservice.

Provides microservice-wide error isolation, dynamic circuit breaking,
dead-letter quarantine (DLQ), and status code extraction across:
  - Network & Ingestion Layer
  - DOM & Pre-Processing Layer
  - Hardware Extraction Pipeline Layer
  - Persistence & Storage Layer
  - Notification & API Layers
"""

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
