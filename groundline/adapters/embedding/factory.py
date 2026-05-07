from __future__ import annotations

from groundline.adapters.embedding.base import Embedder
from groundline.adapters.embedding.deterministic import HashingEmbedder
from groundline.adapters.embedding.http_api import HTTPEmbeddingProvider
from groundline.adapters.embedding.sentence_transformers import SentenceTransformersEmbedder
from groundline.core.errors import ProviderConfigurationError
from groundline.core.provider_config import EmbeddingProviderConfig


def build_embedder(config: EmbeddingProviderConfig) -> Embedder | None:
    provider = config.provider.lower()
    if provider in {"none", "disabled"}:
        return None
    if provider in {"hash", "hashing", "deterministic"}:
        return HashingEmbedder(dimension=config.dimension or 384)
    if provider in {"http", "api", "openai_compatible", "openai-compatible"}:
        return HTTPEmbeddingProvider(config)
    if provider in {"sentence_transformers", "sentence-transformers"}:
        return SentenceTransformersEmbedder(model_name=config.model)
    raise ProviderConfigurationError(f"Unsupported embedding provider: {config.provider}")
