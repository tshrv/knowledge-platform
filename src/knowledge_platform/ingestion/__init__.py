"""Document ingestion pipeline package."""

from knowledge_platform.config import IngestionSettings
from knowledge_platform.ingestion.chunker import HierarchicalMarkdownChunker
from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.discovery import DocumentDiscoveryService
from knowledge_platform.ingestion.embeddings import VertexAIEmbeddingClient
from knowledge_platform.ingestion.exceptions import (
    DocumentParsingError,
    DocumentProcessingError,
    IngestionError,
    PipelineFatalError,
    UnparseableDocumentError,
    VectorIndexingError,
)
from knowledge_platform.ingestion.models import (
    ActionStatus,
    DocumentChunk,
    DocumentProcessingStatus,
    DocumentRecord,
    ExecutionRecord,
    ExecutionStatus,
    VectorPayload,
)
from knowledge_platform.ingestion.parser import PdfMarkdownParser
from knowledge_platform.ingestion.pipeline import IngestionPipeline
from knowledge_platform.ingestion.vector_store import QdrantVectorStore

__all__ = [
    "ActionStatus",
    "DocumentChunk",
    "DocumentDiscoveryService",
    "DocumentParsingError",
    "DocumentProcessingError",
    "DocumentProcessingStatus",
    "DocumentRecord",
    "ExecutionRecord",
    "ExecutionStatus",
    "HierarchicalMarkdownChunker",
    "IngestionError",
    "IngestionPipeline",
    "IngestionSettings",
    "MongoRepository",
    "PdfMarkdownParser",
    "PipelineFatalError",
    "QdrantVectorStore",
    "UnparseableDocumentError",
    "VectorIndexingError",
    "VectorPayload",
    "VertexAIEmbeddingClient",
]
