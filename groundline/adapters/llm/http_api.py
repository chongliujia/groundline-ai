from __future__ import annotations

from groundline.adapters.http_json import post_json, provider_endpoint, provider_headers
from groundline.adapters.llm.base import LLMClient
from groundline.core.errors import BackendUnavailableError
from groundline.core.provider_config import APIProviderConfig


class HTTPLLMProvider(LLMClient):
    """OpenAI-compatible chat completions adapter."""

    def __init__(self, config: APIProviderConfig) -> None:
        self.config = config
        self.url = provider_endpoint(config, default_path="/chat/completions")
        self.headers = provider_headers(config)

    def generate(self, messages: list[dict[str, str]]) -> str:
        decoded = post_json(
            url=self.url,
            payload={"model": self.config.model, "messages": messages},
            headers=self.headers,
            timeout_seconds=self.config.timeout_seconds,
        )
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices:
            raise BackendUnavailableError("LLM response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise BackendUnavailableError("LLM choice must be an object")
        message = first.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        text = first.get("text")
        if isinstance(text, str):
            return text
        raise BackendUnavailableError("LLM response missing text content")
