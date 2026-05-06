from __future__ import annotations

from collections import defaultdict

from rank_bm25 import BM25Okapi

from groundline.core.schemas import Chunk, RetrievalHit
from groundline.retrieval.tokenize import tokenize


class InMemoryBM25Store:
    """Small local BM25 store for demos and tests."""

    def __init__(self) -> None:
        self._chunks: dict[str, list[Chunk]] = defaultdict(list)
        self._indexes: dict[str, BM25Okapi] = {}

    def index(self, collection: str, chunks: list[Chunk]) -> None:
        self._chunks[collection] = chunks
        corpus = [tokenize(chunk.content_text) for chunk in chunks]
        if not corpus:
            self._indexes.pop(collection, None)
            return
        self._indexes[collection] = BM25Okapi(corpus)

    def search(self, collection: str, query: str, top_k: int) -> list[RetrievalHit]:
        chunks = self._chunks.get(collection, [])
        index = self._indexes.get(collection)
        if index is None or not chunks:
            return []
        query_tokens = tokenize(query)
        query_token_set = set(query_tokens)
        scores = index.get_scores(query_tokens)
        ranked = sorted(
            (
                (idx, self._effective_score(float(score), query_token_set, chunks[idx]))
                for idx, score in enumerate(scores)
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        ranked = [item for item in ranked if item[1] > 0][:top_k]
        return [
            RetrievalHit(
                chunk_id=chunks[idx].chunk_id,
                score=float(score),
                source="bm25",
                rank=rank,
            )
            for rank, (idx, score) in enumerate(ranked, start=1)
        ]

    @staticmethod
    def _effective_score(score: float, query_tokens: set[str], chunk: Chunk) -> float:
        if score > 0:
            return score
        if not query_tokens:
            return 0.0
        overlap = query_tokens & set(tokenize(chunk.content_text))
        if not overlap:
            return 0.0
        return len(overlap) / len(query_tokens)
