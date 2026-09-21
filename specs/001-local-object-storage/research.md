# Phase 0 Research: Local Object Storage with Built-in Web UI

**Feature**: `001-local-object-storage`  
**Date**: 2026-09-21  
**Status**: Completed  

---

## 1. Object Storage Provider Selection

### Decision
Deploy **MinIO** using the pinned container image `minio/minio:RELEASE.2024-11-07T00-52-19Z`.

### Rationale
- **Full S3 Compatibility**: Provides complete fidelity to the Amazon S3 API, ensuring all downstream ingestion code, agents, and SDKs operate identically against local MinIO and production cloud object storage.
- **Built-in Web Console UI**: MinIO natively bundles the MinIO Web Console, accessible on port 9001. Users can authenticate, create buckets, browse objects, and upload single or multiple files using drag-and-drop out of the box without developing custom UI or custom upload backend code.
- **Lightweight & High Performance**: Minimal footprint, written in Go, boots in <2 seconds inside Docker on WSL/Ubuntu.
- **Specific Version Pinning**: Uses an immutable release tag (`RELEASE.2024-11-07T00-52-19Z`) rather than `:latest`, fulfilling constitutional constraints against unpredictable image drift.

### Alternatives Considered
- **LocalStack**: Emulates various AWS services including S3. Rejected because LocalStack's free tier has high resource overhead, longer cold-start times, and does not provide an intuitive, dedicated object management web UI out of the box without external third-party tools.
- **Custom FastAPI File Upload Server**: Rejected per user clarification. Writing custom endpoints and UI components introduces unnecessary maintenance burden when an enterprise-grade object store UI already exists.
- **SeaweedFS / Ceph**: Powerful distributed storage systems, but significantly more complex to configure, operate, and maintain in a lightweight local developer environment.

---

## 2. Default Bucket Provisioning Pattern (`knowledge-source`)

### Decision
Use a declarative, ephemeral **MinIO Client (`mc`) sidecar container** (`minio/mc:RELEASE.2024-11-05T11-41-28Z`) in `docker-compose.yml` that waits for the MinIO service health check and executes an idempotent bucket initialization command:
```sh
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc mb --ignore-existing local/knowledge-source
```

### Rationale
- **Idempotency**: The `--ignore-existing` flag guarantees that subsequent restarts or container recreations detect the existing bucket and exit cleanly without data modification.
- **Non-Invasive**: Leaves the core MinIO container clean with its default entrypoint and health checks intact.
- **Zero Manual Steps**: Fully automates bucket provisioning on `docker compose up -d`.

### Alternatives Considered
- **Custom Shell Script Entrypoint inside MinIO Container**: Modifying the MinIO container entrypoint creates maintainability issues, breaks clean container lifecycle management, and complicates updates.
- **Application Startup Hook in Python**: Requiring the Python application to create the bucket couples the web/AI app lifecycle to infrastructure initialization. Downstream consumers expect the storage infrastructure to be ready independently.

---

## 3. Data Persistence & Volume Management

### Decision
Use a named Docker volume (`minio_data`) mounted to `/data` in the MinIO container.

### Rationale
- **Container Lifecycle Independence**: Retains all bucket configurations and uploaded files across container stops, restarts, down-and-ups (`docker compose down` and `docker compose up`), and image version upgrades.
- **Performance on WSL2/Ubuntu**: Named volumes managed by Docker engine on Linux perform at native filesystem speeds without translation layer latency.
- **Ease of Inspection & Backup**: Standard Docker commands (`docker volume inspect`) cleanly manage the storage state.

### Alternatives Considered
- **Host Bind Mount (e.g., `./.data/minio`):** Can suffer from file permission mismatch issues across WSL/Windows boundaries and accidental inclusion in git commits. A named volume provides superior isolation and consistency.

---

## 4. Configuration & Credential Management

### Decision
Twelve-factor environment variable management via a root `.env` file referenced by `docker-compose.yml`, accompanied by a tracked template `.env.example`.

### Variables Defined
- `MINIO_ROOT_USER`: Administrative username (default for local dev: `admin`).
- `MINIO_ROOT_PASSWORD`: Administrative password (default for local dev: `minioadmin123`).
- `MINIO_PORT`: S3 API port (default: `9000`).
- `MINIO_CONSOLE_PORT`: Web UI port (default: `9001`).
- `MINIO_DEFAULT_BUCKET`: Default bucket name (`knowledge-source`).

### Rationale
- **Security & Hygiene**: `.env` is ignored by Git, preventing any local credentials from entering version control. `.env.example` provides self-documenting configuration for new developers.
- **Port Flexibility**: Local port mappings are parameter-driven to prevent collisions with host machine services.

---

## 5. Programmatic Client Access (Asynchronous Python)

### Decision
Adopt **`aioboto3`** (backed by `aiobotocore` and `boto3`) for all downstream programmatic client interactions.

### Rationale
- **Non-blocking Asynchronous I/O**: Downstream ingestion pipelines, RAG enrichment services, and Vertex AI agents run asynchronously on `asyncio` event loops. Using `aioboto3` ensures that streaming documents, checking bucket status, and reading objects never blocks the event loop.
- **S3 API Fidelity**: Uses the exact same S3 client surface as `boto3`, maintaining complete parity with AWS S3 and GCP Cloud Storage (S3-compatible mode).
- **Type Annotations**: Integrates with Pydantic response models for strict type safety and schema validation.

### Alternatives Considered
- **Synchronous `boto3`**: Rejected per user requirement ("prefer async approach over sync for downstream services to use"). Synchronous network calls block the asyncio loop during document downloads.
- **`httpx` directly to S3 REST API**: Writing raw HTTP requests requires manual AWS Signature Version 4 calculation, error handling, and XML parsing, which introduces error-prone boilerplate.

---

## 6. End-to-End Verification Strategy

### Decision
Implement real, unmocked asynchronous end-to-end integration tests using `pytest` and `pytest-asyncio` (`tests/integration/test_object_storage.py`) that:
1. Validate connectivity against the live local MinIO S3 API on port 9000.
2. Verify that the bucket `knowledge-source` exists using `AsyncStorageClient`.
3. Upload test documents and asynchronously retrieve them, confirming byte-for-byte checksum integrity.
4. Verify HTTP availability of the MinIO Web Console on port 9001.

### Rationale
- Strictly aligns with Constitution Principle III (End-to-End Integration Verification Over Mocks) by exercising the genuine containerized service and avoiding brittle mocks.
