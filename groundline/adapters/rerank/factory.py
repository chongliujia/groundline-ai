from __future__ import annotations

from groundline.adapters.rerank.base import Reranker
from groundline.adapters.rerank.cross_encoder import CrossEncoderReranker
from groundline.adapters.rerank.keyword import KeywordOverlapReranker
from groundline.core.errors import ProviderConfigurationError
from groundline.core.provider_config import APIProviderConfig


def build_reranker(config: APIProviderConfig) -> Reranker | None:
    provider = config.provider.lower()
    if provider in {"none", "disabled"}:
        return None
    if provider in {"keyword", "overlap"}:
        return KeywordOverlapReranker()
    if provider in {"cross_encoder", "cross-encoder", "sentence_transformers"}:
        return CrossEncoderReranker(model_name=config.model)
    raise ProviderConfigurationError(f"Unsupported rerank provider: {config.provider}")

