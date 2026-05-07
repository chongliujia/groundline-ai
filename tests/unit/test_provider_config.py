from pathlib import Path

from groundline.core.provider_config import load_provider_config


def test_provider_config_loads_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "groundline.toml"
    config_path.write_text(
        """
        [llm]
        provider = "openai_compatible"
        model = "chat-model"
        api_key_env = "GROUNDLINE_LLM_API_KEY"

        [embedding]
        provider = "openai_compatible"
        model = "embedding-model"
        endpoint_path = "/v1/embeddings"
        dimension = 1536

        [rerank]
        provider = "api"
        model = "rerank-model"
        """,
        encoding="utf-8",
    )

    config = load_provider_config(config_path)

    assert config.llm.model == "chat-model"
    assert config.embedding.endpoint_path == "/v1/embeddings"
    assert config.embedding.dimension == 1536
    assert config.rerank.provider == "api"


def test_provider_config_defaults_when_missing(tmp_path: Path) -> None:
    config = load_provider_config(tmp_path / "missing.toml")

    assert config.embedding.provider == "none"
    assert config.rerank.provider == "none"
