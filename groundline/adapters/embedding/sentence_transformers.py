from __future__ import annotations


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        return [vector.tolist() for vector in model.encode(texts)]

