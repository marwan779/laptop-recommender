"""Resilient Execution Boundary: Context Managers and Decorators.

Provides unified error isolation, automatic status code extraction,
DLQ quarantine routing, and circuit breaker evaluation.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
import functools
import logging
import traceback
from typing import Any, TypeVar

from app.common.resilience.circuit_breaker import BatchCircuitBreaker, CircuitBreakerTrippedError
from app.common.resilience.models import (
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction,
    ServiceErrorRecord,
)
from app.common.resilience.quarantine import DeadLetterQuarantine

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def extract_status_code(exc: BaseException) -> int | None:
    """Intelligently inspect an exception to extract HTTP/API status code."""
    # 1. Direct status_code attribute (FastAPI HTTPException, starlette, httpx)
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code

    # 2. Nested response object (httpx, requests, curl_cffi, boto3)
    resp = getattr(exc, "response", None)
    if resp is not None:
        resp_code = getattr(resp, "status_code", None)
        if isinstance(resp_code, int):
            return resp_code
        # Boto3 ClientError format: exc.response['ResponseMetadata']['HTTPStatusCode']
        if isinstance(resp, dict):
            boto_code = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if isinstance(boto_code, int):
                return boto_code

    # 3. urllib.error.HTTPError or standard socket/os error code
    code_attr = getattr(exc, "code", None)
    if isinstance(code_attr, int):
        return code_attr

    return None


class BoundaryContext:
    """Mutable context yielded inside resilient_boundary for inspection or dynamic metadata."""

    def __init__(self) -> None:
        self.error_record: ServiceErrorRecord | None = None
        self.has_error: bool = False
        self.status_code: int | None = None


@contextmanager
def resilient_boundary(
    category: ErrorCategory,
    source_component: str,
    context: dict[str, Any] | None = None,
    quarantine: DeadLetterQuarantine | None = None,
    circuit_breaker: BatchCircuitBreaker | None = None,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    recovery_action: RecoveryAction = RecoveryAction.QUARANTINED,
    payload_snapshot: dict[str, Any] | None = None,
    suppress: bool = True,
    reraise_on_circuit_break: bool = True,
    on_error: Callable[[ServiceErrorRecord], None] | None = None,
) -> Generator[BoundaryContext, None, None]:
    """Isolate an execution block, log typed diagnostics, and route failures to DLQ.

    Args:
        category: Operational classification (network, dom_parsing, pipeline_extraction, etc.).
        source_component: Identifier for originating module (e.g. 'store.elbadr').
        context: Operational metadata (URL, product_id, index, etc.).
        quarantine: Optional DeadLetterQuarantine collector instance.
        circuit_breaker: Optional BatchCircuitBreaker to record health and check thresholds.
        severity: Severity rating of intercepted error.
        recovery_action: Action label to attach to the record.
        payload_snapshot: Input data to save in DLQ for reproduction.
        suppress: True to swallow error and continue execution; False to re-raise after recording.
        reraise_on_circuit_break: If circuit breaker trips, always re-raise to halt the batch.
        on_error: Optional callback executed when an error is caught.
    """
    ctx = BoundaryContext()

    # Pre-check circuit breaker health before executing the block
    if circuit_breaker and circuit_breaker.is_tripped:
        if reraise_on_circuit_break:
            circuit_breaker.check_circuit()
        return

    try:
        yield ctx
        # Block succeeded: record success with circuit breaker
        if circuit_breaker:
            circuit_breaker.record_success()

    except CircuitBreakerTrippedError:
        # Re-raised from internal check, always propagate if requested
        if reraise_on_circuit_break:
            raise
    except BaseException as exc:
        ctx.has_error = True
        status_code = extract_status_code(exc)
        ctx.status_code = status_code
        tb_str = traceback.format_exc()

        # Update circuit breaker
        tripped = False
        if circuit_breaker:
            tripped = circuit_breaker.record_failure(reason=f"{type(exc).__name__}: {exc}")

        effective_action = RecoveryAction.CIRCUIT_BROKEN if tripped else recovery_action

        # Record into DLQ quarantine
        record: ServiceErrorRecord
        if quarantine:
            record = quarantine.record_error(
                category=category,
                source_component=source_component,
                exception=exc,
                traceback_str=tb_str,
                context=context,
                status_code=status_code,
                severity=severity,
                recovery_action=effective_action,
                payload_snapshot=payload_snapshot,
            )
            if tripped:
                quarantine.mark_circuit_broken()
        else:
            record = ServiceErrorRecord(
                category=category,
                severity=severity,
                source_component=source_component,
                context=context or {},
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                status_code=status_code,
                traceback=tb_str,
                recovery_action=effective_action,
                payload_snapshot=payload_snapshot,
            )
            logger.warning(
                "[Resilience Boundary] Caught %s in '%s' (%s): %s [status=%s, id=%s]",
                category.value,
                source_component,
                record.exception_type,
                record.exception_message,
                status_code,
                record.error_id,
            )

        ctx.error_record = record

        if on_error:
            try:
                on_error(record)
            except Exception as cb_err:
                logger.error("[Resilience Boundary] on_error callback raised: %s", cb_err)

        # If circuit breaker just tripped and caller wants circuit aborts reraised:
        if tripped and reraise_on_circuit_break:
            raise CircuitBreakerTrippedError(
                target_key=circuit_breaker.target_key if circuit_breaker else "unknown",
                failure_rate_pct=circuit_breaker.failure_rate_pct if circuit_breaker else 100.0,
                threshold_pct=circuit_breaker.failure_threshold_pct if circuit_breaker else 20.0,
                reason=circuit_breaker.tripped_reason or str(exc),
            ) from exc

        # If suppression is disabled, re-raise original exception
        if not suppress:
            raise


def resilient_step(
    category: ErrorCategory,
    source_component: str,
    fallback_value: Any = None,
    quarantine: DeadLetterQuarantine | None = None,
    circuit_breaker: BatchCircuitBreaker | None = None,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
) -> Callable[[F], F]:
    """Decorator to wrap a function with a resilient boundary, returning fallback_value on error."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with resilient_boundary(
                category=category,
                source_component=source_component,
                context={"function": fn.__qualname__},
                quarantine=quarantine,
                circuit_breaker=circuit_breaker,
                severity=severity,
                suppress=True,
            ) as b_ctx:
                return fn(*args, **kwargs)
            if b_ctx.has_error:
                return fallback_value
            return None

        return wrapper  # type: ignore[return-value]

    return decorator
