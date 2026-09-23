# Quickstart Validation Guide: Ingestion Pipeline with Hierarchical Chunking & Vector Indexing

**Feature**: `002-ingestion-pipeline`  
**Date**: 2026-09-22  
**Status**: Ready for Implementation  

---

## 1. Prerequisites

- Linux / WSL (Ubuntu) environment.
- Docker & Docker Compose running.
- Python 3.12+ with `uv` installed (`uv --version`).
- Valid Google Cloud Platform API key with Vertex AI Agent Platform access for embeddings (`VERTEX_API_KEY`).

---

## 2. Infrastructure Setup

### Step 1: Prepare Environment Configuration
Ensure `.env` contains configuration for MinIO, MongoDB, Qdrant, and Vertex AI:

```dotenv
# Storage (MinIO)
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
MINIO_DEFAULT_BUCKET=knowledge-source

# Vector Database (Qdrant)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION_NAME=document_chunks

# Metadata Database (MongoDB)
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_ROOT_USER=admin
MONGO_ROOT_PASSWORD=mongoadmin123
MONGO_DATABASE=knowledge_platform

# Vertex AI Embeddings
VERTEX_API_KEY=your_vertex_api_key_here
VERTEX_EMBEDDING_MODEL=gemini-embedding-001

# Ingestion Pipeline Behavior
INGESTION_RESET_ON_START=false
```

### Step 2: Boot Containerized Infrastructure
Start MinIO, MongoDB, and Qdrant in detached mode:
```bash
docker compose up -d
```

Verify service status:
```bash
docker compose ps
```
**Expected Outcome**:
- `minio`: `Up (healthy)`
- `minio-create-bucket`: `Exit 0`
- `mongodb`: `Up (healthy)`
- `qdrant`: `Up (healthy)`

Web consoles accessible:
- MinIO: `http://localhost:9001`
- Qdrant: `http://localhost:6333/dashboard`

---

## 3. End-to-End Validation Scenarios

### Scenario 1: Initial PDF Ingestion & Discovery Classification
1. Upload a sample PDF with multiple heading levels into MinIO's `knowledge-source` bucket under `manuals/system_guide.pdf`.
2. Trigger the ingestion pipeline targeting directory `manuals/`:
   ```bash
   uv run python -m knowledge_platform.ingestion.cli --directory manuals/
   ```
3. **Expected Outcome**:
   - Execution status transitions to `completed`.
   - Loguru structured logs emit events with `execution_id`, `document_id`, and `chunk_id`.
   - MongoDB `executions` record displays `created_count: 1`, `failed_count: 0`.
   - MongoDB `documents` record shows `action_status: "created"`, `processing_status: "indexed"`, and valid `markdown_storage_path`.
   - Markdown artifact is persisted in MinIO under `processed/markdown/<doc_id>.md`.
   - Qdrant collection `document_chunks` contains points with metadata `source_file_name: "system_guide.pdf"`, sequential `chunk_index`, accurate `total_chunks`, and inherited `h1`/`h2`/`h3` headers.

---

### Scenario 2: Incremental Modification & Stable ID Re-indexing
1. Re-upload a modified version of `system_guide.pdf` with updated content.
2. Trigger pipeline again:
   ```bash
   uv run python -m knowledge_platform.ingestion.cli --directory manuals/
   ```
3. **Expected Outcome**:
   - Document categorized as `updated`.
   - Retains the exact same `document_id`.
   - Previous Qdrant vector points for that `document_id` are purged and replaced with new chunk vectors.
   - MongoDB `documents` record is updated with new timestamp and chunk count.

---

### Scenario 3: Document Deletion & Vector Cleanup
1. Delete `manuals/system_guide.pdf` from MinIO via Web Console or CLI.
2. Trigger pipeline:
   ```bash
   uv run python -m knowledge_platform.ingestion.cli --directory manuals/
   ```
3. **Expected Outcome**:
   - Document categorized as `deleted`.
   - MongoDB `documents` record marked with `action_status: "deleted"`.
   - All corresponding points in Qdrant for that `document_id` are deleted (0 points remaining).

---

### Scenario 4: Clean Start Purge (`reset_on_start`)
1. Trigger pipeline with the reset flag enabled:
   ```bash
   uv run python -m knowledge_platform.ingestion.cli --directory manuals/ --reset-on-start
   ```
2. **Expected Outcome**:
   - Qdrant collection `document_chunks` is cleared and recreated before scanning.
   - MongoDB `documents` and `executions` collections are cleared.
   - Only newly discovered files are ingested fresh.

---

### Scenario 5: Automated End-to-End Integration Tests
Run the comprehensive integration test suite without mocks:
```bash
uv run pytest tests/integration/test_ingestion_pipeline.py -v
```
**Expected Outcome**:
- All unmocked integration tests pass against live MinIO, MongoDB, and Qdrant containers.
