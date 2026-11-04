"""create_laptop_metrics_topsis_table

Revision ID: c3774c547114
Revises: 39ea42df084b
Create Date: 2026-11-03 22:45:44.511277

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3774c547114"
down_revision: Union[str, Sequence[str], None] = "39ea42df084b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create laptop_metrics table for 1:1 hardware performance, TOPSIS scores, and sub-tiers."""
    op.create_table(
        "laptop_metrics",
        sa.Column(
            "laptop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("laptop_configuration.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        # 11 Flat TOPSIS Float Scores (0.00 to 100.00)
        sa.Column("cpu_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("gpu_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("silicon_index", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("power_therm_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("display_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("mobility_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("longevity_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("ergonomics_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("connectivity_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("community_nlp_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("value_score", sa.Numeric(precision=5, scale=2), nullable=False),
        # Operational Meta for TOPSIS Recommender
        sa.Column("effective_price_egp", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("is_recommendable_price", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("in_stock_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        # Computed Sub-Metrics & Tiers
        sa.Column("delta_p_watts", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("simultaneous_load_w", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("electrical_status", sa.String(length=30), nullable=False),
        sa.Column("estimated_battery_hours", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("silicon_tier", sa.String(length=50), nullable=False),
        sa.Column("display_tier", sa.String(length=50), nullable=False),
        sa.Column("portability_tier", sa.String(length=30), nullable=False),
        sa.Column("upgradeability_tier", sa.String(length=50), nullable=False),
        sa.Column("is_copilot_plus_pc", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pricing_status", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Drop laptop_metrics table."""
    op.drop_table("laptop_metrics")
