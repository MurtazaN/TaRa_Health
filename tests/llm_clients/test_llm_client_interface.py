"""get_llm_client routing: model_mode x prefer_hosted -> backend. Local mode
must NEVER return the hosted client (no silent PHI egress)."""
from __future__ import annotations

import pytest

from tara import config
from tara.llm_clients.hosted_client import HostedLLMClient
from tara.llm_clients.llm_client_interface import get_llm_client
from tara.llm_clients.ollama_client import OllamaClient


@pytest.fixture
def model_mode(monkeypatch):
    """Set TARA_MODEL_MODE hermetically (+ a hosted credential where required)."""
    def _set(mode: str) -> None:
        monkeypatch.setenv("TARA_MODEL_MODE", mode)
        if mode in ("hosted", "hybrid"):
            monkeypatch.setenv("TARA_HOSTED_API_KEY", "test-credential")
        config.get_settings.cache_clear()
    yield _set
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_local_mode_uses_local_client(model_mode):
    model_mode("local")
    assert isinstance(get_llm_client(), OllamaClient)


@pytest.mark.unit
def test_local_mode_ignores_prefer_hosted(model_mode):
    model_mode("local")
    # The per-query opt-in must be inert in local mode: no silent egress path.
    assert isinstance(get_llm_client(prefer_hosted=True), OllamaClient)


@pytest.mark.unit
def test_hosted_mode_uses_hosted_client(model_mode):
    model_mode("hosted")
    assert isinstance(get_llm_client(), HostedLLMClient)


@pytest.mark.unit
def test_hybrid_defaults_to_local(model_mode):
    model_mode("hybrid")
    assert isinstance(get_llm_client(), OllamaClient)


@pytest.mark.unit
def test_hybrid_prefer_hosted_opts_into_hosted(model_mode):
    model_mode("hybrid")
    assert isinstance(get_llm_client(prefer_hosted=True), HostedLLMClient)
