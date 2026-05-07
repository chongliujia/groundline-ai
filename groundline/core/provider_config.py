from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class APIProviderConfig(BaseModel):
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    endpoint_path: str = ""
    api_key_env: str = ""
    timeout_seconds: int = 60

    @property
    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.getenv(self.api_key_env)


class EmbeddingProviderConfig(APIProviderConfig):
    provider: str = "none"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    api_key_env: str = "GROUNDLINE_EMBEDDING_API_KEY"
    dimension: int | None = 384


class ProviderConfig(BaseModel):
    llm: APIProviderConfig = Field(default_factory=APIProviderConfig)
    embedding: EmbeddingProviderConfig = Field(default_factory=EmbeddingProviderConfig)
    rerank: APIProviderConfig = Field(default_factory=APIProviderConfig)


def load_provider_config(path: Path) -> ProviderConfig:
    if not path.exists():
        return ProviderConfig()
    with path.open("rb") as file:
        data = tomllib.load(file)
    return ProviderConfig.model_validate(data)
