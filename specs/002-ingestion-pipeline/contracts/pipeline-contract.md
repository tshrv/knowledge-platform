# Service Contract: Ingestion Pipeline Orchestrator

**Feature**: `002-ingestion-pipeline`  
**Date**: 2026-09-22  
**Status**: Completed  

---

## 1. Overview

This contract defines the public programmatic interface, domain exception hierarchy, and runtime configuration settings for the Ingestion Pipeline orchestrator.

---

## 2. Configuration Settings (`IngestionSettings`)

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    """Configuration settings for Ingestion Pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # MongoDB Settings
    mongo_host: str = Field(default="localhost", alias="MONGO_HOST")
    mongo_port: int = Field(default=27017, alias="MONGO_PORT")
    mongo_root_user: str = Field(default="admin", alias="MONGO_ROOT_USER")
    mongo_root_password: str = Field(default="mongoadmin123", alias="MONGO_ROOT_PASSWORD")
    mongo_database: str = Field(default="knowledge_platform", alias="MONGO_DATABASE")

    # Qdrant Settings
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_collection_name: str = Field(
        default="document_chunks", alias="QDRANT_COLLECTION_NAME"
    )

    # Vertex AI Settings
    vertex_api_key: str = Field(default="", alias="VERTEX_API_KEY")
    vertex_embedding_model: str = Field(
        default="gemini-embedding-001", alias="VERTEX_EMBEDDING_MODEL"
    )
    vertex_batch_size: int = Field(
        default=50, ge=1, le=100, alias="VERTEX_BATCH_SIZE"
    )
    vertex_max_retries: int = Field(
        default=3, ge=1, le=10, alias="VERTEX_MAX_RETRIES"
    )
    vertex_retry_base_delay: float = Field(
        default=1.0, ge=0.1, alias="VERTEX_RETRY_BASE_DELAY"
    )

    # Ingestion Behavior
    ingestion_reset_on_start: bool = Field(
        default=False, alias="INGESTION_RESET_ON_START"
    )

    @property
    def mongo_uri(self) -> str:
        return f"mongodb://{self.mongo_root_user}:{self.mongo_root_password}@{self.mongo_host}:{self.mongo_port}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
```

---

## 3. Public Service Interface (`IngestionPipeline`)

```python
class IngestionPipeline:
    """Orchestrates recursive PDF discovery, hierarchical chunking, and vector indexing."""

    def __init__(
        self,
        storage_client: StorageClient,
        mongo_client: AsyncIOMotorClient,
        qdrant_client: AsyncQdrantClient,
        settings: IngestionSettings,
    ) -> None:
        """Initialize pipeline with injected client dependencies."""
        ...

    async def run(
        self,
        directory_path: str = "",
        bucket: Optional[str] = None,
        reset_on_start: Optional[bool] = None,
    ) -> ExecutionRecord:
        """
        Execute an ingestion run over the target object storage path.

        Parameters:
            directory_path: Path prefix within the bucket (e.g. "manuals/hr/")
            bucket: Target bucket name (defaults to settings / knowledge-source)
            reset_on_start: If True, completely purges vector collection and document state before scanning

        Returns:
            ExecutionRecord: Fully populated execution record with final status and metrics

        Raises:
            PipelineFatalError: If foundational infrastructure (MinIO, Mongo, Qdrant) is unreachable
        """
        ...
```

---

## 4. Domain Exception Hierarchy

```python
class IngestionError(Exception):
    """Base domain exception for all ingestion failures."""
    pass


class PipelineFatalError(IngestionError):
    """Raised when pipeline-wide infrastructure failure aborts execution."""
    pass


class DocumentProcessingError(IngestionError):
    """Base exception for document-isolated failures."""
    def __init__(self, document_id: str, storage_path: str, message: str) -> None:
        super().__init__(f"Document {document_id} ({storage_path}) failed: {message}")
        self.document_id = document_id
        self.storage_path = storage_path


class DocumentParsingError(DocumentProcessingError):
    """Raised when PDF parser fails to parse corrupted or invalid PDF file."""
    pass


class UnparseableDocumentError(DocumentProcessingError):
    """Raised when PDF contains no extractable digital text layers (scanned / image-only)."""
    pass


class VectorIndexingError(DocumentProcessingError):
    """Raised when embedding generation or Qdrant point persistence fails for a document."""
    pass
```
