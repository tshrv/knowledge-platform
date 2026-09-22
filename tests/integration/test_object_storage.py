"""Integration tests for local object storage and MinIO Web Console."""

import hashlib
import uuid

import httpx
import pytest

from knowledge_platform.config import StorageSettings
from knowledge_platform.storage import (
    AsyncStorageClient,
    BucketNotFoundError,
    DocumentNotFoundError,
    StorageError,
)


@pytest.fixture
def settings() -> StorageSettings:
    """Fixture providing local storage settings."""
    return StorageSettings()


@pytest.mark.asyncio
async def test_minio_web_console_accessible(settings: StorageSettings) -> None:
    """User Story 2: Verify MinIO Web Console is accessible and returns HTTP 200."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
        response = await client.get(settings.console_url)
        assert response.status_code == 200
        assert "minio" in response.text.lower() or "<html" in response.text.lower()


@pytest.mark.asyncio
async def test_default_bucket_provisioned(settings: StorageSettings) -> None:
    """User Story 1: Verify default bucket 'knowledge-source' was auto-provisioned."""
    async with AsyncStorageClient(settings) as client:
        exists = await client.verify_bucket_exists(settings.minio_default_bucket)
        assert exists is True


@pytest.mark.asyncio
async def test_non_existent_bucket_returns_false(settings: StorageSettings) -> None:
    """Verify verify_bucket_exists returns False for an unknown bucket."""
    async with AsyncStorageClient(settings) as client:
        exists = await client.verify_bucket_exists(
            f"non-existent-{uuid.uuid4().hex[:8]}"
        )
        assert exists is False


@pytest.mark.asyncio
async def test_upload_retrieve_and_checksum_match(settings: StorageSettings) -> None:
    """User Story 3: Upload raw document bytes and retrieve with exact checksum parity."""
    sample_key = f"test-docs/sample-{uuid.uuid4().hex}.txt"
    sample_content = (
        b"Knowledge Platform local object storage integration verification payload."
    )
    expected_md5 = hashlib.md5(sample_content).hexdigest()

    async with AsyncStorageClient(settings) as client:
        # Upload document
        metadata = await client.put_document_bytes(
            bucket_name=settings.minio_default_bucket,
            key=sample_key,
            data=sample_content,
            content_type="text/plain",
        )
        assert metadata.key == sample_key
        assert metadata.bucket == settings.minio_default_bucket
        assert metadata.size_bytes == len(sample_content)
        assert metadata.content_type == "text/plain"
        assert metadata.etag == expected_md5

        # Retrieve full document bytes
        downloaded = await client.get_document_bytes(
            bucket_name=settings.minio_default_bucket,
            key=sample_key,
        )
        assert downloaded == sample_content
        assert hashlib.md5(downloaded).hexdigest() == expected_md5


@pytest.mark.asyncio
async def test_document_stream_retrieval(settings: StorageSettings) -> None:
    """User Story 3: Stream document bytes asynchronously in chunks."""
    sample_key = f"test-stream/data-{uuid.uuid4().hex}.bin"
    sample_content = b"0123456789ABCDEF" * 1024  # 16KB
    chunk_size = 512

    async with AsyncStorageClient(settings) as client:
        await client.put_document_bytes(
            bucket_name=settings.minio_default_bucket,
            key=sample_key,
            data=sample_content,
            content_type="application/octet-stream",
        )

        streamed_chunks: list[bytes] = []
        async for chunk in client.get_document_stream(
            bucket_name=settings.minio_default_bucket,
            key=sample_key,
            chunk_size=chunk_size,
        ):
            streamed_chunks.append(chunk)

        reconstructed = b"".join(streamed_chunks)
        assert reconstructed == sample_content
        assert all(0 < len(c) <= chunk_size for c in streamed_chunks)


@pytest.mark.asyncio
async def test_list_documents(settings: StorageSettings) -> None:
    """User Story 3: List documents residing in knowledge-source bucket."""
    unique_prefix = f"list-test-{uuid.uuid4().hex[:8]}"
    key1 = f"{unique_prefix}/file1.md"
    key2 = f"{unique_prefix}/file2.md"

    async with AsyncStorageClient(settings) as client:
        await client.put_document_bytes(
            settings.minio_default_bucket, key1, b"# Doc 1", "text/markdown"
        )
        await client.put_document_bytes(
            settings.minio_default_bucket, key2, b"# Doc 2", "text/markdown"
        )

        docs = await client.list_documents(
            settings.minio_default_bucket, prefix=unique_prefix
        )
        keys = [d.key for d in docs]
        assert key1 in keys
        assert key2 in keys
        for doc in docs:
            assert doc.bucket == settings.minio_default_bucket
            assert doc.size_bytes > 0
            assert doc.etag != ""


@pytest.mark.asyncio
async def test_bucket_not_found_exception(settings: StorageSettings) -> None:
    """Verify BucketNotFoundError is raised for non-existent bucket."""
    invalid_bucket = f"missing-bucket-{uuid.uuid4().hex[:8]}"
    async with AsyncStorageClient(settings) as client:
        with pytest.raises(BucketNotFoundError) as exc_info:
            await client.list_documents(invalid_bucket)
        assert exc_info.value.bucket_name == invalid_bucket

        with pytest.raises(BucketNotFoundError) as exc_info:
            await client.get_document_bytes(invalid_bucket, "any-key")
        assert exc_info.value.bucket_name == invalid_bucket


@pytest.mark.asyncio
async def test_document_not_found_exception(settings: StorageSettings) -> None:
    """Verify DocumentNotFoundError is raised for non-existent object key."""
    missing_key = f"missing-file-{uuid.uuid4().hex}.pdf"
    async with AsyncStorageClient(settings) as client:
        with pytest.raises(DocumentNotFoundError) as exc_info:
            await client.get_document_bytes(settings.minio_default_bucket, missing_key)
        assert exc_info.value.bucket_name == settings.minio_default_bucket
        assert exc_info.value.key == missing_key


@pytest.mark.asyncio
async def test_client_context_manager_requirement(settings: StorageSettings) -> None:
    """Verify calling client methods outside async context manager raises StorageError."""
    client = AsyncStorageClient(settings)
    with pytest.raises(StorageError):
        await client.verify_bucket_exists("any-bucket")


@pytest.mark.asyncio
async def test_data_persistence_across_restart(settings: StorageSettings) -> None:
    """SC-005: Verify uploaded documents in knowledge-source persist across container restart."""
    import asyncio

    persistence_key = f"persistence-test/doc-{uuid.uuid4().hex}.txt"
    payload = b"Persisted content across MinIO container restart verification."

    async with AsyncStorageClient(settings) as client:
        await client.put_document_bytes(
            settings.minio_default_bucket,
            persistence_key,
            payload,
            "text/plain",
        )

    # Restart the MinIO container
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "restart",
        "minio",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    assert proc.returncode == 0

    # Brief delay for MinIO socket to reopen
    await asyncio.sleep(2)

    async with AsyncStorageClient(settings) as client:
        content = await client.get_document_bytes(
            settings.minio_default_bucket,
            persistence_key,
        )
        assert content == payload
