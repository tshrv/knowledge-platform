# Feature Specification: Recursive PDF Ingestion Pipeline with Markdown Hierarchical Chunking and Vector Indexing

**Feature Branch**: `002-ingestion-pipeline`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Create an ingestion pipeline. The pipeline should take a directory path in object storage, and recursively browse all files in there. Only work for pdf files for now. Any other file, ignore. Each run of the ingestion pipeline is to be considered an \"execution\". In every execution, all files discovered should be recorded in a database, with their path, last modified timestamp, a unique document id etc. Define some status values that records the action status for these files in each execution like, created (newly created), deleted (previously added but now deleted since file not found in that path), updated (file exists in same place but last modified time is later than what exists in record), etc. Based on this, categorise files into created(add to knowledge base), updated(update knowledge base) and deleted (remove from knowledge base). Download file one at a time, parse it, convert to markdown to retain hierarchial structure, store markdown in object storage, save object storage markdown file path in database record as well. Now, the markdown content needs to be divided into chunks, first by headers 1, 2 and 3, then by 1000 characters, along with a 100 character overlap. Assign a unique id to each chunk, and a document id, that this chunk belongs to this document. Also, keep a sequential chunk index and each chunk should know how many total chunks are there. In each chunk, keep the metadata for reference, like header 1, header 2, header 3, etc. whatever is applicable, ensuring to retain important metadata in each chunk. Next, each chunk's content should be converted into embeddings and stored into a vector database, along with metadata. The complete process should log events in all necessary places, with the execution id, document id, chunk id, etc. keeping logs as much relevant as possible."

## Clarifications

### Session 2026-09-22
- Q: What document provenance attributes must be retained in each chunk's metadata in addition to hierarchical headers? → A: Each chunk's metadata MUST include the source file name alongside the storage path, document ID, sequential chunk index, total chunk count, and applicable hierarchical headers (Header 1, Header 2, Header 3).
- Q: Should the 100-character chunk overlap apply strictly within individual header sections, or should it also span across adjacent header boundaries? → A: Within header sections only; headers act as hard boundaries and the 100-character overlap applies strictly when subdividing an individual section that exceeds 1,000 characters, never across different header boundaries.
- Q: When a file at an existing storage path is categorized as updated, should it retain its original unique document ID or receive a newly generated document ID? → A: Retain existing document ID; the document maintains its stable identity across updates while its timestamp, Markdown artifact path, chunk records, and vector embeddings are refreshed.
- Q: How should the pipeline handle scanned or image-only PDF files that contain no extractable text layers? → A: Mark as failed (No OCR); log an error indicating no extractable text was found, mark the document record as failed with an appropriate error message, and continue processing remaining files.
- Q: Should the target directory path input accept an optional bucket name or always assume the platform's default knowledge-source bucket? → A: Default with override; the pipeline defaults to targeting the `knowledge-source` bucket when given a simple path prefix, but supports specifying an explicit bucket name or full storage URI.
- Q: What should be the maximum chunk batch size per request when calling Vertex AI to generate vector embeddings? → A: 50 chunks per batch; embedding requests to Vertex AI MUST batch up to 50 chunks per call, with automatic sub-batching for documents producing more than 50 chunks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recursive File Discovery and Lifecycle Categorization (Priority: P1)

An operator or automated system triggers an ingestion execution targeting a directory path in object storage (defaulting to the `knowledge-source` bucket when a path prefix is given, or specifying an explicit bucket/URI). The pipeline scans the directory recursively, discovers all files, ignores any non-PDF files, and records all discovered PDF files in a database with path, last modified timestamp, unique document ID, and execution details. By comparing discovered files with previous database records for that storage path, the pipeline categorizes each document into an action status: `created` (newly added file), `updated` (file modified since previous execution), `deleted` (file previously recorded under this directory but no longer present), or `unchanged` (file identical to recorded timestamp).

**Why this priority**: Foundational stage of the ingestion pipeline. Accurate discovery, state tracking, and lifecycle change detection determine which documents must be added, updated, or removed from the knowledge base without unnecessary re-processing.

**Independent Test**: Configure a test directory in object storage containing three PDF files and two non-PDF files. Run an initial execution and verify all three PDFs are recorded as `created` while non-PDF files are ignored. Modify one PDF, delete one PDF, and add a fourth PDF; run a second execution and verify the statuses are correctly classified as one `updated`, one `deleted`, one `created`, and one `unchanged`.

**Acceptance Scenarios**:

