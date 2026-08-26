"""Application configuration, loaded from environment / .env.

All paths and model choices are centralized here so the rest of the code never
hard-codes a provider or a directory (Epic 1 M4: local-vs-hosted is config,
never a code change). See docs/epic1_grounded_qa/M4_grounded_answering.md.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 50 MB upload ceiling (§3.1a); a malformed/oversized upload fails fast.
_DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

LocalLLMBackend = Literal["ollama", "openai_compatible"]
GenerationMode = Literal["local", "agent_platform", "hybrid"]
AgentPlatformProvider = Literal["gemini", "llama", "mistral"]
EmbeddingModelDtype = Literal["float32", "bfloat16", "float16"]

# backend/src/tara/config.py -> parents: [0]=tara, [1]=src, [2]=backend, [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # `.env` lives at the repository root, but commands may run from `backend/`.
    # Name both so the file is found either way; the CWD-relative entry wins when
    # both exist, and the container supplies plain env vars instead of a file.
    model_config = SettingsConfigDict(
        env_prefix="TARA_",
        env_file=(_REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    # ---- Storage (local-first) ----
    # Repo-anchored, not CWD-relative: every entry point (Makefile, bootstrap.sh)
    # changes the working directory to backend/ before running, so a relative
    # default would silently relocate an existing user's store.
    data_dir: Path = Field(default=_REPO_ROOT / ".tara_data")
    db_key: str = Field(default="")  # SQLCipher passphrase; empty => unencrypted (dev only)
    # The user interface lives outside the Python package (monorepo layout), so
    # its location is configuration — the container mounts it elsewhere.
    frontend_dir: Path = Field(default=_REPO_ROOT / "frontend")

    # ---- Local server bind address ----
    # Loopback by default: this app holds PHI and must not be reachable from the
    # network unless the operator deliberately opts in. A container sets this to
    # "0.0.0.0" because Docker's published port forwards to the bridge interface,
    # which a loopback-only bind can never receive; there, Docker mediates exposure.
    # Do NOT set this to "0.0.0.0" when running directly on a host.
    server_host: str = "127.0.0.1"

    # ---- Generation mode (§3.5) ----
    # Governs GENERATION ONLY. Embeddings always run in-process and never egress,
    # so a single setting can no longer describe both (M5 §4.2).
    generation_mode: GenerationMode = "local"

    # ---- Local model ----
    # Two on-device backends are supported, chosen by `local_llm_backend`:
    #   - "ollama"            -> Ollama at `ollama_host`
    #   - "openai_compatible" -> an OpenAI-style server (e.g. LM Studio) at `lmstudio_host`
    local_llm_backend: LocalLLMBackend = "openai_compatible"
    ollama_host: str = "http://localhost:11434"
    lmstudio_host: str = "http://localhost:1234"  # OpenAI-compatible base; "/v1" is appended
    local_model: str = "qwen3:8b"
    # LM Studio (and most local OpenAI-compatible servers) ignore the API key, but
    # the openai client requires a non-empty value.
    local_api_key: str = "not-needed"

    # ---- Google Cloud Agent Platform (formerly Vertex AI) — GENERATION ONLY ----
    # Required only when generation may egress. An empty project is the exact
    # condition under which LangChain's backend auto-detection silently falls back
    # to the consumer Gemini Developer API (generativelanguage.googleapis.com),
    # which is NOT BAA-covered. Fail closed rather than egress to the wrong product.
    gcp_project: str = ""
    gcp_location: str = "us-central1"  # MaaS models are region-limited
    agent_platform_provider: AgentPlatformProvider = "gemini"
    # Model IDs are perishable: gemini-2.5-flash retires 2026-10-20, and the Llama
    # allowlist is frozen per langchain-google-vertexai release. Validated at startup.
    gemini_model: str = "gemini-3.5-flash"
    llama_model: str = "meta/llama-3.3-70b-instruct-maas"
    mistral_model: str = "mistral-medium-3"

    # Records that a human asserted a signed GCP BAA covers Agent Platform. It
    # cannot check that; it only refuses to egress until someone says so.
    phi_egress_acknowledged: bool = False

    # ---- Embeddings (in-process; never egress, in any generation mode) ----
    # Pinned by revision, not just name, for the same reason en_core_web_lg is a
    # pinned wheel: an unpinned model silently changes the vector space between
    # installs and makes every retrieval test measure a moving target.
    embed_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embed_model_revision: str = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    embed_dim: int = 1024
    # Refuse to reach Hugging Face for the weights, loading only what is already
    # cached. Defaults false so a fresh developer install can fetch the model
    # once; set true on any host that must be provably offline, where a cold
    # cache would otherwise pull ~1.19 GB silently on the first ingestion
    # (M5 §4.3). The container sets HF_HUB_OFFLINE instead, which does the same
    # job at the library level.
    embed_model_offline_only: bool = False
    # float32, NOT the weights' native bfloat16. Measured 2026-08-25 in the
    # linux/aarch64 container: a 446-token chunk took 456s under bfloat16 versus
    # 1.2s under float32 - a 380x difference, because torch's aarch64 CPU build
    # has no optimised bf16 matmul, so oneDNN fails its check (visible as
    # torchCheckFail inside mkldnn_matmul) and falls back to a scalar reference
    # path. Costs memory: peak RSS 1410MB -> 3337MB. Kept configurable because
    # the tradeoff inverts on hardware with real bf16 support.
    embed_model_dtype: EmbeddingModelDtype = "float32"

    # ---- Retrieval ----
    top_k: int = 6
    # Cosine-similarity floor; if the best hit is below this the question is treated
    # as unsupported and the answerer declines rather than stretch weak context (§3.4).
    abstain_threshold: float = 0.25

    # ---- Timeouts ----
    llm_timeout_seconds: float = 60.0  # a stalled model can't hang a request forever (§3.5)

    # ---- PHI redaction (README §6.2) ----
    # On by default: this module exists so infrastructure can carry clinical
    # content without carrying identity. A caller must never have to check it.
    phi_redaction_enabled: bool = True
    # en_core_web_lg (~427MB on disk) rather than the smaller models: measured
    # 2026-08-15, en_core_web_sm returns ZERO entities for "Member: Priya
    # Raghunathan" and leaks the given name in "MEMBER NAME: JAMAL WASHINGTON",
    # while en_core_web_md still misses ALL-CAPS names. Both formats are
    # standard in benefits documents, so the smaller models fail this module's
    # only job. Size is noise next to the local model this app already runs.
    phi_redaction_nlp_model: str = "en_core_web_lg"

    # ---- Upload limits (§3.1a) ----
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES
    # Page ceiling for PDF parsing: bounds CPU/memory on a pathological (but small)
    # file, since documents may originate from a third party (insurer/provider).
    max_pdf_pages: int = 1000

    # ---- Chunking (coupled to the embedding model — see M5 §5.5) ----
    # sentence-transformers TRUNCATES SILENTLY past the model's sequence limit, so
    # startup validates these against it rather than trusting the default.
    chunk_target_tokens: int = 800
    chunk_overlap_tokens: int = 100

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

    @property
    def active_local_model_host(self) -> str:
        """The host URL of the local backend `local_llm_backend` actually selects.

        One place maps backend -> host, so a startup check cannot warn about the
        host of a backend that is not in use.
        """
        if self.local_llm_backend == "openai_compatible":
            return self.lmstudio_host
        return self.ollama_host

    # -- Validators --
    @model_validator(mode="after")
    def _require_gcp_project_when_generation_egresses(self) -> "Settings":
        """Fail loudly if generation may egress without a project (M5 §5.4).

        Conditional because egress is conditional: in "local" mode nothing leaves
        the device. An empty project is what makes LangChain fall back to the
        consumer Gemini API, so this is the guard against silent mis-routing.
        """
        if self.generation_mode in ("agent_platform", "hybrid") and not self.gcp_project.strip():
            raise ValueError(
                "generation_mode is 'agent_platform'/'hybrid' but TARA_GCP_PROJECT is "
                "empty. An empty project silently routes generation to the consumer "
                "Gemini Developer API, which is not covered by a GCP BAA."
            )
        return self

    @model_validator(mode="after")
    def _require_phi_egress_acknowledgement(self) -> "Settings":
        """Refuse to egress until a human has asserted a BAA is in place."""
        if self.generation_mode in ("agent_platform", "hybrid") and not self.phi_egress_acknowledged:
            raise ValueError(
                "generation_mode is 'agent_platform'/'hybrid' but "
                "TARA_PHI_EGRESS_ACKNOWLEDGED is false. Answering a question sends the "
                "retrieved excerpts to Google Cloud. Set this only once a BAA covering "
                "Agent Platform is in place."
            )
        return self

    @model_validator(mode="after")
    def _embed_dim_is_positive(self) -> "Settings":
        # Static sanity only. The real model<->dim integrity check is
        # verify_embedding_dimension(), which embeds one probe string with the
        # IN-PROCESS model at startup and compares the result to this value and
        # to the stored index_meta row (§3.2). There is no endpoint to probe:
        # M5 moved embeddings in-process, so the dimension comes from the loaded
        # weights rather than from a live API response.
        if self.embed_dim <= 0:
            raise ValueError(f"TARA_EMBED_DIM must be positive, got {self.embed_dim}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings. Side-effect free: creating directories is done
    explicitly via `ensure_data_dirs()` so the cache doesn't hide filesystem writes."""
    return Settings()


def ensure_data_dirs(settings: Settings | None = None) -> None:
    """Create the on-device storage directories, owner-only (PHI on disk). Call
    once at startup / before first write. Idempotent."""
    resolved_settings = settings or get_settings()
    for directory in (resolved_settings.data_dir, resolved_settings.blob_dir):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
