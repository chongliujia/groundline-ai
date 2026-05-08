from __future__ import annotations

from typing import Protocol

from groundline.core.schemas import RetrievalHit


class VectorStore(Protocol):
    def upsert(self, collection: str, vectors: list[tuple[str, list[float], dict]]) -> None:
        ...

    def search(self, collection: str, vector: list[float], top_k: int) -> list[RetrievalHit]:
        ...

    def count_points(self, collection: str, doc_id: str | None = None) -> int:
        ...
