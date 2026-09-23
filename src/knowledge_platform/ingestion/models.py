"""Domain models and schemas for the document ingestion pipeline."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(StrEnum):
    """Operational status of an ingestion pipeline execution run."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ActionStatus(StrEnum):
    """Lifecycle classification of a discovered document within an execution."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class DocumentProcessingStatus(StrEnum):
    """Internal processing milestone for a document within an execution."""

    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    PARSED = "parsed"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    FAILED = "failed"


class ExecutionRecord(BaseModel):
    """Represents a discrete pipeline execution run."""

    model_config = ConfigDict(populate_by_name=True)

    execution_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for the execution run",
    )
    bucket: str = Field(
        default="knowledge-source",
        description="Target object storage bucket",
    )
    target_directory: str = Field(
        ...,
        description="Directory path / prefix scanned in object storage",
    )
    status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING,
        description="Current operational status of execution",
    )
    reset_on_start: bool = Field(
        default=False,
        description="Whether existing documents and vectors were purged before run",
    )
    discovered_count: int = Field(default=0, ge=0)
    created_count: int = Field(default=0, ge=0)
    updated_count: int = Field(default=0, ge=0)
    deleted_count: int = Field(default=0, ge=0)
    unchanged_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None


class DocumentRecord(BaseModel):
    """Tracks a source document across pipeline executions."""

    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Stable unique document identifier across updates",
    )
    execution_id: str = Field(
        ...,
        description="Identifier of execution that last evaluated this document",
    )
    bucket: str = Field(
        default="knowledge-source",
        description="Object storage bucket containing source PDF",
    )
    storage_path: str = Field(
        ...,
        description="Object storage key path of source PDF",
    )
    file_name: str = Field(
        ...,
        description="Original source file name",
    )
    last_modified: datetime = Field(
        ...,
        description="Object storage last modified timestamp",
    )
    size_bytes: int = Field(default=0, ge=0)
    action_status: ActionStatus = Field(
        ...,
        description="Action classification for this execution",
    )
    processing_status: DocumentProcessingStatus = Field(
        default=DocumentProcessingStatus.DISCOVERED,
        description="Processing progress within execution",
    )
    markdown_storage_path: str | None = Field(
        default=None,
        description="Storage key for generated Markdown artifact",
    )
    chunk_count: int = Field(default=0, ge=0)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentChunk(BaseModel):
    """Represents a hierarchically bounded chunk of text."""

    model_config = ConfigDict(populate_by_name=True)

    chunk_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for chunk",
    )
    document_id: str = Field(
        ...,
        description="Reference to parent document ID",
    )
    source_file_name: str = Field(
        ...,
        description="Source PDF file name",
    )
    storage_path: str = Field(
        ...,
        description="Storage key path of source document",
    )
    chunk_index: int = Field(
        ...,
        ge=0,
        description="0-based sequential chunk index within document",
    )
    total_chunks: int = Field(
        ...,
        ge=1,
        description="Total chunk count for parent document",
    )
    text: str = Field(
        ...,
        max_length=1000,
        description="Chunk textual content (max 1000 chars)",
    )
    char_length: int = Field(..., ge=1, le=1000)
    h1: str | None = None
    h2: str | None = None
    h3: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorPayload(BaseModel):
    """Metadata payload stored alongside embedding vectors in Qdrant."""

    model_config = ConfigDict(populate_by_name=True)

    document_id: str
    chunk_id: str
    source_file_name: str
    storage_path: str
    chunk_index: int
    total_chunks: int
    h1: str | None = None
    h2: str | None = None
    h3: str | None = None
    text: str
