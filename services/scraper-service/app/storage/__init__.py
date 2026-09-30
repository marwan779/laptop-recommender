"""Object Storage abstraction and providers for laptop-recommender scraper service."""

from app.storage.base import IObjectStorageService
from app.storage.exceptions import (
    StorageConnectionError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StoragePermissionError,
)
from app.storage.factory import StorageFactory, get_storage_service
from app.storage.models import (
    BatchDeleteResult,
    ObjectMetadata,
    ObjectSummary,
    StorageObject,
)
from app.storage.s3 import S3StorageService

__all__ = [
    "IObjectStorageService",
    "S3StorageService",
    "StorageFactory",
    "get_storage_service",
    "StorageObject",
    "ObjectMetadata",
    "ObjectSummary",
    "BatchDeleteResult",
    "StorageError",
    "StorageNotFoundError",
    "StoragePermissionError",
    "StorageConnectionError",
    "StorageOperationError",
]
