from __future__ import annotations

from groundline.adapters.embedding.base import Embedder
from groundline.adapters.http_json import post_json, provider_endpoint, provider_headers
from groundline.core.errors import BackendUnavailableError
from groundline.core.provider_config import EmbeddingProviderConfig


class HTTPEmbeddingProvider(Embedder):
    """OpenAI-compatible HTTP embedding adapter."""

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self.config = config
        self.url = provider_endpoint(config, default_path="/embeddings")
        self.headers = provider_headers(config)

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self.config.model,
            "input": texts,
        }
        decoded = post_json(
            url=self.url,
            payload=payload,
            headers=self.headers,
            timeout_seconds=self.config.timeout_seconds,
        )
        data = decoded.get("data")
        if not isinstance(data, list):
            raise BackendUnavailableError("Embedding response missing data list")
        if all(isinstance(item, dict) and isinstance(item.get("index"), int) for item in data):
            data = sorted(data, key=lambda item: item["index"])
        vectors: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise BackendUnavailableError("Embedding response item missing embedding list")
            vectors.append([float(value) for value in item["embedding"]])
        if len(vectors) != len(texts):
            raise BackendUnavailableError("Embedding response count does not match input count")
        return vectors
