import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class StoreScrapingPointer(Base):
    """Current live scraping watermark and checkpoint for each store."""

    __tablename__ = "store_scraping_pointer"

    store_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    store_name: Mapped[str] = mapped_column(String(100))
    store_domain: Mapped[str | None] = mapped_column(String(100))
    latest_pointers: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    last_scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    total_active_offers: Mapped[int] = mapped_column(Integer, default=0)
    scrape_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ScrapingBatchLog(Base):
    """Historical audit trail of all ingestion batches, crawler runs, and price monitor jobs."""

    __tablename__ = "scraping_batch_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_key: Mapped[str] = mapped_column(String(50), index=True)
    trigger_type: Mapped[str] = mapped_column(String(30), default="CRON")
    status: Mapped[str] = mapped_column(String(20), default="STARTED")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(8, 2))

    items_scraped: Mapped[int] = mapped_column(Integer, default=0)
    new_laptops_added: Mapped[int] = mapped_column(Integer, default=0)
    offers_updated: Mapped[int] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, default=0)

    pointers_sent: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    pointers_received: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    error_message: Mapped[str | None] = mapped_column(Text)


__all__ = ["StoreScrapingPointer", "ScrapingBatchLog"]
