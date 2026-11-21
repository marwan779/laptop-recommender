"""add_decoupled_metrics_scores

Revision ID: c9f4a1d7b2e6
Revises: a8d3f9c1b204
Create Date: 2026-11-20 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9f4a1d7b2e6"
down_revision: str | Sequence[str] | None = "a8d3f9c1b204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DECOUPLED_COLUMNS: tuple[str, ...] = (
    "gpu_compute_score",
    "vram_score",
    "display_gaming_score",
    "display_creator_score",
    "battery_score",
    "portability_score",
    "upgradeability_score",
    "build_quality_score",
)


def upgrade() -> None:
    """Add the 8 decoupled metrics columns alongside the legacy TOPSIS scores."""
    for column_name in DECOUPLED_COLUMNS:
        op.add_column(
            "laptop_metrics",
            sa.Column(
                column_name,
                sa.Numeric(precision=5, scale=2),
                nullable=False,
                server_default="50.00",
            ),
        )


def downgrade() -> None:
    """Drop the 8 decoupled metrics columns."""
    for column_name in reversed(DECOUPLED_COLUMNS):
        op.drop_column("laptop_metrics", column_name)
