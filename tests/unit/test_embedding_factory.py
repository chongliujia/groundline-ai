from groundline.adapters.embedding.factory import build_embedder
from groundline.core.provider_config import EmbeddingProviderConfig


def test_embedding_factory_returns_none_when_disabled() -> None:
    assert build_embedder(EmbeddingProviderConfig(provider="none")) is None


def test_hashing_embedder_is_deterministic() -> None:
    embedder = build_embedder(EmbeddingProviderConfig(provider="hash", dimension=8))

    assert embedder is not None
    assert embedder.embed(["alpha beta"]) == embedder.embed(["alpha beta"])
    assert len(embedder.embed(["alpha beta"])[0]) == 8

