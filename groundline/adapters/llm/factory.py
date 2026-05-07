from __future__ import annotations

from groundline.adapters.llm.base import LLMClient
from groundline.adapters.llm.http_api import HTTPLLMProvider
from groundline.core.errors import ProviderConfigurationError
from groundline.core.provider_config import APIProviderConfig


def build_llm(config: APIProviderConfig) -> LLMClient | None:
    provider = config.provider.lower()
    if provider in {"none", "disabled"}:
        return None
    if provider in {"http", "api", "openai_compatible", "openai-compatible"}:
        return HTTPLLMProvider(config)
    raise ProviderConfigurationError(f"Unsupported LLM provider: {config.provider}")
