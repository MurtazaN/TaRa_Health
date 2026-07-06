"""Application configuration, loaded from environment / .env.

All paths and model choices are centralized here so the rest of the code never
hard-codes a provider or a directory (design §3.5: local-vs-hosted is config,
never a code change). See PHASE_1_TECHNICAL_DESIGN.md.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 50 MB upload ceiling (§3.1a); a malformed/oversized upload fails fast.
_DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

LocalBackend = Literal["ollama", "openai_compatible"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TARA_", env_file=".env", extra="ignore")

    # ---- Storage (local-first) ----
    data_dir: Path = Field(default=Path("./.tara_data"))
    db_key: str = Field(default="")  # SQLCipher passphrase; empty => unencrypted (dev only)

    # ---- Model mode (§3.5) ----
    model_mode: Literal["local", "hosted", "hybrid"] = "local"

    # ---- Local model ----
    # Two on-device backends are supported, chosen by `local_backend`:
    #   - "ollama"            -> Ollama at `ollama_host`
    #   - "openai_compatible" -> an OpenAI-style server (e.g. LM Studio) at `lmstudio_host`
    local_backend: LocalBackend = "openai_compatible"
    ollama_host: str = "http://localhost:11434"
    lmstudio_host: str = "http://localhost:1234"  # OpenAI-compatible base; "/v1" is appended
    local_model: str = "qwen3:8b"
    # LM Studio (and most local OpenAI-compatible servers) ignore the API key, but
    # the openai client requires a non-empty value.
    local_api_key: str = "not-needed"

    # ---- Hosted model (opt-in; data leaves the device) ----
    hosted_model: str = "claude-sonnet-4-6"
    hosted_api_key: str = ""  # provider-specific wiring is settled in Slice 2 (§3.5)

    # ---- Embeddings (local, on-device) ----
    # Phase 1 serves embeddings from an OpenAI-compatible endpoint (LM Studio) at
    # `lmstudio_host`. Embeddings never egress, even in hosted mode (§3.1e/§7).
    embed_model: str = "text-embedding-qwen3-embedding-0.6b"
    embed_dim: int = 1024

    # ---- Retrieval ----
    top_k: int = 6
    # Cosine-similarity floor; if the best hit is below this the question is treated
    # as unsupported and the answerer declines rather than stretch weak context (§3.4).
    abstain_threshold: float = 0.25

    # ---- Timeouts ----
    llm_timeout_seconds: float = 60.0  # a stalled model can't hang a request forever (§3.5)

    # ---- Upload limits (§3.1a) ----
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES

    # -- Derived paths --
    @property
    def db_path(self) -> Path:
        return self.data_dir / "tara.sqlite"

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def local_openai_base_url(self) -> str:
        """Base URL for the local OpenAI-compatible server (LM Studio)."""
        return f"{self.lmstudio_host.rstrip('/')}/v1"

    # -- Validators --
    @model_validator(mode="after")
    def _require_hosted_key_when_egressing(self) -> "Settings":
        """Fail loudly if the user opts into egress without a credential (§3.5).

        The validator is provider-agnostic on purpose: it enforces that *some*
        hosted credential is present, not which provider it belongs to.
        """
        if self.model_mode in ("hosted", "hybrid") and not self.hosted_api_key.strip():
            raise ValueError(
                "model_mode is 'hosted'/'hybrid' but TARA_HOSTED_API_KEY is empty. "
                "A hosted credential is required before any data may leave the device."
            )
        return self

    @model_validator(mode="after")
    def _embed_dim_is_positive(self) -> "Settings":
        # Static sanity only. The real model<->dim integrity check is a runtime
        # probe against the live endpoint, compared to the stored index_meta row
        # (§3.2) — an API-served model's dimension can't be known from its name.
        if self.embed_dim <= 0:
            raise ValueError(f"TARA_EMBED_DIM must be positive, got {self.embed_dim}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings. Side-effect free: creating directories is done
    explicitly via `ensure_dirs()` so the cache doesn't hide filesystem writes."""
    return Settings()


def ensure_dirs(settings: Settings | None = None) -> None:
    """Create the on-device storage directories. Call once at startup / before
    first write. Idempotent."""
    s = settings or get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.blob_dir.mkdir(parents=True, exist_ok=True)
