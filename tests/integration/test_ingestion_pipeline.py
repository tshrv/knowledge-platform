"""Comprehensive end-to-end integration tests for the Ingestion Pipeline."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import AsyncQdrantClient

from knowledge_platform.config import IngestionSettings, StorageSettings
from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.embeddings import VertexAIEmbeddingClient
from knowledge_platform.ingestion.models import (
    ActionStatus,
    DocumentProcessingStatus,
    ExecutionStatus,
)
from knowledge_platform.ingestion.pipeline import IngestionPipeline
from knowledge_platform.ingestion.vector_store import QdrantVectorStore
from knowledge_platform.storage.client import AsyncStorageClient

VALID_PDF_1 = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 85 >>
stream
BT
/F1 18 Tf
50 720 Td
(# Getting Started) Tj
0 -30 Td
(Welcome to the automated knowledge ingestion platform.) Tj
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
0000000380 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
454
%%EOF"""

VALID_PDF_2 = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 75 >>
stream
BT
/F1 18 Tf
50 720 Td
(## API Reference) Tj
0 -30 Td
(Details about public endpoints and models.) Tj
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
0000000370 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
444
%%EOF"""

SCANNED_EMPTY_PDF = b"""%PDF-1.4
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
async def test_env(
    ingestion_settings: IngestionSettings,
) -> AsyncGenerator[dict[str, Any], None]:
    suffix = uuid4().hex[:8]
    test_db = f"test_db_{suffix}"
    test_collection = f"test_coll_{suffix}"

    mongo_client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(
        ingestion_settings.mongo_uri
    )
    qdrant_client = AsyncQdrantClient(
        url=ingestion_settings.qdrant_url, check_compatibility=False
    )

    mongo_repo = MongoRepository(client=mongo_client, database_name=test_db)
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=test_collection,
        vector_size=768,
    )
    embedding_client = VertexAIEmbeddingClient(
        api_key=ingestion_settings.vertex_api_key,
        model_name=ingestion_settings.vertex_embedding_model,
        dimension=768,
        batch_size=ingestion_settings.vertex_batch_size,
    )

    await mongo_repo.initialize_indexes()
    await vector_store.ensure_collection_exists()

    try:
        yield {
            "mongo_repo": mongo_repo,
            "vector_store": vector_store,
            "embedding_client": embedding_client,
            "mongo_client": mongo_client,
            "qdrant_client": qdrant_client,
            "test_db": test_db,
            "test_collection": test_collection,
        }
    finally:
        await mongo_repo.clear_all_records()
        mongo_client.close()
        try:
            await qdrant_client.delete_collection(test_collection)
        except Exception:  # noqa: BLE001, S110
            pass
        await qdrant_client.close()


