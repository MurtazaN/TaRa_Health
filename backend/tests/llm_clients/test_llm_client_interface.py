"""get_llm_client routing: generation_mode x prefer_agent_platform -> backend.

Local mode must NEVER return the Agent Platform client — that is the only code
path by which a generated answer's context leaves the device. Embeddings are
in-process in every mode, so no routing decision can cause ingestion egress.
"""
from __future__ import annotations

import pytest

from tara import config
from tara.llm_clients.agent_platform_client import AgentPlatformClient
from tara.llm_clients.llm_client_interface import get_llm_client
from tara.llm_clients.ollama_client import OllamaClient
from tara.llm_clients.openai_compatible_client import OpenAICompatibleClient


@pytest.fixture
def generation_mode(monkeypatch):
    """Set TARA_GENERATION_MODE + TARA_LOCAL_LLM_BACKEND hermetically (+ the
    egress prerequisites for agent_platform/hybrid)."""
    def _set(mode: str, local_llm_backend: str = "openai_compatible") -> None:
        monkeypatch.setenv("TARA_GENERATION_MODE", mode)
        monkeypatch.setenv("TARA_LOCAL_LLM_BACKEND", local_llm_backend)
        if mode in ("agent_platform", "hybrid"):
            monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
            monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
        config.get_settings.cache_clear()
    yield _set
    config.get_settings.cache_clear()


@pytest.mark.unit
@pytest.mark.parametrize(
    "local_llm_backend, expected_client",
    [("openai_compatible", OpenAICompatibleClient), ("ollama", OllamaClient)],
)
def test_local_mode_uses_configured_local_backend(generation_mode, local_llm_backend, expected_client):
    generation_mode("local", local_llm_backend=local_llm_backend)
    assert isinstance(get_llm_client(), expected_client)


@pytest.mark.unit
@pytest.mark.parametrize(
    "local_llm_backend, expected_client",
    [("openai_compatible", OpenAICompatibleClient), ("ollama", OllamaClient)],
)
def test_local_mode_ignores_the_opt_in(generation_mode, local_llm_backend, expected_client):
    generation_mode("local", local_llm_backend=local_llm_backend)
    # The per-query opt-in must be inert in local mode: no silent egress path,
    # regardless of which on-device backend is configured.
    assert isinstance(get_llm_client(prefer_agent_platform=True), expected_client)


@pytest.mark.unit
def test_agent_platform_mode_uses_agent_platform_client(generation_mode):
    generation_mode("agent_platform")
    assert isinstance(get_llm_client(), AgentPlatformClient)


@pytest.mark.unit
@pytest.mark.parametrize(
    "local_llm_backend, expected_client",
    [("openai_compatible", OpenAICompatibleClient), ("ollama", OllamaClient)],
)
def test_hybrid_defaults_to_local(generation_mode, local_llm_backend, expected_client):
    generation_mode("hybrid", local_llm_backend=local_llm_backend)
    assert isinstance(get_llm_client(), expected_client)


@pytest.mark.unit
def test_hybrid_opt_in_uses_agent_platform(generation_mode):
    generation_mode("hybrid")
    assert isinstance(get_llm_client(prefer_agent_platform=True), AgentPlatformClient)
