from __future__ import annotations

from typing import Protocol

from groundline.core.schemas import Chunk, Document, DocumentVersion


class MetadataStore(Protocol):
    def put_document(self, collection: str, document: Document) -> None:
        ...

    def put_version(self, collection: str, version: DocumentVersion) -> None:
        ...

    def put_chunks(self, collection: str, chunks: list[Chunk]) -> None:
        ...

    def list_chunks(self, collection: str) -> list[Chunk]:
        ...

    def get_document_by_source_uri(self, collection: str, source_uri: str) -> Document | None:
        ...

    def tombstone_document(self, collection: str, doc_id: str) -> int:
        ...
