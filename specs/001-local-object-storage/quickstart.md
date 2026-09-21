# Quickstart Validation Guide: Local Object Storage

**Feature**: `001-local-object-storage`  
**Date**: 2026-09-21  
**Status**: Ready for Implementation  

---

## 1. Prerequisites
- Linux / WSL (Ubuntu) environment.
- Docker & Docker Compose installed and daemon running.
- Python 3.12+ with `uv` installed (`uv --version`).

---

## 2. Setup & Service Initialization

### Step 1: Prepare Environment Configuration
Copy the template `.env.example` into `.env`:
```bash
cp .env.example .env
```
Ensure `.env` contains:
```env
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
MINIO_DEFAULT_BUCKET=knowledge-source
```

### Step 2: Start the Object Storage Services
Run Docker Compose in detached mode:
```bash
docker compose up -d
```

Verify service status:
```bash
docker compose ps
```
**Expected Outcome**:
- `minio` container is `Up (healthy)`.
- `minio-create-bucket` container completed with `Exit 0`.

---

## 3. End-to-End Validation Scenarios

### Scenario 1: Web Console Access & Manual Document Upload
1. Open a browser and navigate to the MinIO Web Console:
   ```text
   http://localhost:9001
   ```
2. Log in using credentials:
   - **Username**: `admin`
   - **Password**: `minioadmin123`
3. In the sidebar, select **Buckets** and click on `knowledge-source`.
4. Click **Upload** → **Upload Files** and upload one or more sample documents (e.g. a PDF or Markdown file).
5. **Expected Outcome**: The uploaded files appear immediately in the object browser table with accurate sizes and timestamps.

---

### Scenario 2: Asynchronous End-to-End Integration Testing
Run the unmocked asynchronous integration test suite using `uv`:
```bash
uv run pytest tests/integration/test_object_storage.py -v
```

**Expected Outcome**:
- Verifies HTTP 200 response on `http://localhost:9001`.
- Verifies MinIO S3 API connectivity on `http://localhost:9000`.
- Asynchronously checks that `knowledge-source` bucket exists using `AsyncStorageClient`.
- Asynchronously uploads and retrieves sample objects, asserting that downloaded bytes match uploaded bytes exactly with matching checksums.
- All integration tests PASS without mocks using `pytest-asyncio`.

---

### Scenario 3: Data Persistence Across Container Recreations
1. Stop and remove the active containers:
   ```bash
   docker compose down
   ```
2. Re-create and restart the containers:
   ```bash
   docker compose up -d
   ```
3. Inspect bucket contents via web console (`http://localhost:9001`) or run async integration tests:
   ```bash
   uv run pytest tests/integration/test_object_storage.py -v
   ```
4. **Expected Outcome**: All previously uploaded documents in the `knowledge-source` bucket remain present and intact without data loss, proving named volume persistence.
