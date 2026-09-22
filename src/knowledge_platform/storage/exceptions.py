"""Domain exception hierarchy for object storage operations."""


class StorageError(Exception):
    """Base exception for all storage client errors."""


class StorageConnectionError(StorageError):
    """Raised when connection to MinIO fails or times out."""


class BucketNotFoundError(StorageError):
    """Raised when the specified bucket does not exist."""

    def __init__(self, bucket_name: str, message: str | None = None) -> None:
        super().__init__(message or f"Bucket '{bucket_name}' not found.")
        self.bucket_name = bucket_name


class DocumentNotFoundError(StorageError):
    """Raised when the specified object key does not exist in the bucket."""

    def __init__(self, bucket_name: str, key: str, message: str | None = None) -> None:
        super().__init__(
            message or f"Document '{key}' not found in bucket '{bucket_name}'."
        )
        self.bucket_name = bucket_name
        self.key = key
