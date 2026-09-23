"""Asynchronous MongoDB repository for execution and document lifecycle state."""

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from knowledge_platform.ingestion.models import (
    DocumentProcessingStatus,
    DocumentRecord,
    ExecutionRecord,
)


class MongoRepository:
    """Manages persistence and retrieval of execution and document records in MongoDB."""

    def __init__(
        self,
        client: AsyncIOMotorClient[dict[str, Any]],
        database_name: str = "knowledge_platform",
    ) -> None:
        self.client = client
        self.db: AsyncIOMotorDatabase[dict[str, Any]] = client[database_name]
        self.executions = self.db["executions"]
        self.documents = self.db["documents"]

    async def initialize_indexes(self) -> None:
        """Create required indexes for executions and documents collections."""
        execution_indexes = [
            IndexModel(
                [("execution_id", ASCENDING)], unique=True, name="uniq_execution_id"
            ),
            IndexModel([("started_at", DESCENDING)], name="idx_started_at"),
        ]
        await self.executions.create_indexes(execution_indexes)

        document_indexes = [
            IndexModel(
                [("bucket", ASCENDING), ("storage_path", ASCENDING)],
                unique=True,
                name="uniq_bucket_storage_path",
            ),
            IndexModel([("execution_id", ASCENDING)], name="idx_doc_execution_id"),
            IndexModel(
                [("document_id", ASCENDING)], unique=True, name="uniq_document_id"
            ),
            IndexModel([("action_status", ASCENDING)], name="idx_action_status"),
        ]
        await self.documents.create_indexes(document_indexes)
        logger.info("MongoDB indexes successfully initialized.")

    async def create_execution(self, execution: ExecutionRecord) -> ExecutionRecord:
        """Insert a new execution record."""
        doc = execution.model_dump(by_alias=True, mode="python")
        await self.executions.insert_one(doc)
        logger.bind(execution_id=execution.execution_id).info(
            "Created new execution record for directory: {dir}",
            dir=execution.target_directory,
        )
        return execution

    async def update_execution(self, execution: ExecutionRecord) -> None:
        """Update an existing execution record with latest metrics and status."""
        doc = execution.model_dump(by_alias=True, mode="python")
        await self.executions.replace_one(
            {"execution_id": execution.execution_id}, doc, upsert=True
        )
        logger.bind(execution_id=execution.execution_id).info(
            "Updated execution status to: {status}",
            status=execution.status,
        )

    async def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        """Retrieve an execution record by execution_id."""
        doc = await self.executions.find_one({"execution_id": execution_id})
        if not doc:
            return None
        return ExecutionRecord.model_validate(doc)

    async def get_document_by_path(
        self, bucket: str, storage_path: str
    ) -> DocumentRecord | None:
        """Retrieve a document record by bucket and storage path."""
        doc = await self.documents.find_one(
            {"bucket": bucket, "storage_path": storage_path}
        )
        if not doc:
            return None
        return DocumentRecord.model_validate(doc)

    async def list_documents_by_prefix(
        self, bucket: str, directory_prefix: str
    ) -> list[DocumentRecord]:
        """List all tracked documents residing under a given directory prefix."""
        regex_pattern = f"^{directory_prefix}"
        cursor = self.documents.find(
            {"bucket": bucket, "storage_path": {"$regex": regex_pattern}}
        )
        docs: list[DocumentRecord] = []
        async for doc in cursor:
            docs.append(DocumentRecord.model_validate(doc))
        return docs

    async def upsert_document(self, document: DocumentRecord) -> None:
        """Insert or update a document record keyed by bucket and storage_path."""
        doc = document.model_dump(by_alias=True, mode="python")
        await self.documents.replace_one(
            {"bucket": document.bucket, "storage_path": document.storage_path},
            doc,
            upsert=True,
        )
        logger.bind(
            execution_id=document.execution_id,
            document_id=document.document_id,
            storage_path=document.storage_path,
        ).info(
            "Upserted document record with action status: {action}",
            action=document.action_status,
        )

    async def update_document_processing_status(
        self,
        document_id: str,
        status: DocumentProcessingStatus,
        markdown_storage_path: str | None = None,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update internal processing milestone fields on a document."""
        update_fields: dict[str, Any] = {
            "processing_status": status,
            "updated_at": datetime.now(UTC),
        }
        if markdown_storage_path is not None:
            update_fields["markdown_storage_path"] = markdown_storage_path
        if chunk_count is not None:
            update_fields["chunk_count"] = chunk_count
        if error_message is not None:
            update_fields["error_message"] = error_message

        await self.documents.update_one(
            {"document_id": document_id},
            {"$set": update_fields},
        )
        logger.bind(document_id=document_id).debug(
            "Updated document processing status to: {status}",
            status=status,
        )

    async def clear_all_records(self) -> None:
        """Drop/clear all documents and executions collections (for reset_on_start)."""
        await self.documents.delete_many({})
        await self.executions.delete_many({})
        logger.warning(
            "MongoDB collections 'documents' and 'executions' cleared for fresh start."
        )
