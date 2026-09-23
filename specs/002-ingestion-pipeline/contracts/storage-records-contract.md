# Storage Schema Contract: MongoDB Collections & Qdrant Collections

**Feature**: `002-ingestion-pipeline`  
**Date**: 2026-09-22  
**Status**: Completed  

---

## 1. MongoDB Storage Contract

- **Database Name**: `knowledge_platform`

### 1.1 Collection: `executions`

Represents each run of the ingestion pipeline.

```json
{
  "_id": "ObjectId",
  "execution_id": "c8d62635-f09b-4654-bfef-c07a3f81e3ad",
  "bucket": "knowledge-source",
  "target_directory": "documents/reports",
  "status": "completed",
  "reset_on_start": false,
  "discovered_count": 4,
  "created_count": 2,
  "updated_count": 1,
  "deleted_count": 1,
  "unchanged_count": 0,
  "failed_count": 0,
  "started_at": "2026-09-22T10:00:00.000Z",
  "completed_at": "2026-09-22T10:00:15.000Z",
  "error_message": null
}
```

#### Indexes
1. `{"execution_id": 1}` — Unique
2. `{"started_at": -1}`

---

### 1.2 Collection: `documents`

Tracks discovered documents, their lifecycle action status, and Markdown storage artifacts.

```json
{
  "_id": "ObjectId",
  "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "execution_id": "c8d62635-f09b-4654-bfef-c07a3f81e3ad",
  "bucket": "knowledge-source",
  "storage_path": "documents/reports/q3_financials.pdf",
  "file_name": "q3_financials.pdf",
  "last_modified": "2026-09-22T09:45:00.000Z",
  "size_bytes": 1048576,
  "action_status": "created",
  "processing_status": "indexed",
  "markdown_storage_path": "processed/markdown/a1b2c3d4-e5f6-7890-abcd-ef1234567890.md",
  "chunk_count": 12,
  "error_message": null,
  "created_at": "2026-09-22T10:00:02.000Z",
  "updated_at": "2026-09-22T10:00:05.000Z"
}
```

#### Indexes
1. `{"bucket": 1, "storage_path": 1}` — Unique
2. `{"execution_id": 1}`
3. `{"document_id": 1}` — Unique
4. `{"action_status": 1}`

---

## 2. Qdrant Vector Storage Contract

- **Collection Name**: `document_chunks`
- **Vector Configuration**:
  - `size`: `768`
  - `distance`: `Cosine`

### 2.1 Point Record Format

```json
{
  "id": "e4f5a6b7-8c9d-0e1f-2a3b-4c5d6e7f8a9b",
  "vector": [0.0123, -0.0456, 0.0891, ...],
  "payload": {
    "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "chunk_id": "e4f5a6b7-8c9d-0e1f-2a3b-4c5d6e7f8a9b",
    "source_file_name": "q3_financials.pdf",
    "storage_path": "documents/reports/q3_financials.pdf",
    "chunk_index": 0,
    "total_chunks": 12,
    "h1": "Executive Summary",
    "h2": "Revenue Performance",
    "h3": "Regional Breakdown",
    "text": "In Q3, overall revenue increased by 14% compared to the prior year period..."
  }
}
```

### 2.2 Payload Indexing
To support fast filtered deletions and filtered retrieval:
- `document_id`: Keyword index
- `source_file_name`: Keyword index
- `storage_path`: Keyword index
- `chunk_index`: Integer index
