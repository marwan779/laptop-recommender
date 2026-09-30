from datetime import datetime
import json
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ObjectMetadata(BaseModel):
    """Metadata describing a stored object."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    size_bytes: int
    content_type: str = "application/octet-stream"
    etag: str = ""
    last_modified: datetime | None = None
    custom_metadata: dict[str, str] = Field(default_factory=dict)


class StorageObject(BaseModel):
    """Full representation of a retrieved or uploaded storage object including content payload."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    key: str
    bucket: str
    content: bytes
    metadata: ObjectMetadata

    def to_text(self, encoding: str = "utf-8") -> str:
        """Decode payload content to string."""
        return self.content.decode(encoding)

    def to_json(self, encoding: str = "utf-8") -> Any:
        """Parse payload content as JSON."""
        return json.loads(self.to_text(encoding=encoding))


class ObjectSummary(BaseModel):
    """Lightweight summary of a storage object returned by listing operations."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    size_bytes: int
    last_modified: datetime | None = None
    etag: str = ""


class BatchDeleteResult(BaseModel):
    """Result of a batch delete operation."""

    deleted_keys: list[str] = Field(default_factory=list)
    failed_keys: list[dict[str, str]] = Field(default_factory=list)

    @property
    def total_deleted(self) -> int:
        return len(self.deleted_keys)

    @property
    def total_failed(self) -> int:
        return len(self.failed_keys)

    @property
    def is_successful(self) -> bool:
        return len(self.failed_keys) == 0
