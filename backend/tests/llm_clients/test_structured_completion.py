"""One place validates the model's JSON, and one place retries it."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from tara import config
from tara.app_errors import StructuredOutputError
from tara.llm_clients import structured_completion
from tara.llm_clients.structured_completion import generate_structured_object


class _Person(BaseModel):
    name: str
    age: int


_PERSON_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name", "age"],
    "additionalProperties": False,
}


class _ScriptedClient:
    """Returns each scripted payload in turn, recording the prompts it saw."""

    def __init__(self, payloads: list[str]):
        self.payloads = payloads
        self.seen_user_prompts: list[str] = []

    def generate(self, system_prompt, user_prompt):  # pragma: no cover - unused here
        raise AssertionError("structured generation must not fall back to free text")

    def generate_structured_json(self, system_prompt, user_prompt, json_schema):
        self.seen_user_prompts.append(user_prompt)
        return self.payloads[len(self.seen_user_prompts) - 1]


@pytest.fixture
def local_settings(monkeypatch):
    monkeypatch.setenv("TARA_GENERATION_MODE", "local")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _install(monkeypatch, client):
    monkeypatch.setattr(structured_completion, "get_llm_client", lambda **kwargs: client)


@pytest.mark.unit
def test_a_valid_payload_returns_a_validated_object(local_settings, monkeypatch):
    client = _ScriptedClient(['{"name": "Ada", "age": 36}'])
    _install(monkeypatch, client)

    result = generate_structured_object("system", "user", _Person, _PERSON_SCHEMA)

    assert isinstance(result, _Person)
    assert result.name == "Ada"
    assert len(client.seen_user_prompts) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "first_payload",
    ['not json at all', '{"name": "Ada"}', '{"name": "Ada", "age": "old"}'],
)
def test_an_invalid_payload_is_retried_with_a_correction(local_settings, monkeypatch, first_payload):
    client = _ScriptedClient([first_payload, '{"name": "Ada", "age": 36}'])
    _install(monkeypatch, client)

    result = generate_structured_object("system", "user", _Person, _PERSON_SCHEMA)

    assert result.age == 36
    assert len(client.seen_user_prompts) == 2
    assert client.seen_user_prompts[0] == "user"
    assert client.seen_user_prompts[1] != "user"


@pytest.mark.unit
def test_the_retry_budget_is_bounded_and_the_error_carries_no_model_output(
    local_settings, monkeypatch
):
    secret_bearing_payload = '{"name": "Priya Raghunathan", "member_id": "A1234567"'
    client = _ScriptedClient([secret_bearing_payload] * 5)
    _install(monkeypatch, client)

    with pytest.raises(StructuredOutputError) as raised:
        generate_structured_object("system", "user", _Person, _PERSON_SCHEMA)

    assert len(client.seen_user_prompts) == structured_completion.MAX_STRUCTURED_ATTEMPTS
    assert "Priya" not in str(raised.value)
    assert "A1234567" not in str(raised.value)