1. **Given** an object storage directory containing nested PDF files and non-PDF files, **When** an ingestion execution is initiated for that directory path, **Then** only PDF files are recorded, non-PDF files are excluded, and all newly found PDFs are assigned a unique document ID and categorized as `created`.
2. **Given** previously ingested PDF files in the database, **When** an execution detects that a file's last modified timestamp in storage is newer than the recorded timestamp, **Then** the document is categorized as `updated`, retains its existing unique document ID, and is queued for knowledge base re-indexing.
3. **Given** a document previously recorded under a directory path, **When** a subsequent execution scans the directory and finds the file no longer exists in storage, **Then** the document is categorized as `deleted` for removal from the knowledge base.
4. **Given** an existing document whose storage timestamp matches the recorded timestamp, **When** the execution runs, **Then** the document is marked as `unchanged` and skipped from redundant parsing and embedding.

---

### User Story 2 - Sequential PDF Download, Markdown Conversion, and Artifact Storage (Priority: P1)

For every document categorized as `created` or `updated`, the pipeline processes files sequentially ("one at a time"). It downloads the PDF, parses its content, and converts it into structured Markdown to preserve heading and section hierarchy. The converted Markdown file is stored in object storage, and its object storage location is persisted in the document's database record.

**Why this priority**: Essential transformation stage that converts unstructured binary documents into structured textual representations while managing memory footprint through sequential processing.

**Independent Test**: Ingest a sample multi-page PDF document containing multiple heading levels, lists, and paragraphs. Verify the pipeline downloads the file individually, parses it into Markdown format with preserved headers, stores the Markdown artifact in object storage, and updates the document database record with the Markdown storage path.

**Acceptance Scenarios**:

1. **Given** documents categorized as `created` or `updated`, **When** the ingestion pipeline processes them, **Then** each PDF file is downloaded and processed one at a time to prevent resource exhaustion.
2. **Given** a downloaded PDF file, **When** the document parser executes, **Then** the output is structured Markdown retaining the document's hierarchical headings and structural flow.
3. **Given** a generated Markdown file, **When** processing completes for that document, **Then** the Markdown content is saved to object storage and the storage path is saved in the document's database record.

---

### User Story 3 - Hierarchical Markdown Chunking with Contextual Metadata (Priority: P1)

The pipeline segments the converted Markdown content hierarchically. It first partitions content by Markdown headers (Header 1 `#`, Header 2 `##`, and Header 3 `###`), treating headers as hard partitioning boundaries. Any section exceeding 1,000 characters is further divided into sequential chunks of at most 1,000 characters with a 100-character overlap applied strictly within that header section (never crossing header boundaries). Each chunk is assigned a unique chunk ID, its parent document ID, a 0-based sequential chunk index, and the total number of chunks for that document. Every chunk retains applicable contextual metadata (source file name, active Header 1, Header 2, Header 3 hierarchy, and source document reference).

**Why this priority**: High-quality search retrieval and RAG depend directly on chunk granularity and structural context. Retaining heading hierarchy and file name in every chunk ensures semantic meaning and provenance are preserved even when chunks are retrieved independently.

**Independent Test**: Process a Markdown document containing varying heading depths and long text blocks. Inspect the resulting chunk records to confirm: (1) no chunk exceeds 1,000 characters, (2) overlapping boundaries share 100 characters strictly within the same header section, (3) chunks from different headers do not overlap across boundaries, (4) each chunk contains the correct sequential index and total chunk count, and (5) applicable header metadata (H1, H2, H3) and source file name are present.

**Acceptance Scenarios**:

1. **Given** a converted Markdown document, **When** the chunker processes the content, **Then** content is first partitioned along Header 1, Header 2, and Header 3 boundaries as hard division points.
2. **Given** a section under a header that exceeds 1,000 characters, **When** sub-chunking is applied, **Then** each chunk is capped at 1,000 characters with a 100-character overlap with the previous chunk in that section, without pulling content from preceding or subsequent header sections.
3. **Given** generated chunks for a document, **When** chunk metadata is populated, **Then** every chunk contains a unique chunk ID, parent document ID, source file name, sequential chunk index, total chunk count, and the active H1, H2, and H3 headers under which it is nested.

---

### User Story 4 - Vector Embedding Generation and Vector Store Synchronization (Priority: P1)

The pipeline converts each chunk's textual content into vector embeddings (batching requests up to 50 chunks per API call) and persists the embeddings along with chunk metadata in a vector database. When a document is categorized as `updated`, existing chunk embeddings for that document are purged before new ones are inserted. When a document is categorized as `deleted`, all existing chunk embeddings for that document are removed from the vector database, and the document is marked as removed from the knowledge base.

