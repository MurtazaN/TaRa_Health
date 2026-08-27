"""The whole query flow, offline: pre-check, retrieve, generate, verify, frame, record."""
from __future__ import annotations

import pytest

from tara.data_models import Chunk
from tara.question_answering import question_answerer
from tara.question_answering.answer_response_model import GroundedAnswer
from tara.question_answering.question_answerer import ABSTENTION_MESSAGE, answer_question
from tara.safety_checks.answer_framing import SAFETY_FRAMING
from tara.semantic_search.chunk_retriever import RetrievedChunk

_COPAY_TEXT = "Specialist visit copay: $40 after the deductible."


def _retrieved(chunk_id: str = "plan:1:0", text: str = _COPAY_TEXT) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(chunk_id=chunk_id, doc_id="plan", page=1, char_start=0,
                    char_end=len(text), text=text),
        filename="plan.pdf",
        score=0.8,
    )


@pytest.fixture
def offline_flow(monkeypatch, isolated_env):
    """Retrieval and generation replaced; everything else is the real code."""
    from tara.local_data_stores.db_schema import init_db_schema

    init_db_schema()
    state: dict = {"retrieved": [_retrieved()], "generated": None}

    monkeypatch.setattr(
        question_answerer, "retrieve_chunks", lambda question: state["retrieved"]
    )
    monkeypatch.setattr(
        question_answerer,
        "generate_structured_object",
        lambda *args, **kwargs: state["generated"],
    )
    return state


@pytest.mark.integration
def test_a_supported_question_is_answered_with_a_citation(offline_flow):
    offline_flow["generated"] = GroundedAnswer(
        answer_text="Your specialist copay is $40.", cited_chunk_ids=["plan:1:0"]
    )

    answer = answer_question("what is my specialist copay?")

    assert "Your specialist copay is $40." in answer.text
    assert answer.text.endswith(SAFETY_FRAMING)
    assert answer.safety_flag == "none"
    assert [citation.chunk_id for citation in answer.citations] == ["plan:1:0"]
    assert answer.citations[0].filename == "plan.pdf"
    assert answer.citations[0].page == 1
    assert answer.citations[0].char_end == len(_COPAY_TEXT)
    assert answer.citations[0].snippet


@pytest.mark.integration
def test_an_emergency_stops_before_retrieval_and_generation(offline_flow, monkeypatch):
    def must_not_run(question):
        raise AssertionError("retrieval ran after an emergency was detected")

    monkeypatch.setattr(question_answerer, "retrieve_chunks", must_not_run)

    answer = answer_question("I have crushing chest pain")

    assert answer.safety_flag == "emergency"
    assert answer.citations == []


@pytest.mark.integration
def test_empty_retrieval_abstains_without_calling_the_model(offline_flow, monkeypatch):
    offline_flow["retrieved"] = []

    def must_not_run(*args, **kwargs):
        raise AssertionError("the model was called with no excerpts")

    monkeypatch.setattr(question_answerer, "generate_structured_object", must_not_run)

    answer = answer_question("what colour is my car?")

    assert answer.text.startswith(ABSTENTION_MESSAGE)
    assert answer.citations == []


@pytest.mark.integration
def test_an_ungrounded_figure_abstains_the_whole_answer(offline_flow):
    offline_flow["generated"] = GroundedAnswer(
        answer_text="Your specialist copay is $45.", cited_chunk_ids=["plan:1:0"]
    )

    answer = answer_question("what is my specialist copay?")

    assert answer.text.startswith(ABSTENTION_MESSAGE)
    assert "$45" not in answer.text
    assert answer.citations == []


@pytest.mark.integration
def test_a_figure_beyond_the_snippet_limit_is_still_grounded(offline_flow):
    # Grounding reads the FULL cited chunk, not the truncated display snippet.
    padded_text = ("Preamble. " * 60) + "Annual deductible: $1,500 per individual."
    offline_flow["retrieved"] = [_retrieved(text=padded_text)]
    offline_flow["generated"] = GroundedAnswer(
        answer_text="Your annual deductible is $1,500.", cited_chunk_ids=["plan:1:0"]
    )

    answer = answer_question("what is my annual deductible?")

    assert "$1,500" in answer.text
    assert answer.text.startswith("Your annual deductible") is True


