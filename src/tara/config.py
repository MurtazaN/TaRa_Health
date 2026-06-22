"""Application configuration, loaded from environment / .env.

All paths and model choices are centralized here so the rest of the code never
hard-codes a provider or a directory.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TARA_", env_file=".env", extra="ignore")

    # Storage (local-first)
    data_dir: Path = Field(default=Path("./.tara_data"))
    db_key: str = Field(default="")  # SQLCipher passphrase; empty => unencrypted (dev only)

    # Model mode
    model_mode: Literal["local", "hosted", "hybrid"] = "local"

    # Local model (Ollama)
    ollama_host: str = "http://localhost:11434"
    local_model: str = "qwen3:8b"

    # Hosted model (opt-in)
    hosted_model: str = "claude-sonnet-4-6"

    # Embeddings (local)
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384

    # Retrieval
    top_k: int = 6

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tara.sqlite"

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.blob_dir.mkdir(parents=True, exist_ok=True)
    return s
