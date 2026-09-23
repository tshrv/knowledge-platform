# Research & Architecture Decisions: Recursive PDF Ingestion Pipeline

**Feature**: `002-ingestion-pipeline`  
**Date**: 2026-09-22  
**Status**: Completed  

---

## 1. PDF to Markdown Conversion Engine

### Decision
Use Microsoft's `markitdown` library (`markitdown>=0.1.8`) for parsing PDF documents and converting them into structured Markdown.

### Rationale
- **Structural Fidelity**: Converts document hierarchy directly into Markdown headings (`#`, `##`, `###`), tables, and paragraphs, preserving semantic structure needed for hierarchical chunking.
- **Lightweight & Self-Contained**: Avoids heavy external runtime dependencies like Java or complex C++ bindings.
- **Python Ecosystem Integration**: Operates natively in Python 3.12 via file path or stream.

### Alternatives Considered
- **`pypdf` / `pdfminer.six`**: Extracts raw text blocks and coordinates but does not infer or generate Markdown heading syntax (`#`, `##`), which would require developing a fragile heading-inference heuristic.
- **`unstructured`**: High structural extraction accuracy, but has a massive installation footprint (>2GB), dozens of heavyweight transitive dependencies, and complex container image requirements that violate Constitution Principle IV (minimal containers).
- **`pymupdf4llm`**: Efficient, but `markitdown` was specifically requested by the user and provides clean, standard Markdown conversion out of the box.

### Error & Edge Case Handling
- **Scanned / Image-Only PDFs**: `markitdown` returns empty or whitespace-only content when no digital text layer exists. The parser detects `not text_content.strip()` and raises a domain `UnparseableDocumentError("PDF contains no extractable digital text layers")`, causing the pipeline to mark the document as `failed` without crashing execution.
- **Corrupted / Password-Protected PDFs**: Any parser exception is caught and wrapped into `DocumentParsingError`, updating the document database record to `failed` with descriptive error context.

---

## 2. Vector Database Infrastructure & Client

### Decision
Deploy **Qdrant** (`qdrant/qdrant:v1.13.4`) via `docker-compose.yml` with persistent storage on a named Docker volume (`qdrant_data`), accessed programmatically using `qdrant-client`'s native `AsyncQdrantClient`.

### Rationale
- **High Performance & Low Resource Footprint**: Built in Rust; exceptionally fast nearest-neighbor search with low memory overhead.
- **Built-in Web Management UI**: Accessible out of the box on port `6333/dashboard`, enabling operators to visually inspect collections, points, and payload metadata without additional tooling.
- **Native Async Client**: `AsyncQdrantClient` provides full non-blocking asyncio support, aligning with the platform's async architecture.
- **Rich Payload Filtering & Deletion**: Supports instantaneous point deletion filtered by payload field:
  ```python
  await client.delete(
      collection_name="document_chunks",
      points_selector=models.FilterSelector(
          filter=models.Filter(
              must=[
                  models.FieldCondition(
                      key="document_id",
                      match=models.MatchValue(value=document_id),
                  )
              ]
          )
      ),
  )
  ```
  This satisfies the requirement to purge old vectors upon document update or deletion.

### Alternatives Considered
- **Chroma**: Weaker async support and historically less stable server mode compared to Qdrant's containerized release.
- **pgvector (PostgreSQL)**: Requires relational schema migrations and custom SQL for vector operations; Qdrant's dedicated vector engine offers simpler payload indexing and out-of-the-box management dashboard.

---

## 3. Metadata & Document State Database: MongoDB with Motor and Pydantic

### Decision
Deploy **MongoDB 7.0** (`mongo:7.0`) via `docker-compose.yml` with persistent named volume (`mongo_data`), accessed using `motor` (`motor>=3.7.0`, official async driver) paired with explicit Pydantic v2 domain schemas.

### Rationale
- **Flexible Document Tracking**: Allows storing rich document metadata, variable-depth header structures, processing milestones, and error traces without rigid relational schema migrations.
- **Atomic Upserts & Timestamps**: Supports atomic find-and-modify operations and indexed queries on `storage_path`, `execution_id`, and `action_status`.
- **Async Python Integration**: `motor.motor_asyncio.AsyncIOMotorClient` operates seamlessly within Python asyncio event loops.
- **Strict Pydantic Boundary Validation**: In accordance with Constitution Principle I, raw MongoDB dictionaries are validated through explicit Pydantic models (`ExecutionRecord`, `DocumentRecord`) at all repository boundaries.

### Alternatives Considered
- **Beanie / MongoEngine**: Heavyweight ODM frameworks that obscure database interactions, introduce metaclass complexity, and frequently create lifecycle coupling. Using `motor` with Pydantic serialization provides full typing, zero magic, and explicit boundary validation.
- **SQLite / PostgreSQL**: Relational tables require formal migrations for evolving metadata dictionaries; MongoDB's document model naturally accommodates hierarchical document schemas while retaining strong indexing.

---

## 4. Architectural Framework: Native Modular Architecture vs. LangChain

### Decision
**Implement a native, modular, strictly-typed Python pipeline; DO NOT use LangChain.**

### Rationale
- **Constitution Principle I Compliance**: The Constitution explicitly mandates:
  > *"Maintainability & Reliability Over Shortcuts (NON-NEGOTIABLE)... Architecture MUST remain modular with explicit domain boundaries, clear interfaces, and comprehensive typing. Every significant architectural decision MUST be backed by documented reasons... Whenever primitive types become complex, developers MUST define explicit Pydantic models."*
