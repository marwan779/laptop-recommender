from datetime import datetime, timezone

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["Base", "utcnow"]

