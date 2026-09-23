"""Integration tests for recursive PDF discovery and lifecycle categorization."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from knowledge_platform.config import IngestionSettings, StorageSettings
from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.discovery import DocumentDiscoveryService
from knowledge_platform.ingestion.models import (
    ActionStatus,
    ExecutionRecord,
    ExecutionStatus,
)
from knowledge_platform.storage.client import AsyncStorageClient


@pytest.fixture
def settings() -> IngestionSettings:
    return IngestionSettings()


@pytest.fixture
def storage_settings() -> StorageSettings:
    return StorageSettings()


@pytest.fixture
async def storage_client(
    storage_settings: StorageSettings,
) -> AsyncGenerator[AsyncStorageClient, None]:
    async with AsyncStorageClient(settings=storage_settings) as client:
        yield client


@pytest.fixture
async def mongo_repo(
    settings: IngestionSettings,
) -> AsyncGenerator[MongoRepository, None]:
    client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(settings.mongo_uri)
    # Use a test database to prevent collision
    repo = MongoRepository(client=client, database_name="knowledge_platform_test")
    await repo.initialize_indexes()
    await repo.clear_all_records()
    try:
        yield repo
    finally:
        await repo.clear_all_records()
        client.close()


@pytest.mark.asyncio
async def test_recursive_discovery_and_action_categorization(
    storage_client: AsyncStorageClient,
    mongo_repo: MongoRepository,
    storage_settings: StorageSettings,
) -> None:
    bucket = storage_settings.minio_default_bucket
    test_prefix = f"test-discovery-{uuid4().hex[:8]}"

    # Setup files in MinIO:
    # 2 PDF files (one lowercase, one uppercase .PDF) and 1 non-PDF file (.txt)
    pdf_key_1 = f"{test_prefix}/sub/doc1.pdf"
    pdf_key_2 = f"{test_prefix}/doc2.PDF"
    txt_key = f"{test_prefix}/ignore_me.txt"

    dummy_pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    dummy_txt_content = b"This is a text file that must be ignored."

    await storage_client.put_document_bytes(
        bucket, pdf_key_1, dummy_pdf_content, "application/pdf"
    )
    await storage_client.put_document_bytes(
        bucket, pdf_key_2, dummy_pdf_content, "application/pdf"
    )
    await storage_client.put_document_bytes(
        bucket, txt_key, dummy_txt_content, "text/plain"
    )

    try:
        discovery_service = DocumentDiscoveryService(
            storage_client=storage_client,
            repository=mongo_repo,
        )

        # Execution 1: Initial Discovery
        exec_1 = ExecutionRecord(
            bucket=bucket,
            target_directory=test_prefix,
            status=ExecutionStatus.PENDING,
        )
        await mongo_repo.create_execution(exec_1)

        docs_1, updated_exec_1 = await discovery_service.discover_and_reconcile(
            bucket=bucket,
            directory_prefix=test_prefix,
            execution=exec_1,
        )

        # Assertions for Execution 1
        assert len(docs_1) == 2, (
            "Only 2 PDF files should be discovered (non-PDF ignored)"
        )
        assert updated_exec_1.discovered_count == 2
        assert updated_exec_1.created_count == 2
        assert updated_exec_1.updated_count == 0
        assert updated_exec_1.deleted_count == 0
        assert updated_exec_1.unchanged_count == 0

        doc1_record = await mongo_repo.get_document_by_path(bucket, pdf_key_1)
        assert doc1_record is not None
        assert doc1_record.action_status == ActionStatus.CREATED
        doc1_id = doc1_record.document_id

        doc2_record = await mongo_repo.get_document_by_path(bucket, pdf_key_2)
        assert doc2_record is not None
        assert doc2_record.action_status == ActionStatus.CREATED
        assert doc2_record.file_name == "doc2.PDF"

        # Execution 2: Run again with unchanged files
        exec_2 = ExecutionRecord(
            bucket=bucket,
            target_directory=test_prefix,
            status=ExecutionStatus.PENDING,
        )
        await mongo_repo.create_execution(exec_2)

        _docs_2, updated_exec_2 = await discovery_service.discover_and_reconcile(
            bucket=bucket,
            directory_prefix=test_prefix,
            execution=exec_2,
        )

        assert updated_exec_2.discovered_count == 2
        assert updated_exec_2.created_count == 0
        assert updated_exec_2.unchanged_count == 2
        assert updated_exec_2.deleted_count == 0

        # Execution 3: Modify doc1, delete doc2, and add doc3
        await asyncio.sleep(1.1)  # Ensure last_modified timestamp advances
        updated_content = dummy_pdf_content + b"\n%Updated content"
        await storage_client.put_document_bytes(
            bucket, pdf_key_1, updated_content, "application/pdf"
        )
        await storage_client.delete_document(bucket, pdf_key_2)

        pdf_key_3 = f"{test_prefix}/sub/doc3.pdf"
        await storage_client.put_document_bytes(
            bucket, pdf_key_3, dummy_pdf_content, "application/pdf"
        )

        exec_3 = ExecutionRecord(
            bucket=bucket,
            target_directory=test_prefix,
            status=ExecutionStatus.PENDING,
        )
        await mongo_repo.create_execution(exec_3)

        _docs_3, updated_exec_3 = await discovery_service.discover_and_reconcile(
            bucket=bucket,
            directory_prefix=test_prefix,
            execution=exec_3,
        )

        # Assertions for Execution 3:
        # doc1 is UPDATED (must retain stable document_id!)
        # doc2 is DELETED (file no longer in storage)
        # doc3 is CREATED (new file)
        assert updated_exec_3.discovered_count == 2
        assert updated_exec_3.created_count == 1
        assert updated_exec_3.updated_count == 1
        assert updated_exec_3.deleted_count == 1

        doc1_updated = await mongo_repo.get_document_by_path(bucket, pdf_key_1)
        assert doc1_updated is not None
        assert doc1_updated.action_status == ActionStatus.UPDATED
        assert doc1_updated.document_id == doc1_id, (
            "Updated document MUST retain stable document_id!"
        )

        doc2_deleted = await mongo_repo.get_document_by_path(bucket, pdf_key_2)
        assert doc2_deleted is not None
        assert doc2_deleted.action_status == ActionStatus.DELETED

        doc3_created = await mongo_repo.get_document_by_path(bucket, pdf_key_3)
        assert doc3_created is not None
        assert doc3_created.action_status == ActionStatus.CREATED

    finally:
        # Clean up storage files
        try:
            await storage_client.delete_document(bucket, pdf_key_1)
            await storage_client.delete_document(bucket, txt_key)
            await storage_client.delete_document(bucket, f"{test_prefix}/sub/doc3.pdf")
        except Exception:  # noqa: BLE001, S110
            pass
