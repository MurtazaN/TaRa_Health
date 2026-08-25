"""AgentPlatformClient: explicit Vertex routing, failure classification, bounded
retry, and the guarantee that no user content reaches an exception message."""
from __future__ import annotations

import pytest

from tara import config
from tara.app_errors import AgentPlatformConfigError, AgentPlatformUnavailableError
from tara.llm_clients import agent_platform_client


@pytest.fixture
def egress_env(monkeypatch):
    monkeypatch.setenv("TARA_GENERATION_MODE", "agent_platform")
    monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
    monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


class _FakeResponse:
    def __init__(self, text): self.content = text


class _FakeChatModel:
    """Raises the queued exceptions in order, then returns text."""

    def __init__(self, failures=()):
        self.failures = list(failures)
        self.attempts = 0

    def invoke(self, messages):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        return _FakeResponse("the answer")


def _api_error(code: int) -> Exception:
    error = RuntimeError(f"upstream said {code}")
    error.code = code          # what _classify_failure reads
    return error


@pytest.mark.unit
def test_generate_returns_model_text(egress_env, monkeypatch):
    model = _FakeChatModel()
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    assert agent_platform_client.AgentPlatformClient().generate("sys", "user") == "the answer"


@pytest.mark.unit
def test_quota_error_is_retried_then_succeeds(egress_env, monkeypatch):
    model = _FakeChatModel(failures=[_api_error(429)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)
    assert agent_platform_client.AgentPlatformClient().generate("sys", "user") == "the answer"
    assert model.attempts == 2


@pytest.mark.unit
def test_persistent_quota_error_raises_unavailable_with_bounded_attempts(egress_env, monkeypatch):
    model = _FakeChatModel(failures=[_api_error(429) for _ in range(10)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)
    with pytest.raises(AgentPlatformUnavailableError):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    # A runaway retry must not hide behind a green test.
    assert model.attempts == agent_platform_client._MAX_ATTEMPTS


@pytest.mark.unit
@pytest.mark.parametrize("status", [403, 404])
def test_operator_errors_are_never_retried(egress_env, monkeypatch, status):
    model = _FakeChatModel(failures=[_api_error(status) for _ in range(5)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    assert model.attempts == 1


@pytest.mark.unit
def test_exception_message_never_carries_user_content(egress_env, monkeypatch):
    # web_app renders str(exc) to the client, so PHI must never reach it.
    secret = "MEMBER-ID-XQZ8842190-PRIYA-RAGHUNATHAN"
    model = _FakeChatModel(failures=[_api_error(403)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError) as caught:
        agent_platform_client.AgentPlatformClient().generate("sys", secret)
    assert secret not in str(caught.value)


@pytest.mark.unit
def test_verify_generation_model_rejects_unknown_maas_model(egress_env, monkeypatch):
    monkeypatch.setenv("TARA_AGENT_PLATFORM_PROVIDER", "llama")
    monkeypatch.setenv("TARA_LLAMA_MODEL", "meta/llama-9.9-imaginary-maas")
    config.get_settings.cache_clear()
    with pytest.raises(AgentPlatformConfigError, match="not a known"):
        agent_platform_client.verify_generation_model()


@pytest.mark.unit
def test_verify_generation_model_accepts_a_known_maas_model(egress_env, monkeypatch):
    monkeypatch.setenv("TARA_AGENT_PLATFORM_PROVIDER", "llama")
    monkeypatch.setenv("TARA_LLAMA_MODEL", "meta/llama-3.3-70b-instruct-maas")
    config.get_settings.cache_clear()
    agent_platform_client.verify_generation_model()   # must not raise


@pytest.mark.unit
def test_maas_allowlist_import_still_resolves():
    """Guards a PRIVATE import. If langchain-google-vertexai moves these symbols,
    this fails loudly rather than silently disabling the startup model check."""
    assert len(agent_platform_client._MAAS_MODEL_NAMES) > 0
    assert "meta/llama-3.3-70b-instruct-maas" in agent_platform_client._MAAS_MODEL_NAMES
