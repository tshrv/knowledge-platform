---
description: "Task list for local object storage implementation"
---

# Tasks: Local Object Storage with Built-in Web UI

**Input**: Design documents from `/specs/001-local-object-storage/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `.specify/memory/constitution.md`  
**Tests**: Unmocked asynchronous integration tests against live MinIO container per Constitution Principle III  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Exact file paths are included in all task descriptions

---

## Phase 1: Setup (Shared Infrastructure & Environment)

**Purpose**: Project dependency configuration and environment initialization

- [ ] T001 Configure project dependencies in `pyproject.toml` including `aioboto3>=13.2.0`, `aiobotocore>=2.15.0`, `pydantic>=2.9.0`, `pydantic-settings>=2.5.0`, `httpx>=0.27.0`, and dev dependencies `pytest>=8.3.0`, `pytest-asyncio>=0.24.0`, `ruff>=0.6.0`, `mypy>=1.11.0`, `boto3-stubs[s3]>=1.35.0`
- [ ] T002 [P] Create local environment configuration template `.env.example` with `MINIO_ROOT_USER=admin`, `MINIO_ROOT_PASSWORD=minioadmin123`, `MINIO_HOST=localhost`, `MINIO_PORT=9000`, `MINIO_CONSOLE_PORT=9001`, `MINIO_DEFAULT_BUCKET=knowledge-source` per contract in `specs/001-local-object-storage/contracts/docker-compose-contract.md`
- [ ] T003 [P] Ensure `.env` is listed in `.gitignore` to prevent credential leakage into version control
- [ ] T004 Initialize package directory structure creating `src/knowledge_platform/storage/` and `tests/integration/`

---

## Phase 2: Foundational (Core Configuration & Models)

**Purpose**: Core configuration schemas and domain entities that MUST be complete before user story implementation

**⚠️ CRITICAL**: Foundational tasks must be completed before implementing user stories

- [ ] T005 [P] Implement `StorageSettings` in `src/knowledge_platform/config.py` using `pydantic-settings` with field aliases for `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_HOST`, `MINIO_PORT`, `MINIO_CONSOLE_PORT`, `MINIO_DEFAULT_BUCKET`, and properties for `endpoint_url` and `console_url` per `specs/001-local-object-storage/data-model.md`
- [ ] T006 [P] Implement Pydantic domain models `DocumentMetadata` and `BucketStatus` in `src/knowledge_platform/storage/models.py` with validation rules (key non-empty max 1024 chars, size_bytes >= 0, content_type, etag, last_modified) per `specs/001-local-object-storage/data-model.md`
- [ ] T006a [P] Implement domain exception hierarchy in `src/knowledge_platform/storage/exceptions.py` (`StorageError`, `BucketNotFoundError`, `DocumentNotFoundError`, `StorageConnectionError`) per `specs/001-local-object-storage/contracts/storage-client-contract.md`
- [ ] T007 Implement package exports in `src/knowledge_platform/__init__.py` and `src/knowledge_platform/storage/__init__.py` exporting models and domain exceptions

**Checkpoint**: Foundation ready — service orchestration and user stories can now begin

---

## Phase 3: User Story 1 - Automated Storage & Default Bucket Provisioning (Priority: P1) 🎯 MVP

**Goal**: Orchestrate MinIO server container and `minio-create-bucket` init container in `docker-compose.yml` with persistent volume `minio_data`, socket healthchecks, and auto-provisioning of `knowledge-source`.

**Independent Test**: Run `docker compose up -d`, assert `minio` container is healthy and `minio-create-bucket` exits 0, and verify `knowledge-source` bucket is created.

### Implementation for User Story 1

- [ ] T008 [US1] Define `minio` service and `minio-create-bucket` init service in `docker-compose.yml` using pinned image `minio/minio:RELEASE.2024-11-07T00-52-19Z` with command `server /data --console-address ":9001"`, socket healthcheck, named volume `minio_data`, and `minio/mc:RELEASE.2024-11-05T11-41-28Z` with polling loop provisioning `knowledge-source` per `specs/001-local-object-storage/contracts/docker-compose-contract.md`
- [ ] T009 [US1] Create local active configuration `.env` populated from `.env.example`
- [ ] T010 [US1] Validate `docker compose config` syntax and verify service dependency wiring in `docker-compose.yml`

**Checkpoint**: User Story 1 is functional and verifiable — local MinIO boots cleanly with `knowledge-source` bucket pre-created

---

## Phase 4: User Story 2 - Document Upload via Built-in Storage Web UI (Priority: P1)

**Goal**: Enable browser-based document uploads via MinIO Web Console on port 9001 without custom application code.

**Independent Test**: Verify HTTP GET 200 on `http://localhost:9001` and verify UI login and upload workflow.

### Implementation for User Story 2

- [ ] T011 [P] [US2] Create integration test in `tests/integration/test_object_storage.py` to verify HTTP 200 accessibility of the MinIO Web Console at `console_url`
- [ ] T012 [US2] Document browser login and manual file upload workflow in `specs/001-local-object-storage/quickstart.md` validating that uploaded files appear in `knowledge-source`