- **Avoid Abstraction Leakage & Instability**: LangChain frequently changes class hierarchies, wraps standard driver calls in generic wrappers, and obscures async stack traces.
- **Custom Specification Requirements**:
  1. Header-partitioned chunking with hard boundaries (no overlap across headers).
  2. Sequential 0-based chunk indices with `total_chunks` stamped on every chunk.
  3. Contextual metadata inheritance (`file_name`, `storage_path`, `document_id`, `h1`, `h2`, `h3`).
  4. Precise vector purge by `document_id`.
  These requirements are fulfilled in ~80 lines of transparent, fully-typed Python without the 300+ megabytes of transitive dependencies that LangChain introduces.
- **API Key Compliance**: LangChain's Google Vertex AI components frequently default to implicit ADC credentials rather than explicit API key configuration, conflicting with Constitution Principle II.

### Alternatives Considered
- **LangChain (`langchain`, `langchain-community`)**: Evaluated per user prompt ("Can use langchain as framework (open for discussion if needed)"). Rejected due to architectural bloat, opaque abstractions, credential handling limitations, and incompatibility with clean domain modeling.

---

## 5. Embedding Generation: Vertex AI Agent Platform with API Key

### Decision
Use Google's official unified **`google-genai`** SDK (`google-genai>=2.25.0`) with model **`gemini-embedding-001`** (or `text-embedding-004`), configured explicitly with an API key via environment variable `VERTEX_API_KEY`.

### Rationale
- **Constitution Principle II Compliance**:
  > *"All large language model (LLM) and agent capabilities MUST interface through Google Cloud Platform's agent platform (Vertex AI). Vertex AI access MUST be configured explicitly using the API key authentication method rather than ambient or implicit machine credentials... API keys MUST NEVER be hardcoded, committed to version control, or exposed in logs; they MUST be injected via environment variables."*
- **Async Batch Embeddings**: `google-genai` supports non-blocking batch embedding generation:
  ```python
  client = genai.Client(vertexai=True, api_key=settings.vertex_api_key)
  response = await client.aio.models.embed_content(
      model="gemini-embedding-001",
      contents=[chunk.text for chunk in batch],
  )
  ```
- **Embedding Dimensions**: Standard output dimension is 768 float values, compatible with Qdrant collection vector size using Cosine similarity.

### Fallback / Offline Testing Strategy
- For unmocked local testing without active Vertex AI credentials, the embedding client interface (`EmbeddingServiceProtocol`) allows a local deterministic embedding provider in test container setups while production uses live Vertex AI.

---

## 6. Fresh Ingestion Flag via Environment Variable

### Decision
Support environment variable `INGESTION_RESET_ON_START: bool = False`, with runtime override capability via execution trigger parameters (`reset_on_start=True`).

### Rationale
- When enabled, before executing discovery, the pipeline:
  1. Deletes and recreates the Qdrant `document_chunks` collection.
  2. Drops or truncates the MongoDB `documents` and `executions` collections.
  3. Emits structured Loguru audit logs documenting the reset.
- This allows clean re-testing and idempotent cold-start ingestion as explicitly requested by the user.

---

## 7. Hierarchical Markdown Chunker Design

### Decision
Implement a specialized, deterministic chunker (`HierarchicalMarkdownChunker`) that executes in two phases:
1. **Header Segmentation**: Parses Markdown line by line, detecting `# `, `## `, `### ` heading tokens to establish semantic sections and maintain the active heading context stack `(h1, h2, h3)`.
2. **Length Sub-Chunking with Bounded Overlap**:
   - Each heading section is evaluated individually.
   - If length <= 1,000 characters, it becomes a single chunk.
   - If length > 1,000 characters, it is segmented using a sliding window: chunk length 1,000 characters, step size 900 characters (providing exactly 100 characters of overlap).
   - Overlap is strictly constrained within the current heading section and never pulls characters across heading transitions.
3. **Metadata Enrichment & Sequence Stamping**:
   - Upon completing chunk segmentation for the document, each chunk is assigned:
     - `chunk_id`: UUIDv4 string.
     - `document_id`: Parent document ID.
     - `file_name`: Original PDF filename.
     - `storage_path`: Key in object storage.
     - `chunk_index`: 0-based sequential integer (`0` to `total_chunks - 1`).
     - `total_chunks`: Count of all chunks generated for this document.
     - `h1`, `h2`, `h3`: Inherited heading text or `None`.

---

## 8. Structured Contextual Observability via Loguru

### Decision
Use `loguru` exclusively for all logging across the ingestion pipeline, strictly enforcing structured contextual bindings.

### Rationale
- **Constitution Principle VI Compliance**:
  > *"Structured Contextual Logging via Loguru (NON-NEGOTIABLE)... All Python logging MUST be implemented exclusively using loguru. Standard library logging and raw print() statements in application code are strictly prohibited. Every log record MUST include a clear, descriptive human-readable message alongside structured contextual metadata (e.g., unique request IDs, execution/job IDs, object keys, session tokens, or entity identifiers)..."*
- Contextual binding pattern:
  ```python
  doc_logger = logger.bind(
      execution_id=execution_id,
      document_id=doc_id,
      storage_path=storage_path,
  )
  doc_logger.info("Successfully converted PDF to Markdown")
  ```
