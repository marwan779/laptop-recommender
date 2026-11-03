from datetime import UTC, datetime

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = ["Base", "utcnow"]
