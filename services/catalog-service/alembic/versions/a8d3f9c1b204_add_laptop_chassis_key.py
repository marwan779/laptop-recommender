"""add_laptop_chassis_key

Revision ID: a8d3f9c1b204
Revises: f3b9c2d7a8e4
Create Date: 2026-11-16 09:20:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8d3f9c1b204"
down_revision: str | Sequence[str] | None = "f3b9c2d7a8e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexed chassis_key column on laptop_configuration for pre-dispatch review deduplication."""
    op.add_column(
        "laptop_configuration",
        sa.Column("chassis_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_laptop_configuration_chassis_key"),
        "laptop_configuration",
        ["chassis_key"],
        unique=False,
    )
    op.create_index(
        "ix_laptop_chassis_reviewed",
        "laptop_configuration",
        ["chassis_key", "has_reviews"],
        unique=False,
    )


def downgrade() -> None:
    """Remove chassis_key column and indexes from laptop_configuration."""
    op.drop_index("ix_laptop_chassis_reviewed", table_name="laptop_configuration")
    op.drop_index(op.f("ix_laptop_configuration_chassis_key"), table_name="laptop_configuration")
    op.drop_column("laptop_configuration", "chassis_key")
