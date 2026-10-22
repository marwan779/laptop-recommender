"""Context variables and correlation ID tracking for asynchronous request scopes."""

from __future__ import annotations

import contextvars
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

# Global context variables for correlation tracking
_correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)
_request_context_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "request_context", default=None
)


def set_correlation_id(correlation_id: str | None) -> contextvars.Token[str | None]:
    """Set the current correlation ID in the context scope."""
    return _correlation_id_ctx.set(correlation_id)


def get_correlation_id() -> str | None:
    """Retrieve the current correlation ID from the context scope."""
    return _correlation_id_ctx.get()


def bind_context(**kwargs: Any) -> None:
    """Bind key-value metadata pairs to the current request context."""
    current = dict(_request_context_ctx.get() or {})
    current.update(kwargs)
    _request_context_ctx.set(current)


def get_context() -> dict[str, Any]:
    """Retrieve all metadata bound to the current context."""
    return dict(_request_context_ctx.get() or {})


def clear_context() -> None:
    """Clear all context variables for the current scope."""
    _correlation_id_ctx.set(None)
    _request_context_ctx.set(None)


@contextmanager
def request_context(
    correlation_id: str | None = None,
    **kwargs: Any,
) -> Generator[None, None, None]:
    """Context manager for temporary correlation ID and metadata binding."""
    token_cid = _correlation_id_ctx.set(correlation_id)
    prev_ctx = _request_context_ctx.get() or {}
    new_ctx = dict(prev_ctx)
    new_ctx.update(kwargs)
    token_ctx = _request_context_ctx.set(new_ctx)

    try:
        yield
    finally:
        _correlation_id_ctx.reset(token_cid)
        _request_context_ctx.reset(token_ctx)
