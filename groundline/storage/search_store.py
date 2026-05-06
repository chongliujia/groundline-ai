from __future__ import annotations

from typing import Protocol

from groundline.core.schemas import Chunk, RetrievalHit


class SearchStore(Protocol):
    def index(self, collection: str, chunks: list[Chunk]) -> None:
        ...

    def search(self, collection: str, query: str, top_k: int) -> list[RetrievalHit]:
        ...

