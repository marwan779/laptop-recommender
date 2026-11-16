"""create_laptop_review_source

Revision ID: f3b9c2d7a8e4
Revises: c1a7e4d92f60
Create Date: 2026-11-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f3b9c2d7a8e4"
down_revision: Union[str, Sequence[str], None] = "c1a7e4d92f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the canonical laptop review source link table."""
    op.create_table(
        "laptop_review_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "laptop_configuration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "laptop_configuration.id",
                name="fk_laptop_review_source_config_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("author_or_channel", sa.String(length=150), nullable=True),
        sa.Column("channel_url", sa.Text(), nullable=True),
        sa.Column("rating", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("score_or_views", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "laptop_configuration_id",
            "url",
            name="uq_laptop_review_source_config_url",
        ),
    )
    op.create_index(
        op.f("ix_laptop_review_source_laptop_configuration_id"),
        "laptop_review_source",
        ["laptop_configuration_id"],
        unique=False,
    )
    op.create_index(
        "ix_laptop_review_source_config_type",
        "laptop_review_source",
        ["laptop_configuration_id", "source_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the canonical laptop review source link table."""
    op.drop_index(
        "ix_laptop_review_source_config_type",
        table_name="laptop_review_source",
    )
    op.drop_index(
        op.f("ix_laptop_review_source_laptop_configuration_id"),
        table_name="laptop_review_source",
    )
    op.drop_table("laptop_review_source")
