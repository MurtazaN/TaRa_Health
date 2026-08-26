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
    # Hard-coded, not compared against the constant it is meant to pin.
    assert model.attempts == 3


@pytest.mark.unit
@pytest.mark.parametrize("status", [403, 404])
def test_operator_errors_are_never_retried(egress_env, monkeypatch, status):
    model = _FakeChatModel(failures=[_api_error(status) for _ in range(5)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    assert model.attempts == 1


@pytest.mark.unit
@pytest.mark.parametrize("status", [403, 429])
def test_exception_message_never_carries_the_upstream_error_text(egress_env, monkeypatch, status):
    """Spec assertion 8, with teeth: the secret lives in the UPSTREAM error.

    web_app renders str(exc) to the client verbatim. The real §7.2 risk is not
    our own formatting — it is the CHAINED cause, because Google errors routinely
    echo the request body back, and the request body is the assembled excerpts.
    Planting the identifier in the upstream message is the only version of this
    test that can fail; asserting against a message that never contained it holds
    vacuously. repr() is checked too, since a chained cause reaching either one
    reaches the client through the same handler.
    """
    secret = "MEMBER-ID-XQZ8842190-PRIYA-RAGHUNATHAN"
    upstream_error = _api_error(status)
    upstream_error.args = (
        f"upstream said {status}: request payload was 'Deductible for {secret}'",
    )
    model = _FakeChatModel(failures=[upstream_error for _ in range(10)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)

    expected_error = (
        AgentPlatformConfigError if status == 403 else AgentPlatformUnavailableError
    )
    with pytest.raises(expected_error) as caught:
        agent_platform_client.AgentPlatformClient().generate("sys", secret)
    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)


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
    """Guards a PRIVATE, LAZY import. If langchain-google-vertexai moves these
    symbols, this fails loudly rather than silently disabling the startup model
    check. The accessor imports on call so the local path never loads the
    egress library."""
    model_names = agent_platform_client._maas_model_names()
    assert len(model_names) > 0
    assert "meta/llama-3.3-70b-instruct-maas" in model_names


# ---- Transport failures: no status attribute, still retryable (M5 §7.1) ----


def _transport_error_factories():
    """The exception classes a DNS blip or TLS reset actually arrives as.

    None of them carry an HTTP status, which is exactly why classifying by
    status alone turned every one of them into a non-retryable operator error.
    """
    from google.auth.exceptions import TransportError as GoogleTransportError
    from httpx import TransportError as HttpxTransportError

    return [
        pytest.param(lambda: ConnectionError("connection reset by peer"), id="ConnectionError"),
        pytest.param(lambda: TimeoutError("socket timed out"), id="TimeoutError"),
        pytest.param(lambda: GoogleTransportError("refresh failed"), id="GoogleTransportError"),
        pytest.param(lambda: HttpxTransportError("name resolution failed"), id="HttpxTransportError"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize("make_transport_error", _transport_error_factories())
def test_transport_errors_are_retried_then_raise_unavailable(
    egress_env, monkeypatch, make_transport_error
):
    """A network fault must exhaust the retry budget and map to 503, not 500.

    Spec §7.1 lists "connection error" as retryable. Classifying on status alone
    made these fall through to AgentPlatformConfigError, so a DNS blip told the
    user to check their IAM permissions and refused to try again.
    """
    model = _FakeChatModel(failures=[make_transport_error() for _ in range(10)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)
    with pytest.raises(AgentPlatformUnavailableError):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    assert model.attempts == 3


@pytest.mark.unit
def test_transport_error_is_retried_then_succeeds(egress_env, monkeypatch):
    model = _FakeChatModel(failures=[ConnectionError("connection reset by peer")])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)
    assert agent_platform_client.AgentPlatformClient().generate("sys", "user") == "the answer"
    assert model.attempts == 2


@pytest.mark.unit
def test_unrecognised_failure_fails_closed_with_one_attempt(egress_env, monkeypatch):
    """An error that is neither a known status nor a known transport class must
    surface once as an operator error rather than be retried against an unknown
    fault."""
    model = _FakeChatModel(failures=[ValueError("something entirely unexpected")] * 5)
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError, match="unrecognised"):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    assert model.attempts == 1


@pytest.mark.unit
def test_missing_credentials_map_to_a_config_error(egress_env, monkeypatch):
    from google.auth.exceptions import DefaultCredentialsError

    model = _FakeChatModel(failures=[DefaultCredentialsError("no ADC")] * 5)
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError, match="Application Default Credentials"):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    assert model.attempts == 1


# ---- Construction: the one line that keeps PHI off the consumer API ----


@pytest.fixture
def cleared_chat_model_cache():
    """Clear _chat_model's lru_cache around a test that actually constructs it.

    Every other test patches the accessor wholesale, so a cached real client
    built here would poison them. Cleared on both sides for that reason.
    """
    agent_platform_client._chat_model.cache_clear()
    yield
    agent_platform_client._chat_model.cache_clear()


@pytest.mark.unit
def test_gemini_model_is_constructed_with_vertexai_pinned(
    egress_env, monkeypatch, cleared_chat_model_cache
):
    """Spec assertion 5. THE assertion of this module.

    `vertexai=True` is the single line stopping PHI from reaching the consumer
    Gemini Developer API, which no GCP BAA covers. ChatGoogleGenerativeAI
    defaults that field to None, so the fallback is real: without this test,
    deleting the line would ship a green suite.
    """
    captured: dict = {}

    class _RecordingChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import langchain_google_genai
    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", _RecordingChatModel)
    agent_platform_client._chat_model()

    assert captured["vertexai"] is True
    assert captured["project"] == "test-project"
    assert captured["location"] == "us-central1"
    assert captured["timeout"] == 60.0
    assert captured["model"] == "gemini-3.5-flash"


@pytest.mark.unit
def test_gemini_vertexai_field_still_defaults_to_none(egress_env):
    """The fallback the assertion above guards is real, not hypothetical.

    If a future langchain-google-genai made vertexai default to True, this fails
    and the pin above becomes belt-and-braces rather than load-bearing — worth
    knowing either way.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    assert ChatGoogleGenerativeAI.model_fields["vertexai"].default is None


@pytest.mark.unit
def test_maas_model_is_constructed_with_project_location_and_timeout(
    egress_env, monkeypatch, cleared_chat_model_cache
):
    """The MaaS branch must carry the same routing AND the request timeout.

    No `vertexai` assertion here on purpose: the MaaS classes have no such field
    (asserted below) because they are Vertex-only, so there is no consumer-API
    path to pin. `timeout` was previously dropped on this branch, which let a
    stalled call hang a request forever.
    """
    monkeypatch.setenv("TARA_AGENT_PLATFORM_PROVIDER", "llama")
    config.get_settings.cache_clear()
    captured: dict = {}

    def _record_maas_model(model_name, **kwargs):
        captured["model_name"] = model_name
        captured["kwargs"] = kwargs
        return object()

    from langchain_google_vertexai import model_garden_maas
    monkeypatch.setattr(model_garden_maas, "get_vertex_maas_model", _record_maas_model)
    agent_platform_client._chat_model()

    assert captured["model_name"] == "meta/llama-3.3-70b-instruct-maas"
    assert captured["kwargs"]["project"] == "test-project"
    assert captured["kwargs"]["location"] == "us-central1"
    assert captured["kwargs"]["timeout"] == 60.0


@pytest.mark.unit
def test_maas_classes_expose_no_vertexai_field():
    """Documents why the MaaS constructor test asserts no `vertexai`.

    MaaS is Vertex-only, so its absence is correct rather than a gap. If the
    package ever adds the field, this fails and the MaaS branch needs the same
    explicit pin the Gemini branch has.
    """
    from langchain_google_vertexai.model_garden_maas.llama import VertexModelGardenLlama

    assert "vertexai" not in VertexModelGardenLlama.model_fields
    assert "timeout" in VertexModelGardenLlama.model_fields
