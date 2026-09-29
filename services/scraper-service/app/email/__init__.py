"""Email rendering and template helpers."""

from app.email.builder import (
    render_badge,
    render_metric_cards,
    render_pointers_list,
    render_shell,
)
from app.email.templates import (
    build_batch_finished_email,
    build_single_finished_email,
)

__all__ = [
    "render_badge",
    "render_metric_cards",
    "render_pointers_list",
    "render_shell",
    "build_single_finished_email",
    "build_batch_finished_email",
]
