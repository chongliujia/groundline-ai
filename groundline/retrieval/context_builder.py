from __future__ import annotations

from groundline.core.schemas import Chunk, Citation, GroundedContext


def chunk_to_context(
    chunk: Chunk,
    source_uri: str | None = None,
    packed_chunks: list[Chunk] | None = None,
) -> GroundedContext:
    selected_chunks = packed_chunks or [chunk]
    page_starts = [selected.page_start for selected in selected_chunks if selected.page_start]
    page_ends = [selected.page_end for selected in selected_chunks if selected.page_end]
    return GroundedContext(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        version_id=chunk.version_id,
        title=chunk.title,
        section=" > ".join(chunk.heading_path) if chunk.heading_path else None,
        page_start=min(page_starts) if page_starts else chunk.page_start,
        page_end=max(page_ends) if page_ends else chunk.page_end,
        content_markdown=_join_chunk_markdown(selected_chunks),
        source_uri=source_uri,
        citation=Citation(
            doc_id=chunk.doc_id,
            version_id=chunk.version_id,
            chunk_id=chunk.chunk_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        ),
        metadata={
            **chunk.metadata,
            "anchor_chunk_id": chunk.chunk_id,
            "packed_chunk_ids": [selected.chunk_id for selected in selected_chunks],
        },
    )


def pack_adjacent_chunks(
    anchor: Chunk,
    chunk_by_id: dict[str, Chunk],
    context_window: int,
    max_chars: int,
) -> list[Chunk]:
    if context_window <= 0:
        return [anchor]

    previous, following = _adjacent_chunks(anchor, chunk_by_id, context_window)
    packed = [anchor]
    used_chars = len(anchor.content_markdown)

    for chunk in reversed(previous):
        chunk_chars = len(chunk.content_markdown) + 2
        if max_chars > 0 and used_chars + chunk_chars > max_chars:
            continue
        packed.insert(0, chunk)
        used_chars += chunk_chars

    for chunk in following:
        chunk_chars = len(chunk.content_markdown) + 2
        if max_chars > 0 and used_chars + chunk_chars > max_chars:
            continue
        packed.append(chunk)
        used_chars += chunk_chars

    return packed


def _adjacent_chunks(
    anchor: Chunk,
    chunk_by_id: dict[str, Chunk],
    context_window: int,
) -> tuple[list[Chunk], list[Chunk]]:
    previous: list[Chunk] = []
    current = anchor
    for _ in range(context_window):
        if not current.prev_chunk_id:
            break
        previous_chunk = chunk_by_id.get(current.prev_chunk_id)
        if previous_chunk is None:
            break
        previous.append(previous_chunk)
        current = previous_chunk

    following: list[Chunk] = []
    current = anchor
    for _ in range(context_window):
        if not current.next_chunk_id:
            break
        next_chunk = chunk_by_id.get(current.next_chunk_id)
        if next_chunk is None:
            break
        following.append(next_chunk)
        current = next_chunk

    return previous, following


def _join_chunk_markdown(chunks: list[Chunk]) -> str:
    return "\n\n".join(chunk.content_markdown.strip() for chunk in chunks).strip()
