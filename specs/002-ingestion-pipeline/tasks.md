# Tasks: Recursive PDF Ingestion Pipeline with Markdown Hierarchical Chunking and Vector Indexing

**Input**: Design documents from `specs/002-ingestion-pipeline/` (`plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`)  
**Prerequisites**: `plan.md` (complete), `spec.md` (complete), `data-model.md` (complete), `contracts/` (complete), `research.md` (complete)  
**Tests**: Unmocked end-to-end integration tests using live Docker containers (`tests/integration/test_ingestion_pipeline.py`) in compliance with Constitution Principle III.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps task to user story (`[US1]`, `[US2]`, `[US3]`, `[US4]`, `[US5]`)
- Exact file paths are specified in all task descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Infrastructure provisioning, dependency configuration, and environment setup

- [X] T001 Add Qdrant (`qdrant/qdrant:v1.13.4`) and MongoDB 7.0 (`mongo:7.0`) container service definitions with healthchecks and persistent named volumes (`qdrant_data`, `mongo_data`) in `docker-compose.yml`
- [X] T002 Add dependencies (`markitdown>=0.1.8`, `qdrant-client>=1.13.0`, `motor>=3.7.0`, `pymongo>=4.11.0`, `google-genai>=2.25.0`, `loguru>=0.7.2`) to `pyproject.toml`
- [X] T003 Update `.env.example` with MongoDB (`MONGO_HOST`, `MONGO_PORT`, `MONGO_ROOT_USER`, `MONGO_ROOT_PASSWORD`, `MONGO_DATABASE`), Qdrant (`QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION_NAME`), Vertex AI (`VERTEX_API_KEY`, `VERTEX_EMBEDDING_MODEL`), and Ingestion (`INGESTION_RESET_ON_START`) configuration variables
- [X] T004 Run `uv sync` to lock dependencies in `uv.lock` and establish the virtual environment
- [X] T005 [P] Implement `IngestionSettings` in `src/knowledge_platform/config.py` with Pydantic BaseSettings, environment variable aliases, and connection URI helper properties (`mongo_uri`, `qdrant_url`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, database repositories, vector store managers, and client wrappers that MUST be complete before user stories can execute

**⚠️ CRITICAL**: No user story implementation work can begin until this phase is complete

- [X] T006 [P] Implement Pydantic domain models and enums (`ExecutionStatus`, `ActionStatus`, `DocumentProcessingStatus`, `ExecutionRecord`, `DocumentRecord`, `DocumentChunk`, `VectorPayload`) with strict field constraints (`char_length <= 1000`, `chunk_index >= 0`, `total_chunks >= 1`) in `src/knowledge_platform/ingestion/models.py`
- [X] T007 [P] Implement ingestion domain exception hierarchy (`IngestionError`, `PipelineFatalError`, `DocumentProcessingError`, `DocumentParsingError`, `UnparseableDocumentError`, `VectorIndexingError`) in `src/knowledge_platform/ingestion/exceptions.py`
- [X] T008 Implement asynchronous MongoDB repository (`MongoRepository`) with connection management, collection index creation (unique `(bucket, storage_path)` and unique `execution_id`), and atomic CRUD methods in `src/knowledge_platform/ingestion/db.py`
- [X] T009 [P] Implement asynchronous Qdrant vector store manager (`QdrantVectorStore`) with collection initialization (768 dimensions, Cosine distance), payload index creation, and collection recreate logic in `src/knowledge_platform/ingestion/vector_store.py`
- [X] T010 [P] Implement Vertex AI embedding client (`VertexAIEmbeddingClient`) using `google-genai` with explicit API key authentication (`VERTEX_API_KEY`), batch embedding generation, and error handling in `src/knowledge_platform/ingestion/embeddings.py`

**Checkpoint**: Foundation ready — database repositories, vector store, embedding client, and domain models are validated and ready for user story implementation.

---

## Phase 3: User Story 1 - Recursive File Discovery and Lifecycle Categorization (Priority: P1) 🎯 MVP

**Goal**: Recursively scan target object storage directory, filter for PDF files only, compare against database state, assign action status (`created`, `updated`, `deleted`, `unchanged`), preserve stable `document_id` for updates, and persist execution/document records in MongoDB.

**Independent Test**: Populate object storage directory with PDFs and non-PDFs, execute discovery, and verify in MongoDB that only PDFs are recorded as `created`. Modify a file timestamp, remove another file, add a new file, and verify subsequent run correctly classifies `created`, `updated` (with same `document_id`), `deleted`, and `unchanged`.

### Tests for User Story 1

- [X] T011 [P] [US1] Create integration test in `tests/integration/test_ingestion_discovery.py` verifying recursive PDF discovery, non-PDF filtering, action categorization (`created`, `updated`, `deleted`, `unchanged`), and stable `document_id` preservation against live MinIO and MongoDB containers

### Implementation for User Story 1

- [X] T012 [US1] Implement recursive object storage directory scanning and `.pdf` extension filtering in `src/knowledge_platform/ingestion/discovery.py` using `StorageClient.list_objects`
- [X] T013 [US1] Implement document lifecycle reconciliation logic in `src/knowledge_platform/ingestion/discovery.py` comparing storage timestamps against MongoDB records to assign `created`, `updated` (retaining existing `document_id`), `deleted`, and `unchanged` statuses
- [X] T014 [US1] Implement execution record initialization and milestone counter persistence in `src/knowledge_platform/ingestion/db.py`
- [X] T015 [US1] Implement document state batch upserting for discovered files in `src/knowledge_platform/ingestion/db.py`
- [X] T016 [US1] Bind Loguru contextual logging (`execution_id`, `storage_path`, `action_status`) across discovery and classification phases in `src/knowledge_platform/ingestion/discovery.py`

**Checkpoint**: User Story 1 is fully functional and independently testable — storage files are discovered, categorized, and tracked in MongoDB without invoking downstream parsing.

---

## Phase 4: User Story 2 - Sequential PDF Download, Markdown Conversion, and Artifact Storage (Priority: P1)

**Goal**: Sequentially download each `created` or `updated` PDF, convert its content to structured Markdown using Microsoft's `markitdown`, detect image-only/scanned PDFs lacking extractable text, store generated Markdown in object storage under `processed/markdown/<doc_id>.md`, and update the MongoDB document record.

**Independent Test**: Supply a multi-page PDF with headings and a scanned image-only PDF; verify that the digital PDF produces a structured Markdown artifact stored in MinIO and recorded in MongoDB, while the image-only PDF is marked as `failed` without crashing execution.

### Tests for User Story 2

- [X] T017 [P] [US2] Create integration test in `tests/integration/test_ingestion_parser.py` validating sequential download, `markitdown` Markdown conversion, artifact persistence in MinIO, and `failed` status isolation for image-only/corrupt PDFs

### Implementation for User Story 2

- [X] T018 [US2] Implement `PdfMarkdownParser` wrapping `markitdown.MarkItDown` in `src/knowledge_platform/ingestion/parser.py`, including empty text detection (`not text_content.strip()`) to raise `UnparseableDocumentError` for scanned/image-only PDFs
- [X] T019 [US2] Implement sequential PDF byte stream download and temporary buffer handling in `src/knowledge_platform/ingestion/parser.py` using `StorageClient.get_object_stream`
- [X] T020 [US2] Implement Markdown artifact upload to MinIO under `processed/markdown/{document_id}.md` in `src/knowledge_platform/ingestion/parser.py` using `StorageClient.put_object`
- [X] T021 [US2] Update document record in MongoDB with `markdown_storage_path` and transition `processing_status` to `parsed` (or `failed` with `error_message` on exception) in `src/knowledge_platform/ingestion/db.py`

**Checkpoint**: User Stories 1 and 2 work end-to-end — PDFs are discovered, categorized, sequentially converted to Markdown, and stored in object storage with database updates.

---

## Phase 5: User Story 3 - Hierarchical Markdown Chunking with Contextual Metadata (Priority: P1)

**Goal**: Partition converted Markdown content hierarchically along Header 1 (`#`), Header 2 (`##`), and Header 3 (`###`) boundaries (hard boundaries), sub-chunk sections exceeding 1,000 characters with 100-character overlap strictly within section boundaries, and enrich each chunk with `source_file_name`, storage path, 0-based `chunk_index`, `total_chunks`, and active header hierarchy (`h1`, `h2`, `h3`).

**Independent Test**: Process Markdown text with diverse heading depths and paragraphs >1000 characters; assert that no chunk exceeds 1,000 characters, overlap is exactly 100 characters within sections, no text crosses header boundaries, and each chunk contains accurate sequential index, total chunk count, and header metadata.

### Tests for User Story 3

- [X] T022 [P] [US3] Create unit/integration tests in `tests/unit/test_hierarchical_chunker.py` validating H1/H2/H3 hard boundary enforcement, 1,000-character max limit, 100-character section-bounded overlap, fallback for documents without headers, and metadata enrichment

### Implementation for User Story 3

- [X] T023 [US3] Implement heading parsing and context stack tracking (`h1`, `h2`, `h3`) in `src/knowledge_platform/ingestion/chunker.py`
- [X] T024 [US3] Implement section sub-chunking with 1,000-character max length and 100-character sliding-window overlap strictly within the active header section in `src/knowledge_platform/ingestion/chunker.py`
- [X] T025 [US3] Implement chunk sequence stamping (0-based `chunk_index` and `total_chunks = len(chunks)`) and metadata enrichment (`source_file_name`, `storage_path`, `document_id`) in `src/knowledge_platform/ingestion/chunker.py`
- [X] T026 [US3] Update document record in MongoDB with `chunk_count` and update `processing_status` to `chunked` in `src/knowledge_platform/ingestion/db.py`

**Checkpoint**: User Stories 1, 2, and 3 work end-to-end — documents are discovered, parsed to Markdown, and segmented into enriched hierarchical chunks.

---

## Phase 6: User Story 4 - Vector Embedding Generation and Vector Store Synchronization (Priority: P1)

**Goal**: Convert chunk textual content into vector embeddings via Vertex AI (`gemini-embedding-001`), store points with payload metadata in Qdrant `document_chunks` collection, purge old vectors by `document_id` for updated documents, and remove vectors by `document_id` for deleted documents.

**Independent Test**: Ingest a document and verify Qdrant points exist with payload metadata. Re-run with an updated document and verify old vectors are replaced without duplicate vectors. Delete the source document and verify all vectors matching `document_id` are purged from Qdrant.

### Tests for User Story 4

- [X] T027 [P] [US4] Create integration test in `tests/integration/test_ingestion_vector_sync.py` verifying batch vector indexing in Qdrant, payload metadata fidelity (`source_file_name`, `chunk_index`, `total_chunks`, `h1`, `h2`, `h3`), vector replacement on document update, and vector deletion on document removal

### Implementation for User Story 4

- [X] T028 [US4] Implement chunk batching and vector embedding generation in `src/knowledge_platform/ingestion/embeddings.py` using `VertexAIEmbeddingClient`
- [X] T029 [US4] Implement batch vector upserting with `VectorPayload` metadata in `src/knowledge_platform/ingestion/vector_store.py`
- [X] T030 [US4] Implement payload-filtered vector deletion by `document_id` (`points_selector=FilterSelector(...)`) in `src/knowledge_platform/ingestion/vector_store.py` for update and delete lifecycles
- [X] T031 [US4] Update document record in MongoDB to `processing_status: "indexed"` (or `action_status: "deleted"`) in `src/knowledge_platform/ingestion/db.py`

**Checkpoint**: User Stories 1, 2, 3, and 4 are complete — vector embeddings are indexed and synchronized across creation, modification, and deletion lifecycles.

---

## Phase 7: User Story 5 - End-to-End Execution Traceability, CLI & Fresh-Start Reset (Priority: P2)

**Goal**: Implement the overarching `IngestionPipeline` orchestrator, enforce structured Loguru logging bound with `execution_id`, `document_id`, and `chunk_id`, provide a fresh-start purge mechanism (`INGESTION_RESET_ON_START` / `--reset-on-start`), and deliver a command-line interface.

**Independent Test**: Execute the ingestion CLI (`python -m knowledge_platform.ingestion.cli --directory manuals/ --reset-on-start`) over a test directory; verify Qdrant and MongoDB are cleared, documents are processed, structured logs are emitted, and final execution summary record is saved in MongoDB.

### Tests for User Story 5

- [X] T032 [P] [US5] Create comprehensive unmocked end-to-end integration test in `tests/integration/test_ingestion_pipeline.py` testing the complete pipeline lifecycle, document updates, deletions, error containment, and `--reset-on-start` against live MinIO, MongoDB, and Qdrant containers

### Implementation for User Story 5

- [X] T033 [US5] Implement `IngestionPipeline` orchestrator in `src/knowledge_platform/ingestion/pipeline.py` coordinating discovery, conversion, chunking, indexing, and state recording
- [X] T034 [US5] Implement fresh-start purge logic in `src/knowledge_platform/ingestion/pipeline.py` dropping/recreating the Qdrant `document_chunks` collection and dropping/clearing MongoDB `executions` and `documents` collections when `reset_on_start` is enabled
- [X] T035 [US5] Implement per-document error isolation and terminal execution status calculation (`completed`, `completed_with_errors`, `failed`) in `src/knowledge_platform/ingestion/pipeline.py`
- [X] T036 [US5] Implement CLI entrypoint with argument parsing (`--directory`, `--bucket`, `--reset-on-start`) in `src/knowledge_platform/ingestion/cli.py`
- [X] T037 [US5] Enforce Loguru contextual structured logging across all pipeline phases with `execution_id`, `document_id`, `chunk_id`, and `storage_path` in `src/knowledge_platform/ingestion/pipeline.py` and `src/knowledge_platform/ingestion/cli.py`

**Checkpoint**: All user stories (US1–US5) are fully operational and accessible via both Python API and CLI.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Quality gate validation, package exports, and end-to-end verification

- [X] T038 [P] Export public interfaces (`IngestionPipeline`, `IngestionSettings`, domain models, exceptions) in `src/knowledge_platform/ingestion/__init__.py`
- [X] T039 Execute Ruff linting and formatting validation (`uv run ruff check .` and `uv run ruff format --check .`) and fix any code style issues
- [X] T040 Execute strict Mypy static type checking (`uv run mypy src/ tests/`) and resolve any typing ambiguities
- [X] T041 Execute full integration test suite (`uv run pytest tests/integration/test_ingestion_pipeline.py -v`) against live containers
- [X] T042 Validate all runnable scenarios documented in `specs/002-ingestion-pipeline/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1: Setup (T001-T005)
    │
    ▼
Phase 2: Foundational (T006-T010)
    │
    ├─────────────────────────────────────────────────┐
    ▼                                                 ▼
Phase 3: User Story 1 (T011-T016) [P1]       Phase 5: User Story 3 (T022-T026) [P1]
    │                                                 │ (Chunker logic independent)
    ▼                                                 │
Phase 4: User Story 2 (T017-T021) [P1]                │
    │                                                 │
    └───────────────────────┬─────────────────────────┘
                            ▼
               Phase 6: User Story 4 (T027-T031) [P1]
                            │
                            ▼
               Phase 7: User Story 5 (T032-T037) [P2]
                            │
                            ▼
               Phase 8: Polish & Gates (T038-T042)
```

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Foundational Phase (Phase 2). Can start immediately after foundation is established.
- **User Story 2 (P1)**: Integrates with User Story 1 (downloads documents discovered by US1).
- **User Story 3 (P1)**: Chunker logic (`chunker.py`) is modular and can be implemented and unit-tested in parallel with US1/US2.
- **User Story 4 (P1)**: Integrates chunk output from US3 and document status from US1/US2 to generate embeddings and sync Qdrant vectors.
- **User Story 5 (P2)**: Unites all components into the orchestrator and CLI with fresh-start reset and full logging.

---

## Parallel Execution Opportunities

### Within Phase 1 (Setup)
- `T003` (`.env.example`), `T005` (`config.py`) can run in parallel with `T001` (`docker-compose.yml`).

### Within Phase 2 (Foundational)
- `T006` (`models.py`), `T007` (`exceptions.py`), `T009` (`vector_store.py`), and `T010` (`embeddings.py`) can be implemented in parallel.

### User Stories in Parallel
- `T011`–`T016` (US1: Discovery & MongoDB state) and `T022`–`T026` (US3: Hierarchical Markdown chunker) can be implemented completely concurrently by different developers, as the chunker is an independent text-transformation engine.

---

## Implementation Strategy

### MVP Milestone (User Story 1)
1. Complete Phase 1: Setup (T001–T005)
2. Complete Phase 2: Foundational (T006–T010)
3. Complete Phase 3: User Story 1 (T011–T016)
4. **MVP Validation**: Run `tests/integration/test_ingestion_discovery.py` to confirm storage files are discovered, filtered, categorized, and persisted in MongoDB.

### Incremental Feature Additions
1. Add User Story 2 (T017–T021) → Verify Markdown conversion and artifact storage in MinIO.
2. Add User Story 3 (T022–T026) → Verify hierarchical chunking and metadata preservation.
3. Add User Story 4 (T027–T031) → Verify Vertex AI embeddings and Qdrant vector sync/purges.
4. Add User Story 5 (T032–T037) → Verify complete orchestrator, CLI, reset flag, and Loguru logging.
5. Complete Polish & Quality Gates (T038–T042) → Full Ruff, Mypy, and unmocked integration test passes.
