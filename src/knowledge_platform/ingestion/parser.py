"""Sequential PDF download, parsing, and Markdown conversion service."""

import io

from loguru import logger
from markitdown import MarkItDown

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
from knowledge_platform.storage.client import AsyncStorageClient


class PdfMarkdownParser:
    """Downloads PDFs sequentially, converts them to Markdown, and stores Markdown artifacts."""

    def __init__(
        self,
        storage_client: AsyncStorageClient,
        repository: MongoRepository,
    ) -> None:
        self.storage_client = storage_client
        self.repository = repository
        self._converter = MarkItDown()

    async def parse_and_store(
        self,
        document: DocumentRecord,
    ) -> str | None:
        """
        Process a single document: download bytes, convert to Markdown, store artifact,
        and update document status in MongoDB.

        Returns:
            The generated Markdown text, or None if skipped/failed.
        """
        if document.action_status in (ActionStatus.UNCHANGED, ActionStatus.DELETED):
            return None

        doc_logger = logger.bind(
            execution_id=document.execution_id,
            document_id=document.document_id,
            storage_path=document.storage_path,
        )

        doc_logger.info("Starting sequential download and Markdown conversion...")

        # 1. Download file bytes from object storage
        try:
            pdf_bytes = await self.storage_client.get_document_bytes(
                bucket_name=document.bucket,
                key=document.storage_path,
            )
            await self.repository.update_document_processing_status(
                document_id=document.document_id,
                status=DocumentProcessingStatus.DOWNLOADED,
            )
        except Exception as e:
            err_msg = f"Failed to download object from storage: {e}"
            doc_logger.error(err_msg)
            await self.repository.update_document_processing_status(
                document_id=document.document_id,
                status=DocumentProcessingStatus.FAILED,
                error_message=err_msg,
            )
            raise DocumentParsingError(
                document.document_id, document.storage_path, err_msg
            ) from e

        # 2. Validate PDF signature and convert PDF to Markdown using MarkItDown
        if not pdf_bytes.startswith(b"%PDF-"):
            err_msg = "Invalid PDF signature: file header does not start with %PDF-"
            doc_logger.error(err_msg)
            await self.repository.update_document_processing_status(
                document_id=document.document_id,
                status=DocumentProcessingStatus.FAILED,
                error_message=err_msg,
            )
            raise DocumentParsingError(
                document.document_id, document.storage_path, err_msg
            )

        try:
            conversion_result = self._converter.convert_stream(
                stream=io.BytesIO(pdf_bytes),
                file_extension=".pdf",
            )
            markdown_content = conversion_result.text_content or ""
        except Exception as e:
            err_msg = f"PDF parsing error: {e}"
            doc_logger.error(err_msg)
            await self.repository.update_document_processing_status(
                document_id=document.document_id,
                status=DocumentProcessingStatus.FAILED,
                error_message=err_msg,
            )
            raise DocumentParsingError(
                document.document_id, document.storage_path, err_msg
            ) from e

        # 3. Detect scanned / image-only PDFs lacking extractable text
        if not markdown_content.strip():
            err_msg = "PDF contains no extractable digital text layers (scanned or image-only)."
            doc_logger.warning(err_msg)
            await self.repository.update_document_processing_status(
                document_id=document.document_id,
                status=DocumentProcessingStatus.FAILED,
                error_message=err_msg,
            )
            raise UnparseableDocumentError(
                document.document_id, document.storage_path, err_msg
            )

        # 4. Upload Markdown artifact to object storage under processed/markdown/{document_id}.md
        markdown_key = f"processed/markdown/{document.document_id}.md"
        try:
            await self.storage_client.put_document_bytes(
                bucket_name=document.bucket,
                key=markdown_key,
                data=markdown_content.encode("utf-8"),
                content_type="text/markdown",
            )
        except Exception as e:
            err_msg = f"Failed to persist Markdown artifact in storage: {e}"
            doc_logger.error(err_msg)
            await self.repository.update_document_processing_status(
                document_id=document.document_id,
                status=DocumentProcessingStatus.FAILED,
                error_message=err_msg,
            )
            raise DocumentParsingError(
                document.document_id, document.storage_path, err_msg
            ) from e

        # 5. Update MongoDB state to PARSED with markdown path
        document.markdown_storage_path = markdown_key
        document.processing_status = DocumentProcessingStatus.PARSED
        await self.repository.update_document_processing_status(
            document_id=document.document_id,
            status=DocumentProcessingStatus.PARSED,
            markdown_storage_path=markdown_key,
        )

        doc_logger.info(
            "Successfully parsed PDF and stored Markdown artifact at: {path}",
            path=markdown_key,
        )
        return markdown_content
