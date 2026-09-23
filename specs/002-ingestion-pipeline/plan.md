# Implementation Plan: Recursive PDF Ingestion Pipeline with Markdown Hierarchical Chunking and Vector Indexing

**Branch**: `002-ingestion-pipeline` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-ingestion-pipeline/spec.md`

---

## Summary

Build an asynchronous ingestion pipeline that recursively browses PDF documents in an object storage directory path, classifies document lifecycle actions (`created`, `updated`, `deleted`, `unchanged`), sequentially downloads and converts PDFs to structured Markdown using Microsoft's `markitdown`, saves Markdown artifacts in object storage, hierarchically segments Markdown by headers (H1, H2, H3) and length (1,000 characters max with 100-character overlap strictly within header sections), enriches chunks with source file name and provenance metadata, generates vector embeddings using GCP Vertex AI Agent Platform (`gemini-embedding-001`) with explicit API key authentication, indexes vectors in Qdrant running under Docker Compose, synchronizes document updates and deletions, and tracks all state in MongoDB via `motor` and Pydantic models. Comprehensive structured contextual logging is enforced across all processing steps using `loguru`.

---

## Technical Context

**Language/Version**: Python >=3.12 (WSL / Ubuntu)

**Primary Dependencies**:
- `markitdown` (>=0.1.8) — PDF parsing and Markdown conversion
- `qdrant-client` (>=1.13.0) — Native asynchronous vector database client
- `motor` (>=3.7.0) & `pymongo` (>=4.11.0) — Asynchronous MongoDB driver
- `pydantic` (>=2.9.0) & `pydantic-settings` (>=2.5.0) — Strict domain modeling and environment configuration
- `google-genai` (>=2.25.0) — Google Cloud Vertex AI SDK with explicit API key authentication
- `loguru` (>=0.7.2) — Structured, contextual logging
- `aioboto3` (>=13.2.0) — Asynchronous MinIO/S3 object storage client

**Storage**:
- MinIO (Object Storage): source PDFs and converted Markdown artifacts (`knowledge-source` bucket)
- MongoDB 7.0 (`mongo:7.0`): execution and document lifecycle state database (`knowledge_platform` database)
- Qdrant (`qdrant/qdrant:v1.13.4`): vector database for chunk embeddings and metadata payloads (`document_chunks` collection)

**Testing**:
- `pytest` (>=8.3.0) & `pytest-asyncio` (>=0.24.0)
- Unmocked end-to-end integration tests (`tests/integration/test_ingestion_pipeline.py`) running against live containerized MinIO, MongoDB, and Qdrant instances

**Target Platform**: Linux (WSL / Ubuntu) with Docker & Docker Compose

**Project Type**: Asynchronous Core Data Pipeline & CLI Engine

**Performance Goals**:
- Sequential one-at-a-time document processing to bound worker memory footprint
- Sub-second vector deletion by `document_id` payload filter during updates and deletions
- Discovery and action classification under 2 seconds for directories with 100+ documents

**Constraints**:
- Strict non-negotiable Loguru structured logging with contextual attributes (`execution_id`, `document_id`, `chunk_id`, `storage_path`)
- Explicit API key authentication for Vertex AI (zero implicit ADC machine credentials)
- Zero LangChain dependency bloat; clean, modular typed Python architecture
- Zero mocks in standard integration test suites
- All container dependencies defined in `docker-compose.yml` with named volumes and health checks

**Scale/Scope**:
- Multi-page complex technical PDFs
- Deeply nested directories in object storage
- Hundreds of documents and thousands of vector chunks per execution

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Rule | Compliance Status | Analysis & Verification |
|---|---|---|
| **I. Maintainability Over Shortcuts (NON-NEGOTIABLE)** | **PASS** | Architecture is strictly modular with clear domain boundaries (`src/knowledge_platform/ingestion/`). Explicit Pydantic models for `ExecutionRecord`, `DocumentRecord`, `DocumentChunk`, and `VectorPayload`. LangChain rejected to avoid opaque abstraction leaks. |
| **II. Vertex AI & API Key Auth** | **PASS** | Embedding generation uses GCP Vertex AI (`gemini-embedding-001`) via `google-genai` with explicit API key authentication (`VERTEX_API_KEY`) injected from `.env`. Zero ambient credentials. |
| **III. End-to-End Verification Over Mocks (NON-NEGOTIABLE)** | **PASS** | Verification centers on unmocked end-to-end integration tests (`tests/integration/test_ingestion_pipeline.py`) running against real MinIO, MongoDB, and Qdrant containers. |
| **IV. Containerized Isolation & Minimal Images** | **PASS** | All infrastructure services (MinIO, MongoDB 7.0, Qdrant v1.13.4) are defined in `docker-compose.yml` with pinned releases, named volumes, and health checks. |
| **V. Tooling via WSL & UV** | **PASS** | All dependencies managed and locked with `uv`. Execution runs via `uv run`. |
| **VI. Structured Contextual Logging via Loguru (NON-NEGOTIABLE)** | **PASS** | `loguru` used exclusively across all pipeline modules. Zero raw `print()` statements. Log events bound with `execution_id`, `document_id`, `chunk_id`, and `storage_path`. |
| **Governance: Manual Commits Only** | **PASS** | Automated agents will never execute `git commit` or `git push`. All version control commits remain strictly manual by the human developer. |
| **Governance: Out-of-Scope Files** | **PASS** | `.notes/` and `design.excalidraw.png` are completely ignored and untouched. |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-ingestion-pipeline/
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0: Technology selection and architectural decisions
├── data-model.md        # Phase 1: Entity models, schemas, and lifecycle states
├── quickstart.md        # Phase 1: Runnable end-to-end validation guide
├── contracts/           # Phase 1: Service and infrastructure interface contracts
│   ├── docker-compose-contract.md
│   ├── pipeline-contract.md
│   └── storage-records-contract.md
└── checklists/
    └── requirements.md  # Specification quality checklist
```