**Why this priority**: Enables semantic search and information retrieval over the ingested knowledge base, while ensuring the vector store reflects the current state of documents without orphan or stale embeddings.

**Independent Test**: Ingest a new PDF and confirm all chunk embeddings appear in the vector database with metadata. Update the source PDF and re-run execution; verify old chunk vectors are purged and new chunk vectors are indexed. Delete the source PDF and re-run execution; verify all chunk vectors for that document are completely removed from the vector database.

**Acceptance Scenarios**:

1. **Given** chunks generated from a `created` document, **When** the embedding stage runs, **Then** embeddings are computed for each chunk in batches of up to 50 chunks and stored in the vector database alongside chunk text and metadata.
2. **Given** an `updated` document with existing vector embeddings, **When** re-indexing occurs, **Then** all previous chunk vectors for that document ID are deleted from the vector store before the new chunk embeddings under the same document ID are stored.
3. **Given** a `deleted` document, **When** the pipeline handles deletion, **Then** all chunk vectors associated with the document ID are deleted from the vector database and the document record is marked as deleted.

---

### User Story 5 - End-to-End Execution Traceability and Structured Observability (Priority: P2)

Every phase of the ingestion pipeline logs structured events correlated with operational context: execution ID, document ID, chunk ID, storage path, action status, and timing. If an individual file fails during download, parsing, chunking, or embedding, the pipeline logs the failure with full context, records the document's failed state in the database, and continues processing remaining documents without crashing the overall execution.

**Why this priority**: Ensures operators have complete visibility into long-running pipeline runs, auditability of document lifecycle transitions, and resilient execution where single bad files do not abort entire batches.

**Independent Test**: Trigger an execution on a directory containing both valid PDFs and an invalid/corrupted PDF file. Verify that the execution completes, structured logs capture all events with execution ID, document ID, and chunk ID, the corrupted file is recorded as failed with descriptive error information, and valid files are successfully processed into the knowledge base.

**Acceptance Scenarios**:

1. **Given** an active pipeline execution, **When** log events are emitted at each stage, **Then** every log record includes structured contextual metadata (execution ID, document ID, chunk ID, and storage path where applicable) with clear human-readable messages.
2. **Given** a corrupted, unparseable, or scanned image-only PDF file lacking extractable text in the target directory, **When** the parser processes the file, **Then** the failure is logged with error context, the document record status is updated to `failed` with a descriptive message, and the pipeline proceeds to the next file.
3. **Given** an execution run finishes, **When** the final summary is recorded, **Then** the execution record reflects overall status, counts of created, updated, deleted, unchanged, and failed documents, and start/finish timestamps.
4. **Given** `reset_on_start` is enabled, **When** the ingestion execution begins, **Then** all existing records in the document database and all existing vectors in the vector database are completely cleared before file discovery initiates.

---

### Edge Cases

- **Empty Directory**: When a target directory path contains no files, the execution completes successfully with an execution record noting zero discovered files and zero actions taken.
- **Directory with No PDF Files or Non-PDF Files**: When a directory contains non-PDF files (e.g., images, text files, spreadsheets), the pipeline ignores all non-PDF files without recording them as knowledge documents. File extension matching is case-insensitive (e.g., `.PDF` and `.pdf` are both processed).
- **Corrupted or Password-Protected PDF**: When a PDF file cannot be opened or parsed due to corruption, invalid format, or password encryption, the pipeline catches the error, updates the document status to `failed` with the error message, logs the event with document context, and continues processing subsequent files.
- **Scanned or Image-Only PDF**: When a PDF contains no extractable text layers (e.g., scanned images without OCR), the pipeline logs an error indicating no extractable text was found, marks the document status as `failed` with a descriptive error message, and proceeds to the next document.
- **PDF with Missing or Flat Heading Structure**: When a PDF has no identifiable headings, the entire text is chunked using the character threshold (1,000 characters with 100-character overlap) with heading metadata recorded as empty/null.
- **Deeply Nested Heading Hierarchy**: When documents contain headings beyond Header 3 (e.g., Header 4 or Header 5), chunking splits down to Header 3 and preserves lower heading text within chunk content.
- **Exact Overlap Boundary Edge Case**: When a section is between 1,000 and 1,100 characters, the second chunk captures the trailing content with the required 100-character overlap from the first chunk.
- **Abrupt Execution Interruption**: If the pipeline process is stopped mid-execution, re-running the pipeline on the same directory recovers idempotently by evaluating the storage last modified timestamps against the database records.
- **Entire Directory Removed**: If an entire directory path previously ingested is deleted from object storage, all previously recorded documents under that path are detected as missing, categorized as `deleted`, and their corresponding vectors purged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Pipeline MUST accept an object storage directory path (prefix) with an optional bucket name parameter (defaulting to the configured default bucket `knowledge-source`) or a storage URI, and recursively discover all files within that target location.
- **FR-002**: Pipeline MUST evaluate the file type of each discovered file using case-insensitive extension matching and process only PDF files (e.g., `.pdf`, `.PDF`, `.Pdf`), ignoring all non-PDF files without creating document records.
- **FR-003**: Pipeline MUST track each pipeline execution with a unique execution ID, target directory path, execution start timestamp, completion timestamp, execution status, and document summary metrics.
- **FR-004**: Pipeline MUST record all discovered PDF files in a document database (MongoDB) including storage path, last modified timestamp, unique document ID, and execution reference.
- **FR-005**: Pipeline MUST determine the lifecycle action status of each discovered PDF by comparing its storage state with existing database records:
  - `created`: newly discovered file path not previously recorded in the database (assigned a new unique document ID).
  - `updated`: file path exists in database, but the storage last modified timestamp is newer than the recorded timestamp (retains the existing unique document ID and updates timestamp, content artifacts, chunks, and embeddings).
  - `deleted`: file path was previously recorded under the target directory path but is no longer found during the storage scan.
  - `unchanged`: file path exists in database and its storage last modified timestamp matches the recorded timestamp.