@pytest.mark.integration
def test_an_invented_chunk_identifier_is_dropped(offline_flow):
    offline_flow["generated"] = GroundedAnswer(
        answer_text="Your specialist copay is $40.", cited_chunk_ids=["plan:1:0", "made:up:99"]
    )

    answer = answer_question("what is my specialist copay?")

    assert [citation.chunk_id for citation in answer.citations] == ["plan:1:0"]


@pytest.mark.integration
def test_a_model_citing_nothing_abstains(offline_flow):
    offline_flow["generated"] = GroundedAnswer(
        answer_text="I do not see that in your documents.", cited_chunk_ids=[]
    )

    answer = answer_question("what colour is my car?")

    assert answer.text.startswith(ABSTENTION_MESSAGE)
    assert answer.citations == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario, expected_flag",
    [("answered", "none"), ("declined", "none"), ("emergency", "emergency")],
)
def test_every_outcome_writes_one_audit_row(offline_flow, scenario, expected_flag):
    from tara.local_data_stores.db_connection import connect_db

    if scenario == "answered":
        offline_flow["generated"] = GroundedAnswer(
            answer_text="Your specialist copay is $40.", cited_chunk_ids=["plan:1:0"]
        )
        answer_question("what is my specialist copay?")
    elif scenario == "declined":
        offline_flow["retrieved"] = []
        answer_question("what colour is my car?")
    else:
        answer_question("I have crushing chest pain")

    conn = connect_db()
    try:
        rows = conn.execute("SELECT safety_flag, model_route FROM queries").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["safety_flag"] == expected_flag
    assert rows[0]["model_route"] == "local"


@pytest.mark.integration
def test_a_failed_audit_write_does_not_destroy_a_good_answer(offline_flow, monkeypatch):
    # Auditability matters, but losing a correct answer to a logging fault is
    # the worse outcome. The failure is recorded on the span instead.
    offline_flow["generated"] = GroundedAnswer(
        answer_text="Your specialist copay is $40.", cited_chunk_ids=["plan:1:0"]
    )

    def explode(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(question_answerer, "insert_query_record", explode)

    answer = answer_question("what is my specialist copay?")

    assert "Your specialist copay is $40." in answer.text


@pytest.mark.integration
def test_a_generation_failure_still_writes_one_audit_row(offline_flow, monkeypatch):
    """The fourth terminal outcome, which test_every_outcome_writes_one_audit_row
    does not cover: the model itself failing.

    A request that reached generation and then failed must leave a local record
    that it happened. On the hosted path that row is the only evidence an egress
    attempt was ever made, which is exactly the record wanted afterwards.
    """
    from tara.app_errors import StructuredOutputError
    from tara.local_data_stores.db_connection import connect_db

    def explode(*args, **kwargs):
        raise StructuredOutputError("the model returned nothing usable")

    monkeypatch.setattr(question_answerer, "generate_structured_object", explode)

    with pytest.raises(StructuredOutputError):
        answer_question("what is my specialist copay?")

    conn = connect_db()
    try:
        rows = conn.execute(
            "SELECT answer, model_route, safety_flag, citations FROM queries"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    # The failure CLASS is recorded, not the upstream message: the row records
    # that a request happened, and is not a place to store an error's text.
    assert "StructuredOutputError" in rows[0]["answer"]
    assert "returned nothing usable" not in rows[0]["answer"]
    assert rows[0]["model_route"] == "local"
    assert rows[0]["safety_flag"] == "none"


@pytest.mark.integration
def test_a_generation_failure_is_raised_not_turned_into_an_abstention(
    offline_flow, monkeypatch
):
    # A broken model must not read as "I don't see that in your documents",
    # which would hide a fault behind a plausible answer.
    from tara.app_errors import StructuredOutputError

    def explode(*args, **kwargs):
        raise StructuredOutputError("the model returned nothing usable")

    monkeypatch.setattr(question_answerer, "generate_structured_object", explode)

    with pytest.raises(StructuredOutputError):
        answer_question("what is my specialist copay?")
