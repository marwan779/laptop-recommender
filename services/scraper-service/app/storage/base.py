from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.storage.models import BatchDeleteResult, ObjectMetadata, ObjectSummary, StorageObject


class IObjectStorageService(ABC):
    """Abstract Base Class defining the contract for object storage providers.

    All storage implementations (AWS S3, MinIO, Google Cloud Storage, Azure Blob,
    or Local Filesystem) must implement this interface to ensure transparent swappability
    and adherence to the Liskov Substitution Principle (LSP).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the object storage provider (e.g. 's3', 'minio', 'local')."""
        pass

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        """The active bucket or container name."""
        pass

    # ── Create / Upload (C) ──────────────────────────────────────────────

    @abstractmethod
    def upload_file(
        self,
        file_path: str | Path,
        object_key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """Upload a local file from disk to object storage."""
        pass

    @abstractmethod
    def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """Upload raw in-memory bytes to object storage."""
        pass

    @abstractmethod
    def upload_json(
        self,
        data: Any,
        object_key: str,
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        """Serialize data to JSON and upload to object storage."""
        pass

    # ── Read / Retrieve (R) ──────────────────────────────────────────────

    @abstractmethod
    def get_object(self, object_key: str) -> StorageObject:
        """Retrieve an object's full payload and metadata from storage."""
        pass

    @abstractmethod
    def read_bytes(self, object_key: str) -> bytes:
        """Fast helper to read raw bytes of an object."""
        pass

    @abstractmethod
    def read_json(self, object_key: str) -> Any:
        """Fast helper to read and deserialize a JSON object from storage."""
        pass

    @abstractmethod
    def download_file(self, object_key: str, destination_path: str | Path) -> Path:
        """Download an object directly to a local filesystem destination."""
        pass

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Check whether an object key exists in the bucket without downloading its payload."""
        pass

    @abstractmethod
    def get_metadata(self, object_key: str) -> ObjectMetadata:
        """Retrieve metadata headers (size, content type, etag, last_modified) for an object."""
        pass

    # ── Update / Copy (U) ────────────────────────────────────────────────

    @abstractmethod
    def copy_object(self, source_key: str, destination_key: str) -> StorageObject:
        """Copy an existing object to a new key within the bucket."""
        pass

    # ── Delete (D) ───────────────────────────────────────────────────────

    @abstractmethod
    def delete_object(self, object_key: str) -> bool:
        """Delete an object from storage."""
        pass

    @abstractmethod
    def delete_objects(self, object_keys: list[str]) -> BatchDeleteResult:
        """Delete multiple objects from storage in a single batch operation."""
        pass

    # ── List / Query ─────────────────────────────────────────────────────

    @abstractmethod
    def list_objects(self, prefix: str = "", max_keys: int = 1000) -> list[ObjectSummary]:
        """List objects in the bucket matching an optional key prefix."""
        pass

    # ── Presigned URLs ───────────────────────────────────────────────────

    @abstractmethod
    def generate_presigned_url(
        self,
        object_key: str,
        expiration_seconds: int = 3600,
        http_method: str = "GET",
    ) -> str:
        """Generate a pre-signed URL for temporary, secure client-side access."""
        pass
