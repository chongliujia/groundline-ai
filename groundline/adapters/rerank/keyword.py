from __future__ import annotations

from groundline.core.schemas import Chunk
from groundline.retrieval.tokenize import tokenize


class KeywordOverlapReranker:
    """Dependency-free reranker for local tests and demos."""

    def rerank(self, query: str, candidates: list[Chunk]) -> list[tuple[Chunk, float]]:
        query_tokens = set(tokenize(query))
        scored: list[tuple[Chunk, float]] = []
        for chunk in candidates:
            chunk_tokens = set(tokenize(chunk.content_text))
            score = len(query_tokens & chunk_tokens) / max(len(query_tokens), 1)
            scored.append((chunk, float(score)))
        return sorted(scored, key=lambda item: item[1], reverse=True)

