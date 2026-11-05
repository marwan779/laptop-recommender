"""create_outbox_message_table

Revision ID: e813a529873a
Revises: 2780cc9a0302
Create Date: 2026-11-05 09:17:27.262308
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e813a529873a"
down_revision: Union[str, Sequence[str], None] = "2780cc9a0302"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create outbox_message table and its indexing for high-speed polling."""
    op.create_table(
        "outbox_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("routing_key", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="5", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_outbox_message_correlation_id"), "outbox_message", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_outbox_message_created_at"), "outbox_message", ["created_at"], unique=False)
    op.create_index(op.f("ix_outbox_message_event_type"), "outbox_message", ["event_type"], unique=False)
    op.create_index(op.f("ix_outbox_message_status"), "outbox_message", ["status"], unique=False)


def downgrade() -> None:
    """Drop outbox_message table and its indexes."""
    op.drop_index(op.f("ix_outbox_message_status"), table_name="outbox_message")
    op.drop_index(op.f("ix_outbox_message_event_type"), table_name="outbox_message")
    op.drop_index(op.f("ix_outbox_message_created_at"), table_name="outbox_message")
    op.drop_index(op.f("ix_outbox_message_correlation_id"), table_name="outbox_message")
    op.drop_table("outbox_message")
