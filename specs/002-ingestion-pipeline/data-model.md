# Data Model: Ingestion Pipeline with Markdown Hierarchical Chunking & Vector Indexing

**Feature**: `002-ingestion-pipeline`  
**Date**: 2026-09-22  
**Status**: Completed  

---

## 1. Conceptual Model

The ingestion domain orchestrates the lifecycle of source documents from raw PDF discovery in object storage through text parsing, hierarchical chunking, vector embedding, and state tracking.

```
+-----------------------------------------------------------------------+
|                            ExecutionRecord                            |
|-----------------------------------------------------------------------|
| execution_id: str (UUIDv4)                                            |
| bucket: str ("knowledge-source")                                      |
| target_directory: str                                                 |
| status: ExecutionStatus                                               |
| reset_on_start: bool                                                  |
| discovered_count: int                                                 |
| created_count: int, updated_count: int, deleted_count: int            |
| unchanged_count: int, failed_count: int                               |
| started_at: datetime, completed_at: Optional[datetime]                |
+-----------------------------------+-----------------------------------+
                                    |
                                    | tracks 1..*
                                    v
+-----------------------------------------------------------------------+
|                            DocumentRecord                             |
|-----------------------------------------------------------------------|
| document_id: str (UUIDv4, stable across updates)                      |
| execution_id: str (UUIDv4)                                            |
| bucket: str                                                           |
| storage_path: str (Unique index with bucket)                          |
| file_name: str                                                        |
| last_modified: datetime                                               |
| size_bytes: int                                                       |
| action_status: ActionStatus (created | updated | deleted | unchanged) |
| processing_status: DocumentProcessingStatus                           |
| markdown_storage_path: Optional[str]                                  |
| chunk_count: int                                                      |
| error_message: Optional[str]                                          |
+-----------------------------------+-----------------------------------+
                                    |
                                    | partitions into 0..*
                                    v
+-----------------------------------------------------------------------+
|                             DocumentChunk                             |
|-----------------------------------------------------------------------|
| chunk_id: str (UUIDv4)                                                |
| document_id: str (UUIDv4)                                             |
| source_file_name: str                                                 |
| storage_path: str                                                     |
| chunk_index: int (0-based)                                            |
| total_chunks: int                                                     |
| text: str (length <= 1,000)                                           |
| char_length: int                                                      |
| h1: Optional[str], h2: Optional[str], h3: Optional[str]                |
+-----------------------------------+-----------------------------------+
                                    |
                                    | embeds into 1..1
                                    v
+-----------------------------------------------------------------------+
|                             VectorRecord                              |
|-----------------------------------------------------------------------|
| id: str (matching chunk_id)                                           |
| vector: list[float] (768 dimensions)                                  |
| payload: dict (document_id, chunk_id, file_name, path, headers, text) |
+-----------------------------------------------------------------------+
```

---

## 2. Enumerations

### 2.1 ExecutionStatus
Represents the overall operational state of an ingestion pipeline run:
- `pending`: Execution instantiated but discovery not yet begun.
- `in_progress`: Active discovery, parsing, chunking, or indexing underway.
- `completed`: Execution completed with 100% of discovered files processed without error.
- `completed_with_errors`: Execution completed, but one or more individual documents failed parsing or indexing.
- `failed`: Catastrophic execution abort (e.g., storage or database connection unavailable).

### 2.2 ActionStatus
Represents the lifecycle classification of a document discovered during an execution:
- `created`: New file discovered in object storage; queued for initial ingestion.
- `updated`: File exists at the same storage path, but storage timestamp is newer than database record; queued for re-ingestion and vector replacement.
- `deleted`: File previously ingested under this path is no longer present in storage; queued for vector purge and record deletion.
- `unchanged`: File storage timestamp matches recorded timestamp; skipped from re-processing.

### 2.3 DocumentProcessingStatus
Tracks internal milestone progression for a document within an execution:
- `discovered`: File recognized and recorded in database.
- `downloaded`: PDF stream fetched to local worker memory.
- `parsed`: Converted to structured Markdown by parser.
- `chunked`: Segmented into hierarchical chunks.
- `indexed`: Vectors generated and written to Qdrant.
- `failed`: Document-level failure encountered (error captured in `error_message`).

---

## 3. Pydantic Domain Schemas

### 3.1 ExecutionRecord (MongoDB Collection: `executions`)

```python
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ExecutionRecord(BaseModel):
    """Represents a discrete pipeline execution run."""

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
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
```

### 3.2 DocumentRecord (MongoDB Collection: `documents`)

```python
class ActionStatus(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class DocumentProcessingStatus(StrEnum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    PARSED = "parsed"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    FAILED = "failed"


class DocumentRecord(BaseModel):
    """Tracks a source document across pipeline executions."""

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
    markdown_storage_path: Optional[str] = Field(
        default=None,
        description="Storage key for generated Markdown artifact",
    )
    chunk_count: int = Field(default=0, ge=0)
    error_message: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

### 3.3 DocumentChunk (Domain Model)

```python
class DocumentChunk(BaseModel):
    """Represents a hierarchically bounded chunk of text."""

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
    h1: Optional[str] = None
    h2: Optional[str] = None
    h3: Optional[str] = None
```

### 3.4 VectorRecord (Qdrant Point Structure)

```python
class VectorPayload(BaseModel):
    """Metadata payload stored alongside embedding vectors in Qdrant."""

    document_id: str
    chunk_id: str
    source_file_name: str
    storage_path: str
    chunk_index: int
    total_chunks: int
    h1: Optional[str] = None
    h2: Optional[str] = None
    h3: Optional[str] = None
    text: str
```

---

## 4. State Transitions

### 4.1 Document Action Classification Logic

```text
Input: Discovered file (path, storage_last_modified)
Existing Record in MongoDB: existing_doc = find_one(bucket=bucket, storage_path=path)

IF existing_doc IS NULL:
    Action = CREATED
    document_id = uuid4()
ELSE IF existing_doc.last_modified < storage_last_modified:
    Action = UPDATED
    document_id = existing_doc.document_id (RETAIN STABLE ID)
ELSE:
    Action = UNCHANGED
    document_id = existing_doc.document_id

After scan of directory prefix:
FOR EACH recorded_doc in MongoDB matching directory prefix:
    IF recorded_doc.storage_path NOT IN discovered_paths AND recorded_doc.action_status != DELETED:
        Action = DELETED
```

### 4.2 Document Processing Lifecycle

```text
[DISCOVERED]
     │
     ▼ (Sequential download)
[DOWNLOADED]
     │
     ▼ (MarkItDown conversion)
[PARSED] ──(Failure: empty text / corrupt)──> [FAILED]
     │
     ▼ (Hierarchical chunker)
[CHUNKED]
     │
     ▼ (Vertex AI embed + Qdrant upsert)
[INDEXED]
```
