"""Integration tests for vector embedding generation and Qdrant store synchronization."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from knowledge_platform.config import IngestionSettings
from knowledge_platform.ingestion.chunker import HierarchicalMarkdownChunker
from knowledge_platform.ingestion.embeddings import VertexAIEmbeddingClient
from knowledge_platform.ingestion.models import VectorPayload
from knowledge_platform.ingestion.vector_store import QdrantVectorStore


@pytest.fixture
def settings() -> IngestionSettings:
    return IngestionSettings()


@pytest.fixture
async def qdrant_store(
    settings: IngestionSettings,
) -> AsyncGenerator[QdrantVectorStore, None]:
    client = AsyncQdrantClient(url=settings.qdrant_url, check_compatibility=False)
    test_collection = f"test_chunks_{uuid4().hex[:8]}"
    store = QdrantVectorStore(
        client=client,
        collection_name=test_collection,
        vector_size=768,
    )
    await store.ensure_collection_exists()
    try:
        yield store
    finally:
        try:
            await client.delete_collection(test_collection)
        except Exception:  # noqa: BLE001, S110
            pass
        await client.close()


@pytest.fixture
def embedding_client(settings: IngestionSettings) -> VertexAIEmbeddingClient:
    return VertexAIEmbeddingClient(
        api_key=settings.vertex_api_key,
        model_name=settings.vertex_embedding_model,
        batch_size=settings.vertex_batch_size,
    )


@pytest.mark.asyncio
async def test_vector_indexing_and_metadata_fidelity(
    qdrant_store: QdrantVectorStore,
    embedding_client: VertexAIEmbeddingClient,
) -> None:
    doc_id = str(uuid4())
    file_name = "quarterly_report.pdf"
    storage_path = "reports/quarterly_report.pdf"

    sample_markdown = """# Financial Highlights
Revenue grew 25% year-over-year.

## Regional Results
North America exceeded targets by 10%.

### Operating Costs
Costs were managed within strict limits.
"""
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(
        markdown_text=sample_markdown,
        document_id=doc_id,
        source_file_name=file_name,
        storage_path=storage_path,
    )
    assert len(chunks) == 3

    # Generate embeddings
    texts = [c.text for c in chunks]
    vectors = await embedding_client.embed_texts(texts, document_id=doc_id)
    assert len(vectors) == 3
    assert len(vectors[0]) == 768

    chunk_ids = [c.chunk_id for c in chunks]
    payloads = [
        VectorPayload(
            document_id=c.document_id,
            chunk_id=c.chunk_id,
            source_file_name=c.source_file_name,
            storage_path=c.storage_path,
            chunk_index=c.chunk_index,
            total_chunks=c.total_chunks,
            h1=c.h1,
            h2=c.h2,
            h3=c.h3,
            text=c.text,
        )
        for c in chunks
    ]

    # Index into Qdrant
    await qdrant_store.upsert_chunk_vectors(
        document_id=doc_id,
        chunk_ids=chunk_ids,
        vectors=vectors,
        payloads=payloads,
    )

    # Verify points in Qdrant
    points = await qdrant_store.get_points_by_document_id(doc_id)
    assert len(points) == 3

    point_map = {
        p.payload["chunk_index"]: p.payload for p in points if p.payload is not None
    }
    assert point_map[0]["h1"] == "Financial Highlights"
    assert point_map[0]["source_file_name"] == file_name
    assert point_map[0]["total_chunks"] == 3

    assert point_map[1]["h2"] == "Regional Results"
    assert point_map[2]["h3"] == "Operating Costs"


@pytest.mark.asyncio
async def test_vector_synchronization_update_and_purge(
    qdrant_store: QdrantVectorStore,
    embedding_client: VertexAIEmbeddingClient,
) -> None:
    doc_id = str(uuid4())
    file_name = "user_manual.pdf"
    storage_path = "manuals/user_manual.pdf"

    # Step 1: Initial Ingestion (2 chunks)
    md_v1 = "# Section A\nInitial version of section A.\n\n# Section B\nInitial version of section B."
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks_v1 = chunker.chunk_document(md_v1, doc_id, file_name, storage_path)
    assert len(chunks_v1) == 2

    vectors_v1 = await embedding_client.embed_texts(
        [c.text for c in chunks_v1], document_id=doc_id
    )
    payloads_v1 = [
        VectorPayload(
            document_id=c.document_id,
            chunk_id=c.chunk_id,
            source_file_name=c.source_file_name,
            storage_path=c.storage_path,
            chunk_index=c.chunk_index,
            total_chunks=c.total_chunks,
            h1=c.h1,
            h2=c.h2,
            h3=c.h3,
            text=c.text,
        )
        for c in chunks_v1
    ]
    await qdrant_store.upsert_chunk_vectors(
        doc_id, [c.chunk_id for c in chunks_v1], vectors_v1, payloads_v1
    )

    initial_count = await qdrant_store.count_vectors_by_document_id(doc_id)
    assert initial_count == 2

    # Step 2: Document Update (1 chunk now)
    # Purge old vectors before upserting new ones
    await qdrant_store.delete_vectors_by_document_id(doc_id)
    post_purge_count = await qdrant_store.count_vectors_by_document_id(doc_id)
    assert post_purge_count == 0

    md_v2 = (
        "# Consolidated Section\nAll information consolidated into one single section."
    )
    chunks_v2 = chunker.chunk_document(md_v2, doc_id, file_name, storage_path)
    assert len(chunks_v2) == 1

    vectors_v2 = await embedding_client.embed_texts(
        [c.text for c in chunks_v2], document_id=doc_id
    )
    payloads_v2 = [
        VectorPayload(
            document_id=c.document_id,
            chunk_id=c.chunk_id,
            source_file_name=c.source_file_name,
            storage_path=c.storage_path,
            chunk_index=c.chunk_index,
            total_chunks=c.total_chunks,
            h1=c.h1,
            h2=c.h2,
            h3=c.h3,
            text=c.text,
        )
        for c in chunks_v2
    ]
    await qdrant_store.upsert_chunk_vectors(
        doc_id, [c.chunk_id for c in chunks_v2], vectors_v2, payloads_v2
    )

    updated_count = await qdrant_store.count_vectors_by_document_id(doc_id)
    assert updated_count == 1, "Only 1 updated vector should exist; old vectors purged!"

    # Step 3: Document Deletion
    await qdrant_store.delete_vectors_by_document_id(doc_id)
    final_count = await qdrant_store.count_vectors_by_document_id(doc_id)
    assert final_count == 0, "All vectors purged upon document deletion!"
