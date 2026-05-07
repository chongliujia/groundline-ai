import json
from urllib.error import URLError

import pytest

from groundline.adapters import http_json
from groundline.adapters.embedding.factory import build_embedder
from groundline.adapters.llm.factory import build_llm
from groundline.adapters.rerank.factory import build_reranker
from groundline.core.errors import BackendUnavailableError, ProviderConfigurationError
from groundline.core.provider_config import APIProviderConfig, EmbeddingProviderConfig
from groundline.core.schemas import Chunk


def make_chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc_1",
        version_id="v1",
        tenant_id="default",
        content_markdown=text,
        content_text=text,
        text_for_embedding=text,
        content_hash=chunk_id,
    )


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_http_embedding_provider_posts_openai_compatible_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }
        )

    monkeypatch.setenv("EMBED_KEY", "secret")
    monkeypatch.setattr(http_json, "urlopen", fake_urlopen)
    embedder = build_embedder(
        EmbeddingProviderConfig(
            provider="http",
            model="embedding-model",
            base_url="https://provider.example/v1",
            endpoint_path="/embeddings",
            api_key_env="EMBED_KEY",
            timeout_seconds=7,
        )
    )

    assert embedder is not None
    assert embedder.embed(["alpha", "beta"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "https://provider.example/v1/embeddings"
    assert captured["timeout"] == 7
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["payload"] == {
        "model": "embedding-model",
        "input": ["alpha", "beta"],
    }


def test_http_rerank_provider_orders_by_api_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["query"] == "住宿标准"
        assert payload["documents"] == ["alpha", "beta"]
        return FakeResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ]
            }
        )

    monkeypatch.setattr(http_json, "urlopen", fake_urlopen)
    reranker = build_reranker(
        APIProviderConfig(
            provider="api",
            model="rerank-model",
            base_url="https://provider.example",
            api_key_env="",
        )
    )

    assert reranker is not None
    ranked = reranker.rerank(
        "住宿标准",
        [
            make_chunk("chunk_1", "alpha"),
            make_chunk("chunk_2", "beta"),
        ],
    )

    assert ranked[0][0].chunk_id == "chunk_2"
    assert ranked[0][1] == 0.9
    assert ranked[1][0].chunk_id == "chunk_1"


def test_http_llm_provider_reads_chat_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "grounded answer"}}]})

    monkeypatch.setattr(http_json, "urlopen", fake_urlopen)
    llm = build_llm(
        APIProviderConfig(
            provider="openai_compatible",
            model="chat-model",
            base_url="https://provider.example/v1",
            api_key_env="",
        )
    )

    assert llm is not None
    assert llm.generate([{"role": "user", "content": "hello"}]) == "grounded answer"
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["payload"] == {
        "model": "chat-model",
        "messages": [{"role": "user", "content": "hello"}],
    }


def test_http_provider_requires_configured_api_key_env() -> None:
    with pytest.raises(ProviderConfigurationError):
        build_embedder(
            EmbeddingProviderConfig(
                provider="http",
                base_url="https://provider.example/v1",
                api_key_env="MISSING_EMBED_KEY",
            )
        )


def test_http_provider_wraps_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("offline")

    monkeypatch.setattr(http_json, "urlopen", fake_urlopen)
    embedder = build_embedder(
        EmbeddingProviderConfig(
            provider="http",
            base_url="https://provider.example/v1",
            api_key_env="",
        )
    )

    assert embedder is not None
    with pytest.raises(BackendUnavailableError):
        embedder.embed(["alpha"])
