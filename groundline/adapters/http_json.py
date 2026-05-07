from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from groundline.core.errors import BackendUnavailableError, ProviderConfigurationError
from groundline.core.provider_config import APIProviderConfig


def provider_endpoint(config: APIProviderConfig, default_path: str) -> str:
    if not config.base_url:
        raise ProviderConfigurationError("HTTP provider requires base_url")
    path = config.endpoint_path or default_path
    if config.base_url.rstrip("/").endswith(path):
        return config.base_url.rstrip("/")
    return f"{config.base_url.rstrip('/')}/{path.lstrip('/')}"


def provider_headers(config: APIProviderConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = config.api_key
    if config.api_key_env and not api_key:
        raise ProviderConfigurationError(
            f"HTTP provider requires API key env var {config.api_key_env}"
        )
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except URLError as error:
        raise BackendUnavailableError(f"HTTP provider request failed: {error}") from error
    except TimeoutError as error:
        raise BackendUnavailableError("HTTP provider request timed out") from error

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BackendUnavailableError(f"HTTP provider returned invalid JSON: {error}") from error
    if not isinstance(decoded, dict):
        raise BackendUnavailableError("HTTP provider response must be a JSON object")
    return decoded
