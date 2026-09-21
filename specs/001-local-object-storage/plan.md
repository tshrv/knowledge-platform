# Implementation Plan: Local Object Storage with Built-in Web UI

**Branch**: `001-local-object-storage` | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-local-object-storage/spec.md`

---

## Summary

Provision a local, S3-compatible object storage infrastructure using MinIO running under Docker Compose. The environment automatically pre-creates the default `knowledge-source` bucket upon startup using an ephemeral MinIO Client (`mc`) init container. Users upload source documents directly via MinIO's built-in Web Console UI on port 9001 without writing custom upload UI or custom upload API endpoints. Stored data is persisted across container restarts and recreations using a named Docker volume (`minio_data`). A lightweight, strictly-typed asynchronous Python storage client (`aioboto3` + Pydantic) provides downstream ingestion components with non-blocking read access. Real end-to-end integration tests validate live container health, bucket existence, and unmocked asynchronous object persistence.

---

## Technical Context

**Language/Version**: Python >=3.12 (WSL / Ubuntu)

**Primary Dependencies**: `aioboto3` (>=13.2.0), `aiobotocore` (>=2.15.0), `pydantic` (>=2.9.0), `pydantic-settings` (>=2.5.0), `boto3-stubs[s3]`

**Storage**: MinIO (`minio/minio:RELEASE.2024-11-07T00-52-19Z`) with named Docker volume (`minio_data`)

**Testing**: `pytest` (>=8.3.0), `pytest-asyncio` (>=0.24.0), unmocked end-to-end integration tests executed via `uv run pytest tests/integration/`

**Target Platform**: Linux (WSL / Ubuntu) with Docker & Docker Compose

**Project Type**: Infrastructure & Service Foundation (Docker Compose + Asynchronous Python Core Library)

**Performance Goals**: Service startup and bucket availability within <15 seconds; non-blocking asynchronous document retrieval

**Constraints**: Specific container version pinning (no `:latest` tags); all configuration via `.env` / `.env.example`; zero custom upload application code needed; asynchronous access for downstream services; zero mocks in standard test suites

**Scale/Scope**: Local developer workstation; supports gigabyte-scale document sets and hundreds of source documents in `knowledge-source`

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Rule | Compliance Status | Analysis & Verification |
|---|---|---|
| **I. Maintainability Over Shortcuts** | **PASS** | Clear separation between infrastructure orchestration (`docker-compose.yml`), configuration (`config.py`), and async storage client (`storage/client.py`). Full type annotations with Pydantic schemas. |
| **II. Vertex AI & API Key Auth** | **PASS** | N/A for this storage feature (no LLM components). Project structure maintains clean isolation for future LLM integration. |
| **III. End-to-End Verification Over Mocks** | **PASS** | Skip unit tests by default. Verification uses unmocked async integration tests (`test_object_storage.py`) connecting directly to the running MinIO container. |
| **IV. Containerized Isolation & Minimal Images** | **PASS** | MinIO and MinIO Client (`mc`) defined in `docker-compose.yml` with immutable release tags and persistent named volume (`minio_data`). |
| **V. Tooling via WSL & UV** | **PASS** | Python dependencies managed with `uv`. Execution via `uv run`. |
| **Governance: Manual Commits Only** | **PASS** | No automated git commits will be generated or executed. All commits remain the exclusive domain of the human developer. |
| **Governance: Out-of-Scope Files** | **PASS** | `design.excalidraw.png` is untouched and out of scope. |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-local-object-storage/
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0: Technology selection and architectural decisions
├── data-model.md        # Phase 1: Entity models, schemas, and lifecycle states
├── quickstart.md        # Phase 1: Runnable end-to-end validation guide
├── contracts/           # Phase 1: Service and client interface contracts
│   ├── docker-compose-contract.md
│   └── storage-client-contract.md
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
│       └── storage/
│           ├── __init__.py
│           ├── client.py
│           └── models.py
└── tests/
    └── integration/
        ├── __init__.py
        └── test_object_storage.py
```

**Structure Decision**: Single-package Python project structure with root-level `docker-compose.yml` for infrastructure service orchestration. Python source code lives in `src/knowledge_platform/` with isolated modules for settings and asynchronous storage access. Verification tests live in `tests/integration/`.

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No constitutional violations identified. Design adheres strictly to all governance principles.*
