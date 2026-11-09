"""add_reviews_lifecycle_columns

Revision ID: a4f1c7d29b63
Revises: e813a529873a
Create Date: 2026-11-07 10:12:44.118204

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4f1c7d29b63"
down_revision: Union[str, Sequence[str], None] = "e813a529873a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add community review lifecycle tracking to laptop_configuration."""
    op.add_column(
        "laptop_configuration",
        sa.Column("has_reviews", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("reviews_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_laptop_configuration_has_reviews"),
        "laptop_configuration",
        ["has_reviews"],
        unique=False,
    )


def downgrade() -> None:
    """Drop community review lifecycle tracking from laptop_configuration."""
    op.drop_index(op.f("ix_laptop_configuration_has_reviews"), table_name="laptop_configuration")
    op.drop_column("laptop_configuration", "reviews_checked_at")
    op.drop_column("laptop_configuration", "has_reviews")
