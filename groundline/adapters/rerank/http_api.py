from __future__ import annotations

from groundline.adapters.http_json import post_json, provider_endpoint, provider_headers
from groundline.adapters.rerank.base import Reranker
from groundline.core.errors import BackendUnavailableError
from groundline.core.provider_config import APIProviderConfig
from groundline.core.schemas import Chunk


class HTTPRerankProvider(Reranker):
    """HTTP rerank adapter using common Cohere/Jina-style response shapes."""

    def __init__(self, config: APIProviderConfig) -> None:
        self.config = config
        self.url = provider_endpoint(config, default_path="/rerank")
        self.headers = provider_headers(config)

    def rerank(self, query: str, candidates: list[Chunk]) -> list[tuple[Chunk, float]]:
        if not candidates:
            return []
        payload = {
            "model": self.config.model,
            "query": query,
            "documents": [chunk.content_text for chunk in candidates],
        }
        decoded = post_json(
            url=self.url,
            payload=payload,
            headers=self.headers,
            timeout_seconds=self.config.timeout_seconds,
        )
        results = decoded.get("results")
        if not isinstance(results, list):
            raise BackendUnavailableError("Rerank response missing results list")

        scored: list[tuple[Chunk, float]] = []
        for item in results:
            if not isinstance(item, dict):
                raise BackendUnavailableError("Rerank result item must be an object")
            index = item.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(candidates):
                raise BackendUnavailableError("Rerank result item has invalid index")
            score = item.get("score", item.get("relevance_score"))
            if not isinstance(score, int | float):
                raise BackendUnavailableError("Rerank result item missing score")
            scored.append((candidates[index], float(score)))

        if not scored:
            return [(chunk, 0.0) for chunk in candidates]
        seen = {chunk.chunk_id for chunk, _ in scored}
        scored.extend((chunk, 0.0) for chunk in candidates if chunk.chunk_id not in seen)
        return sorted(scored, key=lambda item: item[1], reverse=True)
