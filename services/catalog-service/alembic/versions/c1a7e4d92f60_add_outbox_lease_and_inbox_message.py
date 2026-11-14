"""add_outbox_lease_and_inbox_message

Revision ID: c1a7e4d92f60
Revises: 4b8e1f6a2c93
Create Date: 2026-11-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c1a7e4d92f60"
down_revision: Union[str, Sequence[str], None] = "4b8e1f6a2c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add outbox lease/event-id columns and the transactional inbox table."""
    op.add_column("outbox_message", sa.Column("event_id", sa.String(length=100), nullable=True))
    op.add_column(
        "outbox_message",
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill deterministic ids for messages emitted before this migration.
    op.execute("UPDATE outbox_message SET event_id = id::text WHERE event_id IS NULL")
    # Legacy in-flight rows have no lease; treat them as immediately reclaimable.
    op.execute(
        "UPDATE outbox_message SET leased_at = created_at "
        "WHERE status = 'PUBLISHING' AND leased_at IS NULL"
    )

    op.create_index(
        op.f("ix_outbox_message_event_id"),
        "outbox_message",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_outbox_message_leased_at"),
        "outbox_message",
        ["leased_at"],
        unique=False,
    )

    op.create_table(
        "inbox_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("message_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("handler_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PROCESSED", nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_inbox_message_message_id"),
        "inbox_message",
        ["message_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the inbox table and outbox lease/event-id columns."""
    op.drop_index(op.f("ix_inbox_message_message_id"), table_name="inbox_message")
    op.drop_table("inbox_message")

    op.drop_index(op.f("ix_outbox_message_leased_at"), table_name="outbox_message")
    op.drop_index(op.f("ix_outbox_message_event_id"), table_name="outbox_message")
    op.drop_column("outbox_message", "leased_at")
    op.drop_column("outbox_message", "event_id")