- **FR-006**: Pipeline MUST route documents based on action status:
  - `created`: add to knowledge base (download, parse, convert, chunk, embed, index).
  - `updated`: update knowledge base (download, parse, convert, chunk, re-embed, replace existing vectors).
  - `deleted`: remove from knowledge base (purge existing vectors, update record status).
  - `unchanged`: skip processing.
- **FR-007**: Pipeline MUST process documents sequentially ("one at a time"), downloading and processing each PDF individually before proceeding to the next.
- **FR-008**: Pipeline MUST parse downloaded PDF files and convert their content into structured Markdown to preserve hierarchical headings and document formatting.
- **FR-009**: Pipeline MUST persist the generated Markdown representation in object storage under the target bucket's `processed/markdown/{document_id}.md` key pattern and save this storage path in the document database record.
- **FR-010**: Pipeline MUST divide Markdown content into semantic chunks:
  - First partitioning hierarchically along Markdown headers: Header 1 (`#`), Header 2 (`##`), and Header 3 (`###`), treating headers as hard partitioning boundaries.
  - Then partitioning any section exceeding 1,000 characters into sequential sub-chunks of at most 1,000 characters, with a 100-character overlap applied strictly within that subdivided section (never spanning across header boundaries).
- **FR-011**: Pipeline MUST assign each generated chunk:
  - A unique chunk ID.
  - The parent document ID.
  - A 0-based sequential chunk index.
  - The total number of chunks generated for that document (`total_chunks`).
- **FR-012**: Pipeline MUST attach contextual metadata to each chunk, including source file name, active hierarchical header context (Header 1, Header 2, Header 3 values where applicable), source storage path, and document ID.
- **FR-013**: Pipeline MUST generate vector embeddings for each chunk's textual content, batching embedding API requests up to 50 chunks per call with automatic sub-batching for larger documents. The pipeline MUST handle transient API errors or rate-limit responses (HTTP 429) using exponential backoff (initial delay 1.0s, exponential multiplier 2.0x, maximum 3 retry attempts) before marking a document as failed.
- **FR-014**: Pipeline MUST ensure vector store synchronization:
  - For `updated` documents, all previously stored vectors associated with the document ID MUST be purged prior to inserting new vectors.
  - For `deleted` documents, all vectors associated with the document ID MUST be purged from the vector database.
- **FR-015**: Pipeline MUST emit structured contextual log events at all processing stages (execution lifecycle, discovery, classification, download, parsing, Markdown storage, chunking, embedding, vector store operations, deletions, and errors).
- **FR-016**: Every log event MUST include relevant contextual identifiers (execution ID, document ID, chunk ID, storage path) alongside clear descriptive human-readable messages.
- **FR-017**: Pipeline MUST isolate document-level failures, logging the failure with error details, marking the document's status as `failed` in the database, and continuing processing for remaining documents in the execution.
- **FR-018**: Pipeline MUST support an optional `reset_on_start` flag (configurable via environment variable `INGESTION_RESET_ON_START` or execution trigger parameter). When enabled, the pipeline MUST purge and recreate the vector database collection before scanning files, ensuring a completely clean slate for fresh ingestion.
- **FR-019**: When `reset_on_start` is enabled, the pipeline MUST clear all existing records in the document database (`executions` and `documents` collections) prior to initiating discovery, logging the purge action with execution audit details.

