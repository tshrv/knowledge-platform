"""Integration tests for PDF parsing, Markdown conversion, and artifact persistence."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from knowledge_platform.config import IngestionSettings, StorageSettings
from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.exceptions import (
    DocumentParsingError,
    UnparseableDocumentError,
)
from knowledge_platform.ingestion.models import (
    ActionStatus,
    DocumentProcessingStatus,
    DocumentRecord,
)
from knowledge_platform.ingestion.parser import PdfMarkdownParser
from knowledge_platform.storage.client import AsyncStorageClient

VALID_PDF_BYTES = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 70 >>
stream
BT
/F1 18 Tf
50 720 Td
(# System Architecture) Tj
0 -30 Td
(This guide documents the ingestion engine.) Tj
ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000365 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
439
%%EOF"""

EMPTY_TEXT_PDF_BYTES = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
185
%%EOF"""

CORRUPT_PDF_BYTES = b"This is clearly not a valid PDF file content"


@pytest.fixture
def storage_settings() -> StorageSettings:
    return StorageSettings()


@pytest.fixture
def ingestion_settings() -> IngestionSettings:
    return IngestionSettings()


@pytest.fixture
async def storage_client(
    storage_settings: StorageSettings,
) -> AsyncGenerator[AsyncStorageClient, None]:
    async with AsyncStorageClient(settings=storage_settings) as client:
        yield client


@pytest.fixture
async def mongo_repo(
    ingestion_settings: IngestionSettings,
) -> AsyncGenerator[MongoRepository, None]:
    client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(
        ingestion_settings.mongo_uri
    )
    repo = MongoRepository(client=client, database_name="knowledge_platform_test")
    await repo.initialize_indexes()
    try:
        yield repo
    finally:
        await repo.clear_all_records()
        client.close()


@pytest.mark.asyncio
async def test_parse_valid_pdf_and_store_markdown(
    storage_client: AsyncStorageClient,
    mongo_repo: MongoRepository,
    storage_settings: StorageSettings,
) -> None:
    bucket = storage_settings.minio_default_bucket
    doc_id = str(uuid4())
    pdf_key = f"test-parser/{doc_id}/valid.pdf"

    await storage_client.put_document_bytes(
        bucket, pdf_key, VALID_PDF_BYTES, "application/pdf"
    )

    doc = DocumentRecord(
        document_id=doc_id,
        execution_id="exec-123",
        bucket=bucket,
        storage_path=pdf_key,
        file_name="valid.pdf",
        last_modified=datetime.now(UTC),
        size_bytes=len(VALID_PDF_BYTES),
        action_status=ActionStatus.CREATED,
    )
    await mongo_repo.upsert_document(doc)

    parser = PdfMarkdownParser(storage_client=storage_client, repository=mongo_repo)
    markdown_result = await parser.parse_and_store(doc)

    assert markdown_result is not None
    assert "# System Architecture" in markdown_result

    # Verify Markdown artifact saved in MinIO under processed/markdown/{document_id}.md
    expected_md_key = f"processed/markdown/{doc_id}.md"
    md_bytes = await storage_client.get_document_bytes(bucket, expected_md_key)
    assert b"# System Architecture" in md_bytes

    # Verify MongoDB record updated
    updated_doc = await mongo_repo.get_document_by_path(bucket, pdf_key)
    assert updated_doc is not None
    assert updated_doc.processing_status == DocumentProcessingStatus.PARSED
    assert updated_doc.markdown_storage_path == expected_md_key

    # Cleanup
    await storage_client.delete_document(bucket, pdf_key)
    await storage_client.delete_document(bucket, expected_md_key)


@pytest.mark.asyncio
async def test_parse_scanned_image_only_pdf_fails_gracefully(
    storage_client: AsyncStorageClient,
    mongo_repo: MongoRepository,
    storage_settings: StorageSettings,
) -> None:
    bucket = storage_settings.minio_default_bucket
    doc_id = str(uuid4())
    pdf_key = f"test-parser/{doc_id}/scanned.pdf"

    await storage_client.put_document_bytes(
        bucket, pdf_key, EMPTY_TEXT_PDF_BYTES, "application/pdf"
    )

    doc = DocumentRecord(
        document_id=doc_id,
        execution_id="exec-123",
        bucket=bucket,
        storage_path=pdf_key,
        file_name="scanned.pdf",
        last_modified=datetime.now(UTC),
        size_bytes=len(EMPTY_TEXT_PDF_BYTES),
        action_status=ActionStatus.CREATED,
    )
    await mongo_repo.upsert_document(doc)

    parser = PdfMarkdownParser(storage_client=storage_client, repository=mongo_repo)

    with pytest.raises(UnparseableDocumentError):
        await parser.parse_and_store(doc)

    updated_doc = await mongo_repo.get_document_by_path(bucket, pdf_key)
    assert updated_doc is not None
    assert updated_doc.processing_status == DocumentProcessingStatus.FAILED
    assert "no extractable digital text" in (updated_doc.error_message or "")

    await storage_client.delete_document(bucket, pdf_key)


@pytest.mark.asyncio
async def test_parse_corrupt_pdf_fails_gracefully(
    storage_client: AsyncStorageClient,
    mongo_repo: MongoRepository,
    storage_settings: StorageSettings,
) -> None:
    bucket = storage_settings.minio_default_bucket
    doc_id = str(uuid4())
    pdf_key = f"test-parser/{doc_id}/corrupt.pdf"

    await storage_client.put_document_bytes(
        bucket, pdf_key, CORRUPT_PDF_BYTES, "application/pdf"
    )

    doc = DocumentRecord(
        document_id=doc_id,
        execution_id="exec-123",
        bucket=bucket,
        storage_path=pdf_key,
        file_name="corrupt.pdf",
        last_modified=datetime.now(UTC),
        size_bytes=len(CORRUPT_PDF_BYTES),
        action_status=ActionStatus.CREATED,
    )
    await mongo_repo.upsert_document(doc)

    parser = PdfMarkdownParser(storage_client=storage_client, repository=mongo_repo)

    with pytest.raises(DocumentParsingError):
        await parser.parse_and_store(doc)

    updated_doc = await mongo_repo.get_document_by_path(bucket, pdf_key)
    assert updated_doc is not None
    assert updated_doc.processing_status == DocumentProcessingStatus.FAILED
    assert updated_doc.error_message is not None

    await storage_client.delete_document(bucket, pdf_key)
