"""Configuration settings for knowledge platform services."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Configuration settings for local MinIO object storage."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    minio_root_user: str = Field(
        default="admin",
        min_length=3,
        alias="MINIO_ROOT_USER",
        description="Root administrative username for MinIO",
    )
    minio_root_password: str = Field(
        default="minioadmin123",
        min_length=8,
        alias="MINIO_ROOT_PASSWORD",
        description="Root administrative password for MinIO",
    )
    minio_host: str = Field(
        default="localhost",
        alias="MINIO_HOST",
        description="Hostname or container network alias for MinIO service",
    )
    minio_port: int = Field(
        default=9000,
        ge=1024,
        le=65535,
        alias="MINIO_PORT",
        description="Port for S3 API endpoint",
    )
    minio_console_port: int = Field(
        default=9001,
        ge=1024,
        le=65535,
        alias="MINIO_CONSOLE_PORT",
        description="Port for MinIO Web Console",
    )
    minio_default_bucket: str = Field(
        default="knowledge-source",
        pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$",
        alias="MINIO_DEFAULT_BUCKET",
        description="Canonical default bucket for source documents",
    )

    @property
    def endpoint_url(self) -> str:
        """Construct the local S3 endpoint URL."""
        return f"http://{self.minio_host}:{self.minio_port}"

    @property
    def console_url(self) -> str:
        """Construct the local web console URL."""
        return f"http://{self.minio_host}:{self.minio_console_port}"


class IngestionSettings(BaseSettings):
    """Configuration settings for document ingestion pipeline, MongoDB, Qdrant, and Vertex AI."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # MongoDB Settings
    mongo_host: str = Field(
        default="localhost",
        alias="MONGO_HOST",
        description="MongoDB server hostname or container alias",
    )
    mongo_port: int = Field(
        default=27017,
        ge=1024,
        le=65535,
        alias="MONGO_PORT",
        description="MongoDB port",
    )
    mongo_root_user: str = Field(
        default="admin",
        alias="MONGO_ROOT_USER",
        description="Root administrative user for MongoDB",
    )
    mongo_root_password: str = Field(
        default="mongoadmin123",
        alias="MONGO_ROOT_PASSWORD",
        description="Root administrative password for MongoDB",
    )
    mongo_database: str = Field(
        default="knowledge_platform",
        alias="MONGO_DATABASE",
        description="Target database name for execution and document records",
    )

    # Qdrant Settings
    qdrant_host: str = Field(
        default="localhost",
        alias="QDRANT_HOST",
        description="Qdrant vector store hostname or container alias",
    )
    qdrant_port: int = Field(
        default=6333,
        ge=1024,
        le=65535,
        alias="QDRANT_PORT",
        description="Qdrant REST API port",
    )
    qdrant_grpc_port: int = Field(
        default=6334,
        ge=1024,
        le=65535,
        alias="QDRANT_GRPC_PORT",
        description="Qdrant gRPC API port",
    )
    qdrant_collection_name: str = Field(
        default="document_chunks",
        alias="QDRANT_COLLECTION_NAME",
        description="Canonical Qdrant collection name for document chunk vectors",
    )

    # Vertex AI Settings
    vertex_api_key: str = Field(
        default="",
        alias="VERTEX_API_KEY",
        description="API key for GCP Vertex AI Agent Platform access",
    )
    vertex_embedding_model: str = Field(
        default="gemini-embedding-001",
        alias="VERTEX_EMBEDDING_MODEL",
        description="Embedding model name",
    )
    vertex_batch_size: int = Field(
        default=50,
        ge=1,
        le=100,
        alias="VERTEX_BATCH_SIZE",
        description="Maximum chunk batch size per embedding API call",
    )
    vertex_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="VERTEX_MAX_RETRIES",
        description="Maximum retry attempts on transient or 429 rate limit errors",
    )
    vertex_retry_base_delay: float = Field(
        default=1.0,
        ge=0.1,
        alias="VERTEX_RETRY_BASE_DELAY",
        description="Base delay in seconds for exponential backoff",
    )

    # Ingestion Pipeline Behavior
    ingestion_reset_on_start: bool = Field(
        default=False,
        alias="INGESTION_RESET_ON_START",
        description="If True, clears vector database and document state on execution trigger",
    )
    default_bucket: str = Field(
        default="knowledge-source",
        alias="MINIO_DEFAULT_BUCKET",
        description="Default object storage bucket for source documents",
    )

    @property
    def mongo_uri(self) -> str:
        """Construct the MongoDB connection URI."""
        return f"mongodb://{self.mongo_root_user}:{self.mongo_root_password}@{self.mongo_host}:{self.mongo_port}"

    @property
    def qdrant_url(self) -> str:
        """Construct the Qdrant HTTP URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
