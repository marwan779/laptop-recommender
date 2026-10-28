"""Resilient Execution Boundary: Context Managers and Decorators."""

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
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code

    resp = getattr(exc, "response", None)
    if resp is not None:
        resp_code = getattr(resp, "status_code", None)
        if isinstance(resp_code, int):
            return resp_code
        if isinstance(resp, dict):
            boto_code = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if isinstance(boto_code, int):
                return boto_code

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
    """Isolate an execution block, log typed diagnostics, and route failures to DLQ."""
    ctx = BoundaryContext()

    if circuit_breaker and circuit_breaker.is_tripped:
        if reraise_on_circuit_break:
            circuit_breaker.check_circuit()
        return

    try:
        yield ctx
        if circuit_breaker:
            circuit_breaker.record_success()

    except CircuitBreakerTrippedError:
        if reraise_on_circuit_break:
            raise
    except BaseException as exc:
        ctx.has_error = True
        status_code = extract_status_code(exc)
        ctx.status_code = status_code
        tb_str = traceback.format_exc()

        tripped = False
        if circuit_breaker:
            tripped = circuit_breaker.record_failure(reason=f"{type(exc).__name__}: {exc}")

        effective_action = RecoveryAction.CIRCUIT_BROKEN if tripped else recovery_action

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
            except Exception as cb_err:  # noqa: BLE001
                logger.error("[Resilience Boundary] on_error callback raised: %s", cb_err)

        if tripped and reraise_on_circuit_break:
            raise CircuitBreakerTrippedError(
                target_key=circuit_breaker.target_key if circuit_breaker else "unknown",
                failure_rate_pct=circuit_breaker.failure_rate_pct if circuit_breaker else 100.0,
                threshold_pct=circuit_breaker.failure_threshold_pct if circuit_breaker else 20.0,
                reason=circuit_breaker.tripped_reason or str(exc),
            ) from exc

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

