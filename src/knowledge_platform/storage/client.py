"""Asynchronous client implementation for local object storage (MinIO)."""

import mimetypes
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Protocol, Self, runtime_checkable

import aioboto3
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError

from knowledge_platform.config import StorageSettings
from knowledge_platform.storage.exceptions import (
    BucketNotFoundError,
    DocumentNotFoundError,
    StorageConnectionError,
    StorageError,
)
from knowledge_platform.storage.models import DocumentMetadata


@runtime_checkable
class AsyncStorageClientProtocol(Protocol):
    """Asynchronous interface for object storage operations."""

    async def __aenter__(self) -> Self:
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


class AsyncStorageClient:
    """Concrete asynchronous storage client connecting to MinIO via aioboto3."""

    def __init__(self, settings: StorageSettings | None = None) -> None:
        """Initialize storage client with environment configuration."""
        self.settings = settings or StorageSettings()
        self._session = aioboto3.Session()
        self._client_cm: Any = None
        self._client: Any = None

    async def __aenter__(self) -> Self:
        """Open the aioboto3 S3 client session."""
        try:
            self._client_cm = self._session.client(
                "s3",
                endpoint_url=self.settings.endpoint_url,
                aws_access_key_id=self.settings.minio_root_user,
                aws_secret_access_key=self.settings.minio_root_password,
            )
            self._client = await self._client_cm.__aenter__()
            return self
        except (EndpointConnectionError, ConnectionError) as exc:
            raise StorageConnectionError(
                f"Failed to connect to MinIO at {self.settings.endpoint_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise StorageConnectionError(
                f"Storage client session initialization error: {exc}"
            ) from exc

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the underlying client connection resources."""
        if self._client_cm is not None:
            await self._client_cm.__aexit__(exc_type, exc_val, exc_tb)
            self._client = None
            self._client_cm = None

    def _require_client(self) -> Any:
        """Ensure the client session is active."""
        if self._client is None:
            raise StorageError(
                "Storage client is not connected. Use 'async with' context manager."
            )
        return self._client

    async def verify_bucket_exists(self, bucket_name: str) -> bool:
        """Asynchronously verify whether a bucket exists."""
        client = self._require_client()
        try:
            await client.head_bucket(Bucket=bucket_name)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                return False
            raise StorageError(f"Error checking bucket '{bucket_name}': {exc}") from exc
        except (EndpointConnectionError, ConnectionError) as exc:
            raise StorageConnectionError(
                f"Connection error reaching storage service: {exc}"
            ) from exc

    async def list_documents(
        self, bucket_name: str, prefix: str = ""
    ) -> list[DocumentMetadata]:
        """Asynchronously list all documents in the bucket."""
        client = self._require_client()
        if not await self.verify_bucket_exists(bucket_name):
            raise BucketNotFoundError(bucket_name)

        documents: list[DocumentMetadata] = []
        try:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    guessed_type, _ = mimetypes.guess_type(key)
                    content_type = guessed_type or "application/octet-stream"
                    etag = item.get("ETag", "").strip('"')
                    documents.append(
                        DocumentMetadata(
                            key=key,
                            bucket=bucket_name,
                            size_bytes=item["Size"],
                            content_type=content_type,
                            etag=etag,
                            last_modified=item["LastModified"],
                        )
                    )
            return documents
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                raise BucketNotFoundError(bucket_name) from exc
            raise StorageError(
                f"Failed to list documents in bucket '{bucket_name}': {exc}"
            ) from exc
        except (EndpointConnectionError, ConnectionError) as exc:
            raise StorageConnectionError(
                f"Connection error reaching storage service: {exc}"
            ) from exc

    async def get_document_stream(
        self, bucket_name: str, key: str, chunk_size: int = 65536
    ) -> AsyncIterator[bytes]:
        """Asynchronously stream the raw bytes of a document."""
        client = self._require_client()
        try:
            response = await client.get_object(Bucket=bucket_name, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchBucket":
                raise BucketNotFoundError(bucket_name) from exc
            if error_code in ("NoSuchKey", "404"):
                raise DocumentNotFoundError(bucket_name, key) from exc
            raise StorageError(
                f"Failed to get document '{key}' from bucket '{bucket_name}': {exc}"
            ) from exc
        except (EndpointConnectionError, ConnectionError) as exc:
            raise StorageConnectionError(
                f"Connection error reaching storage service: {exc}"
            ) from exc

        body = response["Body"]
        try:
            while True:
                chunk = await body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    async def get_document_bytes(self, bucket_name: str, key: str) -> bytes:
        """Asynchronously retrieve the complete bytes of a document."""
        chunks: list[bytes] = []
        async for chunk in self.get_document_stream(bucket_name, key):
            chunks.append(chunk)
        return b"".join(chunks)

    async def put_document_bytes(
        self,
        bucket_name: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> DocumentMetadata:
        """Upload raw bytes into a bucket (used for test fixtures/seeding)."""
        client = self._require_client()
        if not await self.verify_bucket_exists(bucket_name):
            raise BucketNotFoundError(bucket_name)

        try:
            response = await client.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            etag = response.get("ETag", "").strip('"')
            return DocumentMetadata(
                key=key,
                bucket=bucket_name,
                size_bytes=len(data),
                content_type=content_type,
                etag=etag,
                last_modified=datetime.now(UTC),
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                raise BucketNotFoundError(bucket_name) from exc
            raise StorageError(
                f"Failed to put document '{key}' in bucket '{bucket_name}': {exc}"
            ) from exc
        except (EndpointConnectionError, ConnectionError) as exc:
            raise StorageConnectionError(
                f"Connection error reaching storage service: {exc}"
            ) from exc
