"""create_scraping_pointers_and_logs

Revision ID: 2780cc9a0302
Revises: c3774c547114
Create Date: 2026-11-03 22:45:52.494478

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2780cc9a0302"
down_revision: Union[str, Sequence[str], None] = "c3774c547114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create store_scraping_pointer and scraping_batch_log tables."""
    # 1. Create store_scraping_pointer
    op.create_table(
        "store_scraping_pointer",
        sa.Column("store_key", sa.String(length=50), primary_key=True, nullable=False),
        sa.Column("store_name", sa.String(length=100), nullable=False),
        sa.Column("store_domain", sa.String(length=100), nullable=True),
        sa.Column("latest_pointers", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("total_active_offers", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scrape_interval_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. Create scraping_batch_log
    op.create_table(
        "scraping_batch_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("store_key", sa.String(length=50), index=True, nullable=False),
        sa.Column("trigger_type", sa.String(length=30), server_default="CRON", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="STARTED", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("items_scraped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new_laptops_added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("offers_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pointers_sent", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("pointers_received", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop scraping_batch_log and store_scraping_pointer tables."""
    op.drop_table("scraping_batch_log")
    op.drop_table("store_scraping_pointer")
