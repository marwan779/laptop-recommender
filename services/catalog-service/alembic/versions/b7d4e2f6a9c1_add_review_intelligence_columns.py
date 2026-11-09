"""add_review_intelligence_columns

Revision ID: b7d4e2f6a9c1
Revises: a4f1c7d29b63
Create Date: 2026-11-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7d4e2f6a9c1"
down_revision: Union[str, Sequence[str], None] = "a4f1c7d29b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add strongly-typed bilingual review intelligence and aspect scores."""
    op.add_column(
        "laptop_configuration",
        sa.Column("reviews_evidence_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("pros_en", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("pros_ar", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("cons_en", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("cons_ar", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
    )

    for column_name in (
        "thermals_score",
        "acoustics_score",
        "build_and_hinges_score",
        "keyboard_and_trackpad_score",
        "real_battery_and_reliability_score",
    ):
        op.add_column(
            "laptop_metrics",
            sa.Column(column_name, sa.Numeric(precision=5, scale=2), server_default="75.00", nullable=False),
        )


def downgrade() -> None:
    """Drop the review intelligence and aspect score columns."""
    for column_name in (
        "real_battery_and_reliability_score",
        "keyboard_and_trackpad_score",
        "build_and_hinges_score",
        "acoustics_score",
        "thermals_score",
    ):
        op.drop_column("laptop_metrics", column_name)

    for column_name in (
        "cons_ar",
        "cons_en",
        "pros_ar",
        "pros_en",
        "reviews_evidence_count",
    ):
        op.drop_column("laptop_configuration", column_name)
