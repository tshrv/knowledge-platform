<!--
# Sync Impact Report
- Version change: 2.2.0 → 2.3.0
- Modified principles: None
- Added sections / policies:
  - Core Principles: Added "VI. Structured Contextual Logging via Loguru (NON-NEGOTIABLE)" mandating `loguru` for all Python logging, accompanied by human-readable messages and structured filtering metadata (unique IDs, entity keys, correlation IDs).
  - Technology Stack & Environment Standards: Added `loguru` as the sanctioned observability standard and strictly prohibited raw `print()` statements.
  - Quality Gates & Development Workflow: Added "Structured Logging Standards" quality gate.
- Removed sections: None
- Follow-up TODOs: None
-->

# Knowledge Platform Constitution

## Core Principles

### I. Maintainability & Reliability Over Shortcuts (NON-NEGOTIABLE)
Code MUST prioritize long-term maintainability, readability, and reliability over expedience or temporary shortcuts. Architecture MUST remain modular with explicit domain boundaries, clear interfaces, and comprehensive typing. Every significant architectural decision MUST be backed by documented reasons, expected benefits, and analyzed trade-offs. All user inputs MUST be strictly validated at system boundaries before entering internal processing pipelines. Type hints are mandatory across all Python code; whenever primitive types (e.g., nested dictionaries, arbitrary tuples, loose parameters) become complex, developers MUST define explicit Pydantic models to ensure clarity, self-documentation, and runtime validation. Failures MUST be handled defensively and gracefully with explicit domain exceptions and structured context; silent error suppression is strictly forbidden.

*Rationale: Production AI platforms compound technical debt rapidly if shortcuts are tolerated. Legible architecture, documented trade-offs, strict boundary validation, and clear data models ensure long-term stability and maintainability.*

### II. Vertex AI Integration & API Key Authentication
All large language model (LLM) and agent capabilities MUST interface through Google Cloud Platform's agent platform (Vertex AI). Vertex AI access MUST be configured explicitly using the API key authentication method rather than ambient or implicit machine credentials, ensuring uniform credential scoping across development and deployment. API keys MUST NEVER be hardcoded, committed to version control, or exposed in logs; they MUST be injected via environment variables. LLM client integrations MUST be decoupled behind clean gateway interfaces with explicit configuration to support robust end-to-end execution.

*Rationale: Explicit API key configuration isolates credential boundaries and guarantees reproducible access patterns across WSL local environments and automated pipelines.*

### III. End-to-End Integration Verification Over Mocks (NON-NEGOTIABLE)
Verification MUST center on real integration tests running actual features end-to-end across all participating components and verifying the final result. Mocking is strictly prohibited in standard verification workflows; tests MUST exercise real component wiring, genuine external service interactions, and live pipelines. Unless explicitly needed for isolated, high-complexity algorithmic logic, unit tests MUST be skipped in favor of end-to-end integration coverage. Separate development and test environments of services (e.g., dedicated test containers in Docker Compose) MAY be established when needed to execute tests reliably without state pollution.

*Rationale: In complex AI and data platforms, unit tests and mocks routinely mask real integration failures, schema drift, and network protocol breakages. Real end-to-end tests provide authentic confidence in system behavior.*

### IV. Containerized Component Isolation & Minimal Images
Any supporting infrastructure or stateful service requirement (such as relational databases, vector stores, caching layers, or search indexes) MUST be containerized using Docker. All service dependencies MUST be formally defined, networked, and configured in `docker-compose.yml`, providing distinct development and test configurations where needed. Docker images MUST be kept minimal by employing multi-stage builds, slim base images, and strict exclusion of build-time caches and tools. Developers and automated tests MUST NOT rely on uncontained, natively installed services on the host machine.

*Rationale: Docker Compose provides reproducible, isolated local environments that maintain parity with production infrastructure, while minimal container images reduce attack surface, build latency, and deployment overhead.*

### V. Deterministic Development Tooling via WSL & UV
The sanctioned local development platform is Linux running on Windows Subsystem for Linux (WSL/Ubuntu). All Python runtime, virtual environment, and dependency management MUST be executed exclusively through `uv`. Dependency specifications and lockfiles (`uv.lock`) MUST be committed and strictly enforced across environments. Direct usage of unmanaged global interpreters, raw pip, or competing package managers is prohibited in project workflows.

*Rationale: Standardizing on WSL and uv ensures instantaneous, reproducible dependency resolution and eliminates platform-specific packaging divergence.*