### Source Code Layout (repository root)

```text
.
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── src/
│   └── knowledge_platform/
│       ├── __init__.py
│       ├── config.py
│       ├── storage/                     # Existing MinIO async storage client
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── models.py
│       │   └── exceptions.py
│       └── ingestion/                   # New ingestion pipeline module
│           ├── __init__.py
│           ├── models.py                # Pydantic schemas (Execution, Document, Chunk)
│           ├── exceptions.py            # Ingestion domain exceptions
│           ├── discovery.py             # Recursive object discovery & lifecycle categorization
│           ├── parser.py                # MarkItDown PDF conversion & text extraction
│           ├── chunker.py               # HierarchicalMarkdownChunker (H1/H2/H3 + 1000/100 overlap)
│           ├── embeddings.py            # Vertex AI embeddings client (API key auth)
│           ├── vector_store.py          # Qdrant async collection & vector manager
│           ├── db.py                    # MongoDB Motor async repository
│           ├── pipeline.py              # IngestionPipeline orchestrator
│           └── cli.py                   # Ingestion CLI trigger entrypoint
└── tests/
    └── integration/
        ├── __init__.py
        ├── test_object_storage.py       # Existing storage tests
        └── test_ingestion_pipeline.py   # Live end-to-end integration tests
```

**Structure Decision**: Single modular Python project located under `src/knowledge_platform/`, dividing concerns into clean domain packages (`storage/`, `ingestion/`). Infrastructure services are unified in root `docker-compose.yml`.

---

## Complexity Tracking

> **No constitutional violations exist. Direct modular architecture chosen over heavy frameworks.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| None | N/A | LangChain rejected in favor of native modular Python architecture for strict typing, minimal dependencies, and direct control over chunk boundaries and vector purges. |
