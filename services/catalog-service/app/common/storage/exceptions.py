class StorageError(Exception):
    """Base exception for all object storage operations."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class StorageNotFoundError(StorageError):
    """Raised when an object or bucket cannot be found."""

    def __init__(
        self, message: str, key: str | None = None, bucket: str | None = None, original_error: Exception | None = None
    ):
        super().__init__(message, original_error=original_error)
        self.key = key
        self.bucket = bucket


class StoragePermissionError(StorageError):
    """Raised when access is denied or authentication credentials are invalid."""

    def __init__(
        self, message: str, key: str | None = None, bucket: str | None = None, original_error: Exception | None = None
    ):
        super().__init__(message, original_error=original_error)
        self.key = key
        self.bucket = bucket


class StorageConnectionError(StorageError):
    """Raised when connecting to the storage provider endpoint fails."""

    def __init__(self, message: str, endpoint: str | None = None, original_error: Exception | None = None):
        super().__init__(message, original_error=original_error)
        self.endpoint = endpoint


class StorageOperationError(StorageError):
    """Raised when a storage operation (upload, download, copy, delete) fails."""

    def __init__(self, message: str, key: str | None = None, original_error: Exception | None = None):
        super().__init__(message, original_error=original_error)
        self.key = key
