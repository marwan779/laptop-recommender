"""Core Data Models and Schemas for Microservice Resilience & Error Handling."""

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
    """Categorization of failure origins across microservices."""

    NETWORK = "network"
    DATABASE = "database"
    CATALOG_SCORING = "catalog_scoring"
    INGESTION = "ingestion"
    API = "api"
    STORAGE = "storage"
    DOM_PARSING = "dom_parsing"
    PIPELINE_EXTRACTION = "pipeline_extraction"
    NOTIFICATION = "notification"
    VALIDATION = "validation"


class ErrorSeverity(StrEnum):
    """Severity rating of the captured error."""

    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RecoveryAction(StrEnum):
    """Action taken by the resilience framework upon intercepting the error."""

    QUARANTINED = "quarantined"
    FALLBACK_USED = "fallback_used"
    CIRCUIT_BROKEN = "circuit_broken"
    RETRIED = "retried"
    SUPPRESSED = "suppressed"


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
        description="Module or component identifier (e.g., 'catalog.scoring', 'database.postgres')",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata (e.g. laptop_id, canonical_id, store_key)",
    )
    exception_type: str = Field(
        description="Python exception class name (e.g. 'SQLAlchemyError', 'ValueError')",
    )
    exception_message: str = Field(
        description="String representation of the intercepted exception",
    )
    status_code: int | None = Field(
        default=None,
        description="HTTP or API status code if the error was caused by an API call",
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

    report_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    generated_at: str = Field(
        default_factory=utcnow_str,
    )
    target_key: str
    target_type: str
    total_attempted: int
    quarantined_count: int
    circuit_broken: bool = False
    errors_by_category: dict[str, int] = Field(default_factory=dict)
    errors_by_severity: dict[str, int] = Field(default_factory=dict)
    records: list[ServiceErrorRecord] = Field(default_factory=list)