@pytest.mark.asyncio
async def test_full_pipeline_lifecycle_end_to_end(
    storage_client: AsyncStorageClient,
    test_env: dict[str, Any],
    storage_settings: StorageSettings,
    ingestion_settings: IngestionSettings,
) -> None:
    bucket = storage_settings.minio_default_bucket
    prefix = f"pipeline-test-{uuid4().hex[:8]}"

    file1_key = f"{prefix}/docs/guide.pdf"
    file2_key = f"{prefix}/api.PDF"  # test case-insensitive matching
    ignore_key = f"{prefix}/notes.txt"

    await storage_client.put_document_bytes(
        bucket, file1_key, VALID_PDF_1, "application/pdf"
    )
    await storage_client.put_document_bytes(
        bucket, file2_key, VALID_PDF_2, "application/pdf"
    )
    await storage_client.put_document_bytes(
        bucket, ignore_key, b"Plain text note", "text/plain"
    )

    pipeline = IngestionPipeline(
        storage_client=storage_client,
        mongo_repo=test_env["mongo_repo"],
        vector_store=test_env["vector_store"],
        embedding_client=test_env["embedding_client"],
        settings=ingestion_settings,
    )

    try:
        # Run 1: Initial Ingestion
        exec_1 = await pipeline.run(
            directory_path=prefix, bucket=bucket, reset_on_start=False
        )

        assert exec_1.status == ExecutionStatus.COMPLETED
        assert exec_1.discovered_count == 2
        assert exec_1.created_count == 2
        assert exec_1.failed_count == 0

        # Verify Document 1 in MongoDB & MinIO
        doc1 = await test_env["mongo_repo"].get_document_by_path(bucket, file1_key)
        assert doc1 is not None
        assert doc1.action_status == ActionStatus.CREATED
        assert doc1.processing_status == DocumentProcessingStatus.INDEXED
        assert doc1.markdown_storage_path == f"processed/markdown/{doc1.document_id}.md"

        # Verify Document 1 vectors in Qdrant
        points1 = await test_env["vector_store"].get_points_by_document_id(
            doc1.document_id
        )
        assert len(points1) > 0
        assert points1[0].payload["source_file_name"] == "guide.pdf"
        assert points1[0].payload["h1"] == "Getting Started"

        # Verify Document 2 vectors in Qdrant
        doc2 = await test_env["mongo_repo"].get_document_by_path(bucket, file2_key)
        assert doc2 is not None
        points2 = await test_env["vector_store"].get_points_by_document_id(
            doc2.document_id
        )
        assert len(points2) > 0
        assert points2[0].payload["source_file_name"] == "api.PDF"
        assert points2[0].payload["h2"] == "API Reference"

        # Run 2: Re-run with unchanged files
        exec_2 = await pipeline.run(
            directory_path=prefix, bucket=bucket, reset_on_start=False
        )
        assert exec_2.status == ExecutionStatus.COMPLETED
        assert exec_2.discovered_count == 2
        assert exec_2.unchanged_count == 2
        assert exec_2.created_count == 0

        # Run 3: Modify doc1, delete doc2
        await asyncio.sleep(1.1)
        updated_pdf_1 = VALID_PDF_1 + b"\n%Updated section text"
        await storage_client.put_document_bytes(
            bucket, file1_key, updated_pdf_1, "application/pdf"
        )
        await storage_client.delete_document(bucket, file2_key)

        exec_3 = await pipeline.run(
            directory_path=prefix, bucket=bucket, reset_on_start=False
        )
        assert exec_3.status == ExecutionStatus.COMPLETED
        assert exec_3.discovered_count == 1
        assert exec_3.updated_count == 1
        assert exec_3.deleted_count == 1

        # Check doc1 updated with stable document_id
        doc1_updated = await test_env["mongo_repo"].get_document_by_path(
            bucket, file1_key
        )
        assert doc1_updated is not None
        assert doc1_updated.document_id == doc1.document_id, (
            "document_id MUST remain stable across updates!"
        )
        assert doc1_updated.action_status == ActionStatus.UPDATED

        # Check doc2 vectors purged
        doc2_count = await test_env["vector_store"].count_vectors_by_document_id(
            doc2.document_id
        )
        assert doc2_count == 0, (
            "Deleted document vectors MUST be completely purged from Qdrant!"
        )

    finally:
        try:
            await storage_client.delete_document(bucket, file1_key)
            await storage_client.delete_document(bucket, ignore_key)
            if doc1 and doc1.markdown_storage_path:
                await storage_client.delete_document(bucket, doc1.markdown_storage_path)
            if doc2 and doc2.markdown_storage_path:
                await storage_client.delete_document(bucket, doc2.markdown_storage_path)
        except Exception:  # noqa: BLE001, S110
            pass


@pytest.mark.asyncio
async def test_error_isolation_with_scanned_pdf(
    storage_client: AsyncStorageClient,
    test_env: dict[str, Any],
    storage_settings: StorageSettings,
    ingestion_settings: IngestionSettings,
) -> None:
    bucket = storage_settings.minio_default_bucket
    prefix = f"error-test-{uuid4().hex[:8]}"

    good_key = f"{prefix}/valid.pdf"
    bad_key = f"{prefix}/scanned_no_text.pdf"

    await storage_client.put_document_bytes(
        bucket, good_key, VALID_PDF_1, "application/pdf"
    )
    await storage_client.put_document_bytes(
        bucket, bad_key, SCANNED_EMPTY_PDF, "application/pdf"
    )

    pipeline = IngestionPipeline(
        storage_client=storage_client,
        mongo_repo=test_env["mongo_repo"],
        vector_store=test_env["vector_store"],
        embedding_client=test_env["embedding_client"],
        settings=ingestion_settings,
    )

    try:
        exec_res = await pipeline.run(
            directory_path=prefix, bucket=bucket, reset_on_start=False
        )

        # Scanned PDF failed, but valid PDF succeeded!
        # Overall status should be COMPLETED_WITH_ERRORS (SC-009)
        assert exec_res.status == ExecutionStatus.COMPLETED_WITH_ERRORS
        assert exec_res.discovered_count == 2
        assert exec_res.created_count == 2
        assert exec_res.failed_count == 1

        bad_doc = await test_env["mongo_repo"].get_document_by_path(bucket, bad_key)
        assert bad_doc is not None
        assert bad_doc.processing_status == DocumentProcessingStatus.FAILED
        assert "no extractable digital text" in (bad_doc.error_message or "")

        good_doc = await test_env["mongo_repo"].get_document_by_path(bucket, good_key)
        assert good_doc is not None
        assert good_doc.processing_status == DocumentProcessingStatus.INDEXED

    finally:
        try:
            await storage_client.delete_document(bucket, good_key)
            await storage_client.delete_document(bucket, bad_key)
            if good_doc and good_doc.markdown_storage_path:
                await storage_client.delete_document(
                    bucket, good_doc.markdown_storage_path
                )
        except Exception:  # noqa: BLE001, S110
            pass
