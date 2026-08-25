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


@pytest.fixture
def generation_mode(monkeypatch):
    """Set TARA_GENERATION_MODE hermetically (+ the egress prerequisites)."""
    def _set(mode: str) -> None:
        monkeypatch.setenv("TARA_GENERATION_MODE", mode)
        if mode in ("agent_platform", "hybrid"):
            monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
            monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
        config.get_settings.cache_clear()
    yield _set
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_local_mode_uses_local_client(generation_mode):
    generation_mode("local")
    assert isinstance(get_llm_client(), OllamaClient)


@pytest.mark.unit
def test_local_mode_ignores_the_opt_in(generation_mode):
    generation_mode("local")
    # The per-query opt-in must be inert in local mode: no silent egress path.
    assert isinstance(get_llm_client(prefer_agent_platform=True), OllamaClient)


@pytest.mark.unit
def test_agent_platform_mode_uses_agent_platform_client(generation_mode):
    generation_mode("agent_platform")
    assert isinstance(get_llm_client(), AgentPlatformClient)


@pytest.mark.unit
def test_hybrid_defaults_to_local(generation_mode):
    generation_mode("hybrid")
    assert isinstance(get_llm_client(), OllamaClient)


@pytest.mark.unit
def test_hybrid_opt_in_uses_agent_platform(generation_mode):
    generation_mode("hybrid")
    assert isinstance(get_llm_client(prefer_agent_platform=True), AgentPlatformClient)
