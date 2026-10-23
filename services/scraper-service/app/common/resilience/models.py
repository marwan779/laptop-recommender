"""Core Data Models and Schemas for Microservice Resilience & Error Handling.

Defines structured error records, severity levels, failure categories,
and Dead-Letter Quarantine (DLQ) schemas for fault-isolated execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
import uuid

from pydantic import BaseModel, Field


def utcnow_str() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class ErrorCategory(StrEnum):
    """Categorization of failure origins across the scraping microservice."""

    NETWORK = "network"
    DOM_PARSING = "dom_parsing"
    PIPELINE_EXTRACTION = "pipeline_extraction"
    STORAGE = "storage"
    NOTIFICATION = "notification"
    API = "api"


class ErrorSeverity(StrEnum):
    """Severity rating of the captured error."""

    WARNING = "warning"  # Non-fatal warning (e.g. fallback used, non-blocking degradation)
    ERROR = "error"  # Fatal to single item, quarantined into DLQ; batch continues
    CRITICAL = "critical"  # Systemic failure (e.g. store completely blocked, circuit tripped)


class RecoveryAction(StrEnum):
    """Action taken by the resilience framework upon intercepting the error."""

    QUARANTINED = "quarantined"  # Item isolated to DLQ, pipeline continued
    FALLBACK_USED = "fallback_used"  # Degraded to fallback strategy (e.g. OCR/deterministic)
    CIRCUIT_BROKEN = "circuit_broken"  # Batch aborted due to high error rate
    RETRIED = "retried"  # Operation retried
    SUPPRESSED = "suppressed"  # Non-essential failure absorbed


class ServiceErrorRecord(BaseModel):
    """Structured, immutable diagnostic record for a single microservice error."""

    error_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID identifying this failure occurrence",
    )
    timestamp: str = Field(
        default_factory=utcnow_str,
        description="UTC ISO-8601 timestamp of when the error occurred",
    )
    category: ErrorCategory = Field(
        description="Operational layer/category where the error originated",
    )
    severity: ErrorSeverity = Field(
        default=ErrorSeverity.ERROR,
        description="Severity classification of the failure",
    )
    source_component: str = Field(
        description="Module or component identifier (e.g., 'store.elbadr', 'pipeline.deterministic', 'storage.s3')",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata (e.g. url, product_id, store_key, batch_index)",
    )
    exception_type: str = Field(
        description="Python exception class name (e.g. 'AttributeError', 'HTTPStatusError')",
    )
    exception_message: str = Field(
        description="String representation of the intercepted exception",
    )
    status_code: int | None = Field(
        default=None,
        description="HTTP or API status code if the error was caused by an external API or network call",
    )
    traceback: str = Field(
        description="Formatted stack trace string for developer diagnostics",
    )
    recovery_action: RecoveryAction = Field(
        default=RecoveryAction.QUARANTINED,
        description="Action applied to recover from or isolate this failure",
    )
    payload_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Exact payload/input snapshot that triggered the exception for offline replay",
    )


class DeadLetterQuarantineReport(BaseModel):
    """Aggregate DLQ report summarizing all quarantined items for a target crawl or job."""

    target_key: str = Field(
        description="Key of the store or brand target (e.g. 'elbadr', 'compumarts', 'asus')",
    )
    target_type: str = Field(
        default="store",
        description="Target category ('store' or 'brand')",
    )
    total_items_attempted: int = Field(
        default=0,
        description="Total items attempted during this processing run",
    )
    quarantined_items_count: int = Field(
        default=0,
        description="Number of failed items isolated into quarantine",
    )
    error_rate_pct: float = Field(
        default=0.0,
        description="Percentage of attempted items that failed and were quarantined",
    )
    circuit_broken: bool = Field(
        default=False,
        description="True if the batch was halted prematurely by the circuit breaker",
    )
    generated_at: str = Field(
        default_factory=utcnow_str,
        description="UTC ISO-8601 generation timestamp",
    )
    errors: list[ServiceErrorRecord] = Field(
        default_factory=list,
        description="Detailed list of all quarantined error records",
    )
