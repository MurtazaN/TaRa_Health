"""The typed answer contract: the model returns fields, not markers to parse."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from tara.question_answering.answer_response_model import (
    GROUNDED_ANSWER_JSON_SCHEMA,
    GroundedAnswer,
)


@pytest.mark.unit
def test_valid_payload_parses_into_the_model():
    parsed = GroundedAnswer.model_validate_json(
        '{"answer_text": "Your copay is $40.", "cited_chunk_ids": ["doc1:2:0"]}'
    )
    assert parsed.answer_text == "Your copay is $40."
    assert parsed.cited_chunk_ids == ["doc1:2:0"]


@pytest.mark.unit
def test_an_abstention_is_an_empty_citation_list_not_a_separate_field():
    parsed = GroundedAnswer.model_validate_json(
        '{"answer_text": "I do not see that in your documents.", "cited_chunk_ids": []}'
    )
    assert parsed.cited_chunk_ids == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "malformed_payload",
    [
        '{"answer_text": "x"}',                                   # citations missing
        '{"cited_chunk_ids": []}',                                # answer missing
        '{"answer_text": "x", "cited_chunk_ids": "doc1:2:0"}',    # citations not a list
    ],
)
def test_a_malformed_payload_is_rejected(malformed_payload):
    with pytest.raises(ValidationError):
        GroundedAnswer.model_validate_json(malformed_payload)


@pytest.mark.unit
def test_the_schema_is_strict_so_a_server_can_constrain_decoding():
    # additionalProperties=false and both fields required are what make
    # OpenAI-style `strict: true` acceptable to the server. A schema derived
    # from Pydantic alone omits additionalProperties, so it is written by hand.
    assert GROUNDED_ANSWER_JSON_SCHEMA["additionalProperties"] is False
    assert set(GROUNDED_ANSWER_JSON_SCHEMA["required"]) == {"answer_text", "cited_chunk_ids"}
    assert set(GROUNDED_ANSWER_JSON_SCHEMA["properties"]) == {"answer_text", "cited_chunk_ids"}
