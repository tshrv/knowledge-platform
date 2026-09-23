"""Domain exception hierarchy for document ingestion pipeline."""


class IngestionError(Exception):
    """Base exception for all ingestion pipeline errors."""


class PipelineFatalError(IngestionError):
    """Raised when pipeline-wide infrastructure failures abort execution."""


class DocumentProcessingError(IngestionError):
    """Base exception for document-isolated failures."""

    def __init__(self, document_id: str, storage_path: str, message: str) -> None:
        super().__init__(f"Document {document_id} ({storage_path}) failed: {message}")
        self.document_id = document_id
        self.storage_path = storage_path
        self.message = message


class DocumentParsingError(DocumentProcessingError):
    """Raised when PDF parser fails to parse a corrupted or invalid PDF file."""


class UnparseableDocumentError(DocumentProcessingError):
    """Raised when PDF contains no extractable digital text layers (scanned or image-only)."""


class VectorIndexingError(DocumentProcessingError):
    """Raised when embedding generation or vector store indexing fails for a document."""
