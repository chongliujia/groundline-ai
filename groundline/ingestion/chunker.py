from __future__ import annotations

from dataclasses import dataclass

from groundline.core.hashing import hash_text
from groundline.core.ids import new_id
from groundline.core.schemas import Block, Chunk

CHUNKER_VERSION = "heading-aware.v0.1"


@dataclass(frozen=True)
class ChunkerConfig:
    max_chars: int = 2400
    tenant_id: str = "default"
    title: str | None = None
    doc_type: str | None = None
    domain: str | None = None
    language: str | None = None
    acl_groups: tuple[str, ...] = ()
    metadata: dict[str, object] | None = None


class HeadingAwareChunker:
    def __init__(self, config: ChunkerConfig | None = None) -> None:
        self.config = config or ChunkerConfig()

    def chunk(self, blocks: list[Block], doc_id: str, version_id: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        current: list[Block] = []
        current_size = 0

        def flush() -> None:
            nonlocal current_size
            if not current:
                return
            content_markdown = "\n\n".join(
                (block.markdown or block.text or "").strip() for block in current
            ).strip()
            content_text = "\n".join((block.text or "").strip() for block in current).strip()
            pages = [block.page for block in current if block.page is not None]
            heading_path = current[-1].heading_path if current[-1].heading_path else []
            chunks.append(
                Chunk(
                    chunk_id=new_id("chunk"),
                    doc_id=doc_id,
                    version_id=version_id,
                    tenant_id=self.config.tenant_id,
                    title=self.config.title,
                    heading_path=heading_path,
                    content_markdown=content_markdown,
                    content_text=content_text,
                    text_for_embedding=" ".join([*heading_path, content_text]).strip(),
                    block_ids=[block.block_id for block in current],
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                    doc_type=self.config.doc_type,
                    domain=self.config.domain,
                    language=self.config.language,
                    acl_groups=list(self.config.acl_groups),
                    content_hash=hash_text(content_markdown),
                    metadata=dict(self.config.metadata or {}),
                )
            )
            current.clear()
            current_size = 0

        for block in blocks:
            block_text = block.markdown or block.text or ""
            should_split = current and (
                block.block_type == "heading"
                or current_size + len(block_text) > self.config.max_chars
            )
            if should_split:
                flush()
            current.append(block)
            current_size += len(block_text)
        flush()

        for index, chunk in enumerate(chunks):
            if index > 0:
                chunk.prev_chunk_id = chunks[index - 1].chunk_id
            if index + 1 < len(chunks):
                chunk.next_chunk_id = chunks[index + 1].chunk_id
        return chunks
