"""Discovery and lifecycle categorization of documents in object storage."""

from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

from loguru import logger

from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.models import (
    ActionStatus,
    DocumentProcessingStatus,
    DocumentRecord,
    ExecutionRecord,
    ExecutionStatus,
)
from knowledge_platform.storage.client import AsyncStorageClient


def _to_utc(dt: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC for safe comparisons."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class DocumentDiscoveryService:
    """Discovers PDF files recursively in object storage and reconciles their lifecycle state."""

    def __init__(
        self,
        storage_client: AsyncStorageClient,
        repository: MongoRepository,
    ) -> None:
        self.storage_client = storage_client
        self.repository = repository

    async def discover_and_reconcile(
        self,
        bucket: str,
        directory_prefix: str,
        execution: ExecutionRecord,
    ) -> tuple[list[DocumentRecord], ExecutionRecord]:
        """
        Recursively discover all PDF files under directory_prefix, reconcile against
        MongoDB records, and assign action statuses (created, updated, deleted, unchanged).
        """
        exec_logger = logger.bind(
            execution_id=execution.execution_id,
            bucket=bucket,
            directory=directory_prefix,
        )
        exec_logger.info("Beginning recursive file discovery in object storage...")

        # Normalize prefix: remove leading slash
        clean_prefix = directory_prefix.lstrip("/")

        # List all objects in bucket under prefix
        all_objects = await self.storage_client.list_documents(
            bucket_name=bucket,
            prefix=clean_prefix,
        )

        # Filter for PDF files using case-insensitive extension matching (FR-002)
        discovered_pdfs = [
            obj for obj in all_objects if obj.key.lower().endswith(".pdf")
        ]
        discovered_map = {obj.key: obj for obj in discovered_pdfs}

        exec_logger.info(
            "Found {total} objects total; {pdf_count} are PDF files.",
            total=len(all_objects),
            pdf_count=len(discovered_pdfs),
        )

        # Retrieve all currently tracked documents in MongoDB under this prefix
        existing_docs = await self.repository.list_documents_by_prefix(
            bucket=bucket,
            directory_prefix=clean_prefix,
        )
        existing_map = {doc.storage_path: doc for doc in existing_docs}

        reconciled_documents: list[DocumentRecord] = []
        created_count = 0
        updated_count = 0
        deleted_count = 0
        unchanged_count = 0

        now = datetime.now(UTC)

        # 1. Evaluate all discovered files against existing records
        for key, obj in discovered_map.items():
            file_name = PurePosixPath(key).name
            doc_logger = logger.bind(
                execution_id=execution.execution_id,
                storage_path=key,
                file_name=file_name,
            )

            existing = existing_map.get(key)

            if existing is None or existing.action_status == ActionStatus.DELETED:
                # Newly discovered file
                action = ActionStatus.CREATED
                doc_id = str(uuid4())
                created_count += 1
                doc_logger.info("Classified as CREATED (document_id={id})", id=doc_id)
                doc = DocumentRecord(
                    document_id=doc_id,
                    execution_id=execution.execution_id,
                    bucket=bucket,
                    storage_path=key,
                    file_name=file_name,
                    last_modified=obj.last_modified,
                    size_bytes=obj.size_bytes,
                    action_status=action,
                    processing_status=DocumentProcessingStatus.DISCOVERED,
                    created_at=now,
                    updated_at=now,
                )
            elif _to_utc(obj.last_modified) > _to_utc(existing.last_modified):
                # Modified file - retains stable document_id (FR-005)
                action = ActionStatus.UPDATED
                doc_id = existing.document_id
                updated_count += 1
                doc_logger.info(
                    "Classified as UPDATED (retaining stable document_id={id})",
                    id=doc_id,
                )
                doc = DocumentRecord(
                    document_id=doc_id,
                    execution_id=execution.execution_id,
                    bucket=bucket,
                    storage_path=key,
                    file_name=file_name,
                    last_modified=obj.last_modified,
                    size_bytes=obj.size_bytes,
                    action_status=action,
                    processing_status=DocumentProcessingStatus.DISCOVERED,
                    markdown_storage_path=existing.markdown_storage_path,
                    created_at=existing.created_at,
                    updated_at=now,
                )
            else:
                # Unchanged file - skip re-processing
                action = ActionStatus.UNCHANGED
                unchanged_count += 1
                doc_logger.debug(
                    "Classified as UNCHANGED (document_id={id})",
                    id=existing.document_id,
                )
                doc = existing.model_copy(
                    update={
                        "execution_id": execution.execution_id,
                        "action_status": action,
                        "updated_at": now,
                    }
                )

            reconciled_documents.append(doc)
            await self.repository.upsert_document(doc)

        # 2. Detect deleted files (previously tracked in DB but missing from current scan)
        for key, existing in existing_map.items():
            if (
                key not in discovered_map
                and existing.action_status != ActionStatus.DELETED
            ):
                deleted_count += 1
                doc_logger = logger.bind(
                    execution_id=execution.execution_id,
                    storage_path=key,
                    document_id=existing.document_id,
                )
                doc_logger.info("Classified as DELETED (file no longer in storage)")
                deleted_doc = existing.model_copy(
                    update={
                        "execution_id": execution.execution_id,
                        "action_status": ActionStatus.DELETED,
                        "updated_at": now,
                    }
                )
                reconciled_documents.append(deleted_doc)
                await self.repository.upsert_document(deleted_doc)

        # Update execution record with milestone metrics
        execution.discovered_count = len(discovered_pdfs)
        execution.created_count = created_count
        execution.updated_count = updated_count
        execution.deleted_count = deleted_count
        execution.unchanged_count = unchanged_count
        execution.status = ExecutionStatus.IN_PROGRESS

        await self.repository.update_execution(execution)

        exec_logger.info(
            "Reconciliation complete: {discovered} discovered, {created} created, "
            "{updated} updated, {deleted} deleted, {unchanged} unchanged.",
            discovered=execution.discovered_count,
            created=created_count,
            updated=updated_count,
            deleted=deleted_count,
            unchanged=unchanged_count,
        )

        return reconciled_documents, execution
