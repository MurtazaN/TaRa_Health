"""Each local backend asks its own server to constrain output to the schema.

Raw JSON text is returned, not a parsed object: validation lives in exactly one
module (structured_completion), so three backends cannot drift on what "valid"
means.
"""
from __future__ import annotations

import json

import pytest

from tara import config
from tara.llm_clients.llm_client_interface import resolve_model_route
from tara.llm_clients.ollama_client import OllamaClient
from tara.llm_clients.openai_compatible_client import OpenAICompatibleClient
from tara.question_answering.answer_response_model import GROUNDED_ANSWER_JSON_SCHEMA


class _CapturedOpenAICall:
    """Stands in for openai.OpenAI, recording the kwargs the client sends."""

    def __init__(self, payload: str):
        self.payload = payload
        self.captured_kwargs: dict = {}
        completions = type("Completions", (), {"create": self._create})()
        self.chat = type("Chat", (), {"completions": completions})()

    def _create(self, **kwargs):
        self.captured_kwargs = kwargs
        message = type("Message", (), {"content": self.payload})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


@pytest.fixture
def local_settings(monkeypatch):
    monkeypatch.setenv("TARA_GENERATION_MODE", "local")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_openai_compatible_client_sends_the_schema_and_returns_raw_json(local_settings, monkeypatch):
    payload = '{"answer_text": "Your copay is $40.", "cited_chunk_ids": ["doc1:2:0"]}'
    captured = _CapturedOpenAICall(payload)
    monkeypatch.setattr(
        "tara.llm_clients.openai_compatible_client.OpenAI", lambda **kwargs: captured
    )

    returned = OpenAICompatibleClient().generate_structured_json(
        "system", "user", GROUNDED_ANSWER_JSON_SCHEMA
    )

    assert returned == payload
    response_format = captured.captured_kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == GROUNDED_ANSWER_JSON_SCHEMA


@pytest.mark.unit
def test_ollama_client_sends_the_schema_as_the_format_argument(local_settings, monkeypatch):
    payload = '{"answer_text": "Your copay is $40.", "cited_chunk_ids": ["doc1:2:0"]}'
    captured: dict = {}

    class _CapturedOllamaClient:
        def __init__(self, host: str):
            self.host = host

        def chat(self, **kwargs):
            captured.update(kwargs)
            return {"message": {"content": payload}}

    monkeypatch.setattr("ollama.Client", _CapturedOllamaClient)

    returned = OllamaClient().generate_structured_json(
        "system", "user", GROUNDED_ANSWER_JSON_SCHEMA
    )

    assert returned == payload
    assert captured["format"] == GROUNDED_ANSWER_JSON_SCHEMA
    assert json.loads(returned)["cited_chunk_ids"] == ["doc1:2:0"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "mode, prefer, expected_route",
    [
        ("local", False, "local"),
        ("local", True, "local"),
        ("agent_platform", False, "agent_platform"),
        ("hybrid", False, "local"),
        ("hybrid", True, "agent_platform"),
    ],
)
def test_resolve_model_route_names_the_backend_that_will_be_used(
    monkeypatch, mode, prefer, expected_route
):
    monkeypatch.setenv("TARA_GENERATION_MODE", mode)
    if mode in ("agent_platform", "hybrid"):
        monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
        monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
    config.get_settings.cache_clear()
    try:
        assert resolve_model_route(prefer_agent_platform=prefer) == expected_route
    finally:
        config.get_settings.cache_clear()
