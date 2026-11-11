"""create_offer_price_history

Revision ID: 4b8e1f6a2c93
Revises: 9f1c2a7d4b6e
Create Date: 2026-11-11 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "4b8e1f6a2c93"
down_revision: Union[str, Sequence[str], None] = "9f1c2a7d4b6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the append-only price history event log and backfill day-1 data."""
    op.create_table(
        "offer_price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("laptop_configuration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_key", sa.String(length=50), nullable=False),
        sa.Column("price_egp", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["laptop_offer.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["laptop_configuration_id"],
            ["laptop_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offer_price_history_offer_id",
        "offer_price_history",
        ["offer_id"],
    )
    op.create_index(
        "ix_offer_price_history_laptop_configuration_id",
        "offer_price_history",
        ["laptop_configuration_id"],
    )
    op.create_index(
        "ix_offer_price_history_store_key",
        "offer_price_history",
        ["store_key"],
    )
    op.create_index(
        "ix_offer_price_history_laptop_time",
        "offer_price_history",
        ["laptop_configuration_id", "recorded_at"],
    )
    op.create_index(
        "ix_offer_price_history_offer_time",
        "offer_price_history",
        ["offer_id", "recorded_at"],
    )

    # ------------------------------------------------------------------
    # Day-1 backfill: seed history from existing laptop_offer rows so every
    # laptop already in the catalog has a working multi-store chart.
    # ------------------------------------------------------------------

    # Step 1 — historical previous price at the offer's creation timestamp.
    op.execute(
        """
        INSERT INTO offer_price_history
            (id, offer_id, laptop_configuration_id, store_key, price_egp, in_stock, recorded_at)
        SELECT
            gen_random_uuid(),
            o.id,
            o.laptop_configuration_id,
            LOWER(TRIM(o.store_key)),
            o.previous_price_egp,
            o.in_stock,
            o.created_at
        FROM laptop_offer AS o
        WHERE o.previous_price_egp IS NOT NULL
          AND o.previous_price_egp > 0
          AND o.previous_price_egp <> o.price_egp
        """
    )

    # Step 2 — current active price at the latest verification timestamp.
    op.execute(
        """
        INSERT INTO offer_price_history
            (id, offer_id, laptop_configuration_id, store_key, price_egp, in_stock, recorded_at)
        SELECT
            gen_random_uuid(),
            o.id,
            o.laptop_configuration_id,
            LOWER(TRIM(o.store_key)),
            o.price_egp,
            o.in_stock,
            COALESCE(o.price_updated_at, o.created_at)
        FROM laptop_offer AS o
        WHERE o.price_egp > 0
        """
    )


def downgrade() -> None:
    """Drop the price history event log."""
    op.drop_index("ix_offer_price_history_offer_time", table_name="offer_price_history")
    op.drop_index("ix_offer_price_history_laptop_time", table_name="offer_price_history")
    op.drop_index("ix_offer_price_history_store_key", table_name="offer_price_history")
    op.drop_index(
        "ix_offer_price_history_laptop_configuration_id",
        table_name="offer_price_history",
    )
    op.drop_index("ix_offer_price_history_offer_id", table_name="offer_price_history")
    op.drop_table("offer_price_history")
