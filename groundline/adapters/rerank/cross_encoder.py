from __future__ import annotations

from groundline.core.schemas import Chunk


class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, candidates: list[Chunk]) -> list[tuple[Chunk, float]]:
        model = self._load()
        pairs = [(query, chunk.content_text) for chunk in candidates]
        scores = model.predict(pairs)
        return sorted(
            zip(candidates, map(float, scores), strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