**Checkpoint**: User Stories 1 AND 2 are verified — storage infrastructure is up and users can ingest documents through the Web Console

---

## Phase 5: User Story 3 - Asynchronous Programmatic Object Access for Downstream Ingestion (Priority: P2)

**Goal**: Provide downstream services with an asynchronous Python client (`AsyncStorageClient`) implementing `AsyncStorageClientProtocol` to verify bucket existence, list documents, and stream bytes without blocking the event loop.

**Independent Test**: Execute `uv run pytest tests/integration/test_object_storage.py` against the running MinIO container to verify asynchronous bucket checks, file uploads, listings, and byte streaming with checksum matches.

### Implementation for User Story 3

- [ ] T013 [P] [US3] Implement `AsyncStorageClientProtocol` in `src/knowledge_platform/storage/client.py` defining `verify_bucket_exists`, `list_documents`, `get_document_stream`, `get_document_bytes`, and `put_document_bytes` per `specs/001-local-object-storage/contracts/storage-client-contract.md`
- [ ] T014 [US3] Implement `AsyncStorageClient` class in `src/knowledge_platform/storage/client.py` using `aioboto3.Session` with context management (`__aenter__` and `__aexit__`) to connect to MinIO S3 API at `endpoint_url`, wrapping connection failures in `StorageConnectionError`
- [ ] T015 [US3] Implement `verify_bucket_exists` method in `src/knowledge_platform/storage/client.py` using `head_bucket`, catching connection errors as `StorageConnectionError`
- [ ] T016 [US3] Implement `list_documents` method in `src/knowledge_platform/storage/client.py` using `list_objects_v2` paginator and mapping results to `DocumentMetadata`, raising `BucketNotFoundError` if the bucket does not exist
- [ ] T017 [US3] Implement `get_document_stream` and `get_document_bytes` methods in `src/knowledge_platform/storage/client.py` streaming chunked bytes from S3 `get_object`, raising `BucketNotFoundError` or `DocumentNotFoundError` for missing targets
- [ ] T018 [US3] Implement `put_document_bytes` helper in `src/knowledge_platform/storage/client.py` using S3 `put_object` for test harness seeding
- [ ] T019 [US3] Implement asynchronous integration tests in `tests/integration/test_object_storage.py` verifying bucket existence, document upload, listing, streaming, checksum matching, and domain exception raising (`BucketNotFoundError`, `DocumentNotFoundError`) against live MinIO container

**Checkpoint**: All user stories are implemented and verified — downstream services have full async programmatic access to `knowledge-source`

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Persistence validation, code hygiene, and end-to-end execution verification

- [ ] T020 [P] Implement data persistence validation test in `tests/integration/test_object_storage.py` verifying that uploaded files in `knowledge-source` persist after container recreation
- [ ] T021 [P] Run static type checking with `mypy` and code formatting/linting with `ruff` across `src/` and `tests/`
- [ ] T022 Execute end-to-end quickstart validation guide in `specs/001-local-object-storage/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — blocks all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion (MinIO service running)
- **User Story 3 (Phase 5)**: Depends on User Story 1 completion (MinIO service running with `knowledge-source` bucket)
- **Polish (Phase 6)**: Depends on all user stories being completed

### Within Each User Story

- Pydantic models before service implementations
- Client protocol before concrete client methods
- Individual client methods before integration tests
- Story complete before proceeding to polish

### Parallel Opportunities

- Phase 1: `T002` and `T003` can run in parallel
- Phase 2: `T005` (`config.py`), `T006` (`models.py`), and `T006a` (`exceptions.py`) can run in parallel
- Phase 4: `T011` (web console HTTP test) can run in parallel with client protocol definition `T013`
- Phase 6: `T020` and `T021` can run in parallel

---

## Parallel Example: Foundational & User Story 3

```bash
# Launch independent models and config in parallel:
Task: "Implement StorageSettings in src/knowledge_platform/config.py"
Task: "Implement Pydantic domain models in src/knowledge_platform/storage/models.py"

# Launch independent tests and linting in parallel:
Task: "Implement data persistence validation test in tests/integration/test_object_storage.py"
Task: "Run static type checking with mypy and code formatting/linting with ruff across src/ and tests/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (`pyproject.toml`, `.env.example`)
2. Complete Phase 2: Foundational (`config.py`, `models.py`)
3. Complete Phase 3: User Story 1 (`docker-compose.yml`, `.env`)
4. **STOP and VALIDATE**: Run `docker compose up -d` and verify `knowledge-source` bucket exists
5. Foundation and MVP container infrastructure are ready

### Incremental Delivery
1. Setup + Foundational → Project foundation ready
2. User Story 1 → Storage service & bucket auto-provisioned (MVP)
3. User Story 2 → Web Console accessible for drag-and-drop document uploads
4. User Story 3 → Async Python client available for downstream ingestion pipelines
5. Polish → Formatting, typing, persistence verification across restarts

---

## Notes

- All tasks strictly follow checklist format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- Real unmocked integration tests run via `uv run pytest tests/integration/` per Constitution Principle III
- No automated git commits will be made; all commits remain strictly human-managed per Constitution Governance rules
