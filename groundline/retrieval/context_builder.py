from __future__ import annotations

from groundline.core.schemas import Chunk, Citation, GroundedContext


def chunk_to_context(chunk: Chunk, source_uri: str | None = None) -> GroundedContext:
    return GroundedContext(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        version_id=chunk.version_id,
        title=chunk.title,
        section=" > ".join(chunk.heading_path) if chunk.heading_path else None,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        content_markdown=chunk.content_markdown,
        source_uri=source_uri,
        citation=Citation(
            doc_id=chunk.doc_id,
            version_id=chunk.version_id,
            chunk_id=chunk.chunk_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        ),
        metadata=dict(chunk.metadata),
    )
