"""Unit tests for the HierarchicalMarkdownChunker."""

from knowledge_platform.ingestion.chunker import HierarchicalMarkdownChunker


def test_chunker_empty_document() -> None:
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document("", "doc-1", "test.pdf", "path/test.pdf")
    assert chunks == []

    chunks_whitespace = chunker.chunk_document(
        "   \n\n  ", "doc-1", "test.pdf", "path/test.pdf"
    )
    assert chunks_whitespace == []


def test_chunker_header_hierarchy_and_hard_boundaries() -> None:
    markdown = """# Architecture Overview
This is introductory architecture text.

## Vector Store
We use Qdrant for vector storage.

### Collection Setup
Details about vector dimensions and distance metrics.

# Deployment
Information about Docker Compose.
"""
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(
        markdown, "doc-1", "architecture.pdf", "docs/architecture.pdf"
    )

    assert len(chunks) == 4
    for idx, chunk in enumerate(chunks):
        assert chunk.chunk_index == idx
        assert chunk.total_chunks == 4
        assert chunk.document_id == "doc-1"
        assert chunk.source_file_name == "architecture.pdf"
        assert chunk.storage_path == "docs/architecture.pdf"

    # Chunk 0: Under H1 Architecture Overview
    assert chunks[0].h1 == "Architecture Overview"
    assert chunks[0].h2 is None
    assert chunks[0].h3 is None
    assert "Architecture Overview" in chunks[0].text

    # Chunk 1: Under H2 Vector Store (inherits H1)
    assert chunks[1].h1 == "Architecture Overview"
    assert chunks[1].h2 == "Vector Store"
    assert chunks[1].h3 is None
    assert "Vector Store" in chunks[1].text

    # Chunk 2: Under H3 Collection Setup (inherits H1, H2)
    assert chunks[2].h1 == "Architecture Overview"
    assert chunks[2].h2 == "Vector Store"
    assert chunks[2].h3 == "Collection Setup"
    assert "Collection Setup" in chunks[2].text

    # Chunk 3: New H1 Deployment (resets H2 and H3)
    assert chunks[3].h1 == "Deployment"
    assert chunks[3].h2 is None
    assert chunks[3].h3 is None
    assert "Deployment" in chunks[3].text


def test_chunker_section_exceeding_1000_chars_subchunking_and_overlap() -> None:
    # Construct a section with length ~1500 chars under an H1
    header = "# Long Section\n"
    # Create 1400 chars of repeating pattern
    body = "A" * 500 + "B" * 500 + "C" * 400
    markdown = header + body

    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(markdown, "doc-2", "long.pdf", "docs/long.pdf")

    assert len(chunks) == 2
    # Verify both chunks do not exceed 1,000 characters
    assert chunks[0].char_length <= 1000
    assert chunks[1].char_length <= 1000

    # Overlap verification:
    # First chunk is chars [0 : 1000]
    # Second chunk starts at 900: chars [900 : 1900]
    expected_overlap = chunks[0].text[900:1000]
    assert len(expected_overlap) == 100
    assert chunks[1].text.startswith(expected_overlap)

    # Both chunks retain the same heading hierarchy
    assert chunks[0].h1 == "Long Section"
    assert chunks[1].h1 == "Long Section"


def test_chunker_overlap_never_spans_across_header_boundaries() -> None:
    # Two short sections (<1000 chars each)
    section1 = "# Section One\n" + "X" * 300
    section2 = "# Section Two\n" + "Y" * 300
    markdown = section1 + "\n\n" + section2

    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(
        markdown, "doc-3", "headers.pdf", "docs/headers.pdf"
    )

    assert len(chunks) == 2
    # Section One must NOT contain any 'Y's
    assert "Y" not in chunks[0].text
    assert chunks[0].h1 == "Section One"

    # Section Two must NOT contain any 'X's (hard boundary: no overlap across sections)
    assert "X" not in chunks[1].text
    assert chunks[1].h1 == "Section Two"


def test_chunker_fallback_for_document_without_headings() -> None:
    body = "This is a document with no markdown headers at all. " * 30
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(body, "doc-4", "plain.pdf", "docs/plain.pdf")

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.h1 is None
        assert chunk.h2 is None
        assert chunk.h3 is None
        assert chunk.char_length <= 1000
        assert chunk.source_file_name == "plain.pdf"


def test_chunker_leading_text_before_first_heading() -> None:
    markdown = """Leading introductory remarks before any section starts.

# Chapter 1
Content of chapter 1.
"""
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(markdown, "doc-5", "intro.pdf", "docs/intro.pdf")

    assert len(chunks) == 2
    # Chunk 0 has no headings
    assert chunks[0].h1 is None
    assert "Leading introductory remarks" in chunks[0].text

    # Chunk 1 has H1
    assert chunks[1].h1 == "Chapter 1"
    assert "Content of chapter 1" in chunks[1].text


def test_chunker_deeper_headings_preserved_as_content() -> None:
    markdown = """### Subsection 3
#### Heading 4 Details
Some deep technical specification text.
##### Heading 5 Further Notes
Even deeper note text.
"""
    chunker = HierarchicalMarkdownChunker(max_chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk_document(markdown, "doc-6", "deep.pdf", "docs/deep.pdf")

    assert len(chunks) == 1
    assert chunks[0].h3 == "Subsection 3"
    # Deeper headings are preserved within the text
    assert "#### Heading 4 Details" in chunks[0].text
    assert "##### Heading 5 Further Notes" in chunks[0].text
