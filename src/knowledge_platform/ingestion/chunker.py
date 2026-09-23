"""Hierarchical Markdown chunker with header boundary enforcement and bounded overlap."""

import re
from uuid import uuid4

from loguru import logger

from knowledge_platform.ingestion.models import DocumentChunk


class HierarchicalMarkdownChunker:
    """
    Partitions Markdown documents hierarchically:
    1. First along Header 1 (#), Header 2 (##), Header 3 (###) boundaries as hard partitions.
    2. Then sub-chunks sections exceeding 1,000 characters using a 100-character overlap
       applied strictly within that header section.
    3. Enriches each chunk with sequential index, total count, file name, and heading context.
    """

    def __init__(
        self,
        max_chunk_size: int = 1000,
        chunk_overlap: int = 100,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.step_size = max_chunk_size - chunk_overlap
        # Regex to detect H1, H2, H3 headers at start of line
        self._h1_pattern = re.compile(r"^#\s+(.+)$")
        self._h2_pattern = re.compile(r"^##\s+(.+)$")
        self._h3_pattern = re.compile(r"^###\s+(.+)$")

    def chunk_document(
        self,
        markdown_text: str,
        document_id: str,
        source_file_name: str,
        storage_path: str,
    ) -> list[DocumentChunk]:
        """
        Split markdown text into hierarchical DocumentChunks.
        """
        if not markdown_text or not markdown_text.strip():
            return []

        lines = markdown_text.splitlines(keepends=True)

        current_h1: str | None = None
        current_h2: str | None = None
        current_h3: str | None = None

        sections: list[tuple[str | None, str | None, str | None, str]] = []
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            h1_match = self._h1_pattern.match(stripped)
            h2_match = self._h2_pattern.match(stripped)
            h3_match = self._h3_pattern.match(stripped)

            if h1_match or h2_match or h3_match:
                # Flush previous section if it has content
                if current_lines:
                    section_text = "".join(current_lines).strip()
                    if section_text:
                        sections.append(
                            (current_h1, current_h2, current_h3, section_text)
                        )
                    current_lines = []

                # Update heading stack
                if h1_match:
                    current_h1 = h1_match.group(1).strip()
                    current_h2 = None
                    current_h3 = None
                elif h2_match:
                    current_h2 = h2_match.group(1).strip()
                    current_h3 = None
                elif h3_match:
                    current_h3 = h3_match.group(1).strip()

            current_lines.append(line)

        # Flush final section
        if current_lines:
            section_text = "".join(current_lines).strip()
            if section_text:
                sections.append((current_h1, current_h2, current_h3, section_text))

        if not sections:
            return []

        # Sub-chunk sections exceeding max_chunk_size with overlap bounded within section
        raw_chunks: list[tuple[str | None, str | None, str | None, str]] = []

        for h1, h2, h3, text in sections:
            if len(text) <= self.max_chunk_size:
                raw_chunks.append((h1, h2, h3, text))
            else:
                for start in range(0, len(text), self.step_size):
                    chunk_slice = text[start : start + self.max_chunk_size]
                    raw_chunks.append((h1, h2, h3, chunk_slice))
                    if start + self.max_chunk_size >= len(text):
                        break

        total_chunks = len(raw_chunks)
        chunks: list[DocumentChunk] = []

        for idx, (h1, h2, h3, chunk_text) in enumerate(raw_chunks):
            chunk_id = str(uuid4())
            metadata = {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "source_file_name": source_file_name,
                "storage_path": storage_path,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "h1": h1,
                "h2": h2,
                "h3": h3,
            }

            chunk = DocumentChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                source_file_name=source_file_name,
                storage_path=storage_path,
                chunk_index=idx,
                total_chunks=total_chunks,
                text=chunk_text,
                char_length=len(chunk_text),
                h1=h1,
                h2=h2,
                h3=h3,
                metadata=metadata,
            )
            chunks.append(chunk)

        logger.bind(document_id=document_id).debug(
            "Chunked document into {count} chunks (max_length={max_l})",
            count=total_chunks,
            max_l=max(c.char_length for c in chunks) if chunks else 0,
        )

        return chunks
