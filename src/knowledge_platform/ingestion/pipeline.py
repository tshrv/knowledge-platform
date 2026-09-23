"""End-to-end ingestion pipeline orchestrator."""

from datetime import UTC, datetime

from loguru import logger

from knowledge_platform.config import IngestionSettings
from knowledge_platform.ingestion.chunker import HierarchicalMarkdownChunker
from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.discovery import DocumentDiscoveryService
from knowledge_platform.ingestion.embeddings import VertexAIEmbeddingClient
from knowledge_platform.ingestion.exceptions import (
    DocumentProcessingError,
    PipelineFatalError,
)
from knowledge_platform.ingestion.models import (
    ActionStatus,
    DocumentProcessingStatus,
    ExecutionRecord,
    ExecutionStatus,
    VectorPayload,
)
from knowledge_platform.ingestion.parser import PdfMarkdownParser
from knowledge_platform.ingestion.vector_store import QdrantVectorStore
from knowledge_platform.storage.client import AsyncStorageClient


class IngestionPipeline:
    """Orchestrates recursive PDF discovery, hierarchical chunking, and vector indexing."""

    def __init__(
        self,
        storage_client: AsyncStorageClient,
        mongo_repo: MongoRepository,
        vector_store: QdrantVectorStore,
        embedding_client: VertexAIEmbeddingClient,
        settings: IngestionSettings | None = None,
    ) -> None:
        self.storage_client = storage_client
        self.mongo_repo = mongo_repo
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.settings = settings or IngestionSettings()
        self.parser = PdfMarkdownParser(
            storage_client=storage_client, repository=mongo_repo
        )
        self.chunker = HierarchicalMarkdownChunker(
            max_chunk_size=1000, chunk_overlap=100
        )

    async def run(
        self,
        directory_path: str = "",
        bucket: str | None = None,
        reset_on_start: bool | None = None,
    ) -> ExecutionRecord:
        """
        Execute an ingestion run over the target object storage directory path.

        Parameters:
            directory_path: Prefix path within the storage bucket (e.g. "reports/")
            bucket: Target bucket name (defaults to configured default bucket)
            reset_on_start: If True, completely purges vector store and DB state before running

        Returns:
            ExecutionRecord: Fully updated execution record with final status and metrics.
        """
        target_bucket = bucket or self.settings.default_bucket
        should_reset = (
            self.settings.ingestion_reset_on_start
            if reset_on_start is None
            else reset_on_start
        )

        exec_record = ExecutionRecord(
            bucket=target_bucket,
            target_directory=directory_path,
            reset_on_start=should_reset,
            status=ExecutionStatus.IN_PROGRESS,
        )

        exec_logger = logger.bind(
            execution_id=exec_record.execution_id,
            bucket=target_bucket,
            directory=directory_path,
        )
        exec_logger.info("Initializing ingestion pipeline execution...")

        # 1. Handle reset_on_start if requested (FR-018, FR-019)
        if should_reset:
            exec_logger.warning(
                "reset_on_start=True: purging all vectors and MongoDB state..."
            )
            try:
                await self.vector_store.recreate_collection()
                await self.mongo_repo.clear_all_records()
            except Exception as e:
                err_msg = f"Fatal error during reset_on_start purge: {e}"
                exec_logger.error(err_msg)
                raise PipelineFatalError(err_msg) from e

        # 2. Ensure infrastructure readiness
        try:
            await self.vector_store.ensure_collection_exists()
            await self.mongo_repo.initialize_indexes()
            await self.mongo_repo.create_execution(exec_record)
        except Exception as e:
            err_msg = f"Failed to verify database or vector store readiness: {e}"
            exec_logger.error(err_msg)
            raise PipelineFatalError(err_msg) from e

        # 3. Discovery and Reconciliation (US1)
        try:
            discovery_service = DocumentDiscoveryService(
                storage_client=self.storage_client,
                repository=self.mongo_repo,
            )
            documents, exec_record = await discovery_service.discover_and_reconcile(
                bucket=target_bucket,
                directory_prefix=directory_path,
                execution=exec_record,
            )
        except Exception as e:
            exec_record.status = ExecutionStatus.FAILED
            exec_record.error_message = f"Discovery phase failed: {e}"
            exec_record.completed_at = datetime.now(UTC)
            await self.mongo_repo.update_execution(exec_record)
            raise PipelineFatalError(f"Discovery phase failed: {e}") from e

        # 4. Sequential Processing Loop for each document (US2, US3, US4)
        for doc in documents:
            doc_logger = logger.bind(
                execution_id=exec_record.execution_id,
                document_id=doc.document_id,
                storage_path=doc.storage_path,
                action=doc.action_status,
            )

            if doc.action_status == ActionStatus.UNCHANGED:
                doc_logger.debug("Skipping unchanged file without re-indexing.")
                continue

            if doc.action_status == ActionStatus.DELETED:
                doc_logger.info("Purging vectors for deleted file from vector store...")
                try:
                    await self.vector_store.delete_vectors_by_document_id(
                        doc.document_id
                    )
                except Exception as e:  # noqa: BLE001
                    doc_logger.error(
                        "Failed to purge vectors for deleted document: {err}",
                        err=str(e),
                    )
                continue

            # Process CREATED or UPDATED documents
            try:
                if doc.action_status == ActionStatus.UPDATED:
                    doc_logger.info(
                        "Purging previous vectors before re-indexing updated document..."
                    )
                    await self.vector_store.delete_vectors_by_document_id(
                        doc.document_id
                    )

                # Step A: Parse PDF to Markdown (US2)
                markdown_text = await self.parser.parse_and_store(doc)
                if not markdown_text:
                    continue

                # Step B: Hierarchical Markdown Chunking (US3)
                chunks = self.chunker.chunk_document(
                    markdown_text=markdown_text,
                    document_id=doc.document_id,
                    source_file_name=doc.file_name,
                    storage_path=doc.storage_path,
                )
                await self.mongo_repo.update_document_processing_status(
                    document_id=doc.document_id,
                    status=DocumentProcessingStatus.CHUNKED,
                    chunk_count=len(chunks),
                )

                # Step C: Generate Embeddings and Index into Qdrant (US4)
                if chunks:
                    texts = [c.text for c in chunks]
                    vectors = await self.embedding_client.embed_texts(
                        texts=texts,
                        document_id=doc.document_id,
                    )
                    chunk_ids = [c.chunk_id for c in chunks]
                    payloads = [
                        VectorPayload(
                            document_id=c.document_id,
                            chunk_id=c.chunk_id,
                            source_file_name=c.source_file_name,
                            storage_path=c.storage_path,
                            chunk_index=c.chunk_index,
                            total_chunks=c.total_chunks,
                            h1=c.h1,
                            h2=c.h2,
                            h3=c.h3,
                            text=c.text,
                        )
                        for c in chunks
                    ]
                    await self.vector_store.upsert_chunk_vectors(
                        document_id=doc.document_id,
                        chunk_ids=chunk_ids,
                        vectors=vectors,
                        payloads=payloads,
                    )

                await self.mongo_repo.update_document_processing_status(
                    document_id=doc.document_id,
                    status=DocumentProcessingStatus.INDEXED,
                )
                doc_logger.info("Document successfully ingested, chunked, and indexed.")

            except DocumentProcessingError as e:
                exec_record.failed_count += 1
                doc_logger.error(
                    "Document processing failure isolated: {err}", err=str(e)
                )
                # Document error status is already captured in MongoDB by the parser
            except Exception as e:  # noqa: BLE001
                exec_record.failed_count += 1
                doc_logger.error(
                    "Unexpected error processing document: {err}", err=str(e)
                )
                await self.mongo_repo.update_document_processing_status(
                    document_id=doc.document_id,
                    status=DocumentProcessingStatus.FAILED,
                    error_message=str(e),
                )

        # 5. Finalize execution metrics and status
        exec_record.completed_at = datetime.now(UTC)
        if exec_record.failed_count > 0:
            exec_record.status = ExecutionStatus.COMPLETED_WITH_ERRORS
        else:
            exec_record.status = ExecutionStatus.COMPLETED

        await self.mongo_repo.update_execution(exec_record)
        exec_logger.info(
            "Execution completed: status={status}, discovered={disc}, created={c}, updated={u}, deleted={d}, failed={f}",
            status=exec_record.status,
            disc=exec_record.discovered_count,
            c=exec_record.created_count,
            u=exec_record.updated_count,
            d=exec_record.deleted_count,
            f=exec_record.failed_count,
        )

        return exec_record
