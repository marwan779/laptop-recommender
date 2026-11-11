"""add_catalog_cursor_index

Revision ID: 9f1c2a7d4b6e
Revises: b7d4e2f6a9c1
Create Date: 2026-11-10 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9f1c2a7d4b6e"
down_revision: Union[str, Sequence[str], None] = "b7d4e2f6a9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a deterministic composite keyset index for cursor pagination."""
    op.create_index(
        "ix_laptop_cursor_price_id",
        "laptop_configuration",
        ["min_price_egp", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the composite keyset index."""
    op.drop_index("ix_laptop_cursor_price_id", table_name="laptop_configuration")