### VI. Structured Contextual Logging via Loguru (NON-NEGOTIABLE)
Comprehensive, structured logging is NON-NEGOTIABLE across the platform. All Python logging MUST be implemented exclusively using `loguru`. Standard library `logging` and raw `print()` statements in application code are strictly prohibited. Every log record MUST include a clear, descriptive human-readable message alongside structured contextual metadata (e.g., unique request IDs, execution/job IDs, object keys, session tokens, or entity identifiers) to enable precise filtering, correlation, and searchability across distributed processing pipelines and async workflows. Uncontextualized, generic log statements lacking situational metadata are forbidden at system boundaries and critical operational paths.

*Rationale: Distributed AI and retrieval pipelines involve concurrent, asynchronous operations across components. Standardizing on Loguru with structured contextual metadata guarantees immediate observability, trace correlation, and rapid failure diagnosis in production.*

## Technology Stack & Environment Standards
- **Runtime & Environment**: Python 3.12+ on Ubuntu (WSL).
- **Dependency Management**: `uv` for package management, virtual environment isolation, and script execution (`uv run`).
- **AI & Agent Foundation**: GCP Vertex AI (Agent Platform) initialized via explicit API key authentication.
- **Observability & Structured Logging**: `loguru` for structured, contextual logging across all Python modules; raw `print()` statements are strictly forbidden.
- **Data Modeling & Validation**: Mandatory type hints across all Python code; Pydantic models for all user input validation, complex payload definitions, and structured domain entities.
- **Infrastructure Services**: Docker & Docker Compose with minimal images (multi-stage builds, slim bases) for all stateful dependencies; separate dev and test service environments when required.
- **Configuration & Secrets**: Twelve-factor configuration using environment variables and git-ignored `.env` files; template `.env.example` must be kept up to date without real credentials.

## Quality Gates & Development Workflow
- **Architectural Decision Reviews**: Every significant architectural choice MUST document its rationale, expected benefits, and trade-offs before implementation.
- **Boundary Validation**: All user inputs and public interface parameters MUST be validated via Pydantic models prior to business logic execution.
- **Structured Logging Standards**: All business logic, system boundaries, and asynchronous pipelines MUST emit structured Loguru events bound with contextual attributes (e.g., entity IDs, operation keys, trace IDs); unformatted print statements or unstructured logs will fail review.
- **Linting & Code Formatting**: Code MUST pass strict linting and formatting checks (via Ruff) before commit with zero tolerance for unresolved errors.
- **Static Type Safety**: Full type annotations are mandatory across all public and internal interfaces, validated via static type checking.
- **Integration Testing Gates**: Test suites MUST execute end-to-end feature verification (`uv run pytest`) against live or containerized components without mocking. Unit tests are skipped by default unless explicitly needed.
- **Infrastructure & Image Validation**: Compose configurations must validate (`docker compose config`), boot cleanly (`docker compose up -d`), and Dockerfile definitions must enforce minimal image layers.
- **Artifact Ownership & Out-of-Scope Files**: The directory `.notes/` and the file `design.excalidraw.png` are reserved strictly for human maintainer use. Although `.notes/` is tracked and committed in git by the developer, automated agents, AI assistants, and background tools MUST ignore `.notes/` completely: agents MUST NOT read, inspect, create, edit, overwrite, delete, reference, or alter any files within `.notes/`. Similarly, automated agents MUST NOT create, edit, overwrite, delete, or alter `design.excalidraw.png`.
- **Version Control & Git Policy (Manual Commits Only)**: Automated agents, AI assistants, and background tools MUST NEVER execute `git commit`, `git push`, or manipulate repository history. Commits, branch pushes, and git history modifications are strictly reserved for the human developer. Agents may propose changes and draft suggested commit messages, but MUST NOT execute the commit.
- **Review Criteria**: Pull requests and code changes MUST be evaluated against constitutional non-negotiables: no shortcuts, end-to-end integration verification, explicit Pydantic data modeling, and complete interface readability.

## Governance
This Constitution represents the supreme architectural and operational authority for the Knowledge Platform. It supersedes informal agreements, quick fixes, and ad-hoc practices. Any architectural deviation or compromise of maintainability MUST be rejected during review.

All git commits, merges, releases, and repository state transitions MUST be manually executed by the human developer; automated tools are strictly prohibited from committing changes. Human-owned design and personal note assets, including `.notes/` and `design.excalidraw.png`, are strictly outside the scope of automated agents; agents must completely ignore `.notes/`.

Amendments to this Constitution require documenting the proposal, evaluating downstream architectural impact, and reaching explicit maintainer consensus. Constitution versions follow Semantic Versioning:
- **MAJOR**: Incompatible principle removals, redefinitions (such as testing philosophy shifts), or foundational architectural pivots.
- **MINOR**: Addition of new principles, material expansion of quality gates, or stack additions.
- **PATCH**: Wording improvements, clarifications, or non-semantic guideline refinements.

Compliance audits MUST occur during every specification, planning, and code review cycle to guarantee ongoing adherence.

**Version**: 2.3.0 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-09-22
