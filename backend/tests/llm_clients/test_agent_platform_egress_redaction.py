"""Nothing identifying may reach Google, and nothing factual may be lost on the way.

The chokepoint is the client itself, not its caller: a redaction call in the
answerer would have to be repeated by every future caller, and one omission is a
PHI incident.
"""
from __future__ import annotations

import json

import pytest

from tara import config
from tara.llm_clients import agent_platform_client
from tara.llm_clients.agent_platform_client import AgentPlatformClient
from tara.phi_redaction import EGRESS_REDACTED_ENTITIES, REDACTED_ENTITIES
from tara.question_answering.answer_response_model import GROUNDED_ANSWER_JSON_SCHEMA

_EXCERPT_WITH_IDENTITY = (
    "Member: Priya Raghunathan\n"
    "Member ID: XQZ884219\n"
    "Plan: Gold PPO 2026\n"
    "Specialist visit copay: $40 after a 30-day waiting period."
)


class _CapturingChatModel:
    """Records the messages sent, and answers with a fixed structured payload."""

    def __init__(self):
        self.sent_messages: list = []

    def invoke(self, messages):
        self.sent_messages.append(messages)
        return type("Reply", (), {"content": "unused"})()

    def with_structured_output(self, schema, method):
        self.structured_schema = schema
        self.structured_method = method

        class _Structured:
            def __init__(self, outer):
                self.outer = outer

            def invoke(self, messages):
                self.outer.sent_messages.append(messages)
                return {"answer_text": "Your copay is $40.", "cited_chunk_ids": ["d:1:0"]}

        return _Structured(self)


@pytest.fixture
def egress_settings(monkeypatch):
    monkeypatch.setenv("TARA_GENERATION_MODE", "agent_platform")
    monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
    monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture
def capturing_chat_model(monkeypatch):
    captured = _CapturingChatModel()
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: captured)
    return captured


def _sent_user_text(captured) -> str:
    """The human-role text of the last message list sent upstream."""
    role, text = captured.sent_messages[-1][-1]
    assert role == "human"
    return text


@pytest.mark.unit
def test_the_egress_entity_list_differs_from_the_tracing_list_only_by_dates():
    assert set(REDACTED_ENTITIES) - set(EGRESS_REDACTED_ENTITIES) == {"DATE_TIME"}
    assert set(EGRESS_REDACTED_ENTITIES) - set(REDACTED_ENTITIES) == set()


@pytest.mark.integration
def test_free_text_generation_strips_identity_before_sending(egress_settings, capturing_chat_model):
    AgentPlatformClient().generate("system", _EXCERPT_WITH_IDENTITY)

    sent = _sent_user_text(capturing_chat_model)
    assert "Priya" not in sent
    assert "Raghunathan" not in sent
    assert "XQZ884219" not in sent


@pytest.mark.integration
def test_structured_generation_strips_identity_before_sending(egress_settings, capturing_chat_model):
    returned = AgentPlatformClient().generate_structured_json(
        "system", _EXCERPT_WITH_IDENTITY, GROUNDED_ANSWER_JSON_SCHEMA
    )

    sent = _sent_user_text(capturing_chat_model)
    assert "Priya" not in sent
    assert "XQZ884219" not in sent
    assert json.loads(returned)["cited_chunk_ids"] == ["d:1:0"]
    assert capturing_chat_model.structured_method == "json_schema"


@pytest.mark.integration
def test_the_facts_an_answer_needs_survive_the_egress_redaction(
    egress_settings, capturing_chat_model
):
    # The whole reason DATE_TIME is excluded: it eats the plan year and the
    # waiting period, which are the answer, not the identity.
    AgentPlatformClient().generate("system", _EXCERPT_WITH_IDENTITY)

    sent = _sent_user_text(capturing_chat_model)
    assert "$40" in sent
    assert "2026" in sent
    assert "30-day waiting period" in sent


@pytest.mark.integration
def test_the_system_prompt_is_sent_unredacted(egress_settings, capturing_chat_model):
    # The system prompt is a constant this repository authors; running Presidio
    # over it costs a pass and risks mangling the instructions.
    AgentPlatformClient().generate("You are Tara, a personal health assistant.", "hello")

    role, text = capturing_chat_model.sent_messages[-1][0]
    assert role == "system"
    assert text == "You are Tara, a personal health assistant."