### Key Entities *(include if feature involves data)*

- **Execution**: Represents a single execution run of the ingestion pipeline. Attributes:
  - Execution ID (unique identifier)
  - Bucket Name (target object storage bucket, defaulting to `knowledge-source`)
  - Target Directory Path (storage prefix scanned)
  - Status (`pending`, `in_progress`, `completed`, `completed_with_errors`, `failed`)
  - Started Timestamp
  - Completed Timestamp
  - Counts: Discovered Count, Created Count, Updated Count, Deleted Count, Unchanged Count, Failed Count
- **Document Record**: Represents a tracked PDF document in the system. Attributes:
  - Document ID (unique identifier, stable across updates for a given storage path)
  - Current Execution ID
  - Storage Path (object storage key)
  - Last Modified Timestamp (from storage)
  - Action Status (`created`, `updated`, `deleted`, `unchanged`)
  - Processing Status (`discovered`, `downloaded`, `parsed`, `chunked`, `indexed`, `failed`)
  - Markdown Storage Path (object storage key of generated markdown)
  - Error Message (null unless processing failed)
  - Created Timestamp
  - Updated Timestamp
- **Document Chunk**: Represents a segmented slice of document text. Attributes:
  - Chunk ID (unique identifier)
  - Document ID (reference to parent document)
  - Source File Name (original PDF filename)
  - Chunk Index (0 to `total_chunks` - 1)
  - Total Chunks (total chunk count for the document)
  - Chunk Text (content string, max 1,000 characters)
  - Character Length
  - Header 1 Context (text of active H1 heading or null)
  - Header 2 Context (text of active H2 heading or null)
  - Header 3 Context (text of active H3 heading or null)
  - Metadata (combined structured dictionary)
- **Vector Record**: Represents an indexed vector entry in the vector store. Attributes:
  - Vector ID (chunk ID)
  - Document ID
  - Embedding Vector (dense numeric vector)
  - Chunk Text
  - Metadata Attributes (source file name, headers, chunk index, total chunks, storage path)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of PDF files located under the target directory path (including nested subdirectories) are discovered and correctly categorized (`created`, `updated`, `deleted`, `unchanged`) during every execution run.
- **SC-002**: 100% of non-PDF files discovered in the target path are ignored with zero document records created and zero errors generated.
- **SC-003**: 100% of successfully processed PDFs have a corresponding structured Markdown file stored in object storage with its storage path saved in the database record.
- **SC-004**: 100% of generated chunks conform to the maximum 1,000 character length limit with 100-character overlap between adjacent sub-chunks.
- **SC-005**: 100% of chunks maintain an accurate 0-based sequential chunk index and correct total chunk count reflecting the total chunks in that document.
- **SC-006**: 100% of active chunks for `created` and `updated` documents are successfully embedded and stored in the vector database with source file name and hierarchical header metadata.
- **SC-007**: 100% of obsolete chunk vectors are purged from the vector database when a document is updated or deleted, leaving zero orphaned or stale vector records.
- **SC-008**: 100% of pipeline events and error conditions emit structured log records containing execution ID, document ID, and relevant contextual attributes without uncontextualized logging.
- **SC-009**: Processing failure on an invalid or corrupted PDF is isolated with 100% containment, allowing remaining valid documents in the execution to process to completion.

## Assumptions

- The target directory path provided to the pipeline is a path or prefix within the configured object storage bucket (defaulting to `knowledge-source`), with optional override for custom bucket names or storage URIs.
- Documents are processed sequentially ("one at a time") to optimize memory usage and stability in the local development environment.
- When Markdown content contains introductory text prior to any heading, the Header 1, Header 2, and Header 3 metadata fields for those initial chunks are set to null/empty.
- Headers (H1, H2, H3) act as strict semantic boundaries: chunk overlaps never cross across different header sections, ensuring that metadata headers remain clean and non-conflicting for each chunk.
- If a document has headings deeper than Header 3 (such as H4 or H5), the chunker preserves them as text within the parent H3 chunk rather than creating separate partitions for them.
- Deleting a document from the knowledge base purges its vector embeddings and marks the database document record as `deleted` while preserving historical execution tracking.
- Object storage, document database (MongoDB), and vector storage services are accessible and running when the pipeline execution is triggered.
- OCR processing is out of scope for the current pipeline; documents are assumed to be digital PDFs with native text layers. Scanned or image-only PDFs containing no extractable text will be marked as failed.
