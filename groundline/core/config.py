from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from groundline.core.provider_config import ProviderConfig, load_provider_config


class Settings(BaseSettings):
    """Runtime settings shared by CLI and API server."""

    model_config = SettingsConfigDict(env_prefix="GROUNDLINE_", env_file=".env")

    data_dir: Path = Field(default=Path(".groundline"))
    default_collection: str = "demo"
    qdrant_url: str = "http://localhost:6333"
    sqlite_path: Path | None = None
    provider_config_path: Path = Path("groundline.toml")

    @property
    def resolved_sqlite_path(self) -> Path:
        return self.sqlite_path or self.data_dir / "groundline.sqlite3"

    @property
    def providers(self) -> ProviderConfig:
        return load_provider_config(self.provider_config_path)


def get_settings() -> Settings:
    return Settings()
