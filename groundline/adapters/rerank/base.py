from __future__ import annotations

from typing import Protocol

from groundline.core.schemas import Chunk


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[Chunk]) -> list[tuple[Chunk, float]]:
        ...

