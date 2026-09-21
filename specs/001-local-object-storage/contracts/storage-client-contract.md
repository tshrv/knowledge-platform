# Interface Contract: Object Storage Python Client (Async)

**Feature**: `001-local-object-storage`  
**Target Module**: `src/knowledge_platform/storage/client.py`  
**Status**: Completed & Refined  

---

## 1. Overview
Defines the asynchronous programmatic contract for interacting with the local object storage service. Used by downstream services (document ingestion, chunking, indexing) to verify bucket readiness, list source documents, and stream document contents without blocking the Python asyncio event loop.

---

## 2. Pydantic Response Models

```python
from datetime import datetime
from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata describing an object in the knowledge-source bucket."""

    key: str = Field(..., description="Object key or filename")
    bucket: str = Field(..., description="Parent bucket name")
    size_bytes: int = Field(..., ge=0, description="Size of document in bytes")
    content_type: str = Field(
        ..., description="Detected MIME content type of document"
    )
    etag: str = Field(..., description="ETag / MD5 content checksum")
    last_modified: datetime = Field(
        ..., description="Last modification timestamp in UTC"
    )


class BucketStatus(BaseModel):
    """Status report for a verified storage bucket."""

    name: str = Field(..., description="Bucket name")
    exists: bool = Field(..., description="Whether the bucket currently exists")
    total_objects: int = Field(
        default=0, ge=0, description="Number of objects present in bucket"
    )
```

---

## 3. Domain Exception Hierarchy

Domain exceptions prevent raw underlying transport and client errors (e.g. `botocore.exceptions.ClientError`) from leaking across architectural boundaries, ensuring adherence to Constitution Principle I.

```python
class StorageError(Exception):
    """Base exception for all storage client errors."""

    pass


class StorageConnectionError(StorageError):
    """Raised when connection to MinIO fails or times out."""

    pass


class BucketNotFoundError(StorageError):
    """Raised when the specified bucket does not exist."""

    def __init__(self, bucket_name: str, message: str | None = None) -> None:
        super().__init__(message or f"Bucket '{bucket_name}' not found.")
        self.bucket_name = bucket_name


class DocumentNotFoundError(StorageError):
    """Raised when the specified object key does not exist in the bucket."""

    def __init__(
        self, bucket_name: str, key: str, message: str | None = None
    ) -> None:
        super().__init__(
            message or f"Document '{key}' not found in bucket '{bucket_name}'."
        )
        self.bucket_name = bucket_name
        self.key = key
```

---

## 4. Protocol Definition: `AsyncStorageClientProtocol`

```python
from typing import Protocol, runtime_checkable
from collections.abc import AsyncIterator
from types import TracebackType


@runtime_checkable
class AsyncStorageClientProtocol(Protocol):
    """Asynchronous interface for object storage operations."""

    async def __aenter__(self) -> "AsyncStorageClientProtocol":
        """Initialize and open the underlying aioboto3 session resources.
        
        Raises:
            StorageConnectionError: If session initialization fails.
        """
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Clean up underlying connections and resources."""
        ...

    async def verify_bucket_exists(self, bucket_name: str) -> bool:
        """Asynchronously check if a specific bucket exists in the storage cluster.
        
        Raises:
            StorageConnectionError: If MinIO is unreachable.
        """
        ...

    async def list_documents(
        self, bucket_name: str, prefix: str = ""
    ) -> list[DocumentMetadata]:
        """Asynchronously list all documents residing in the specified bucket.
        
        Raises:
            BucketNotFoundError: If bucket_name does not exist.
            StorageConnectionError: If MinIO is unreachable.
        """
        ...

    async def get_document_stream(
        self, bucket_name: str, key: str, chunk_size: int = 65536
    ) -> AsyncIterator[bytes]:
        """Asynchronously stream the raw bytes of a document from the bucket.
        
        Raises:
            BucketNotFoundError: If bucket_name does not exist.
            DocumentNotFoundError: If key does not exist in the bucket.
            StorageConnectionError: If MinIO is unreachable.
        """
        ...

    async def get_document_bytes(self, bucket_name: str, key: str) -> bytes:
        """Asynchronously retrieve complete byte contents of a document.
        
        Raises:
            BucketNotFoundError: If bucket_name does not exist.
            DocumentNotFoundError: If key does not exist in the bucket.
            StorageConnectionError: If MinIO is unreachable.
        """
        ...

    async def put_document_bytes(
        self,
        bucket_name: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> DocumentMetadata:
        """Upload raw bytes into a bucket (primarily for testing and synthetic seeding).
        
        Raises:
            BucketNotFoundError: If bucket_name does not exist.
            StorageConnectionError: If MinIO is unreachable.
        """
        ...
```
