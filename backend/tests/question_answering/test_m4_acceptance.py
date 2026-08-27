"""The M4 contract's four acceptance criteria, over a real ingested document.

Retrieval, storage and the vector index are REAL here; only the model is
scripted, because the criteria are about what the app does with what a model
returns, not about which model returned it.
"""
from __future__ import annotations

import pytest

from tara.document_ingestion.ingestion_pipeline import ingest_document
from tara.question_answering import question_answerer
from tara.question_answering.answer_response_model import GroundedAnswer
from tara.question_answering.question_answerer import ABSTENTION_MESSAGE, answer_question

_PLAN_PAGE = [
    "GOLD PPO 2026 SUMMARY OF BENEFITS",
    "Specialist visit copay: $40 after the deductible.",
    "Annual deductible: $1,500 per individual.",
    "Coinsurance: 20% for in-network services.",
]


@pytest.fixture
def ingested_plan(offline_ingest_env, make_pdf, monkeypatch):
    """Ingest the plan for real, on the fake embedder's own relevance scale.

    `offline_ingest_env`'s deterministic bag-of-words embedder does not score on
    the same scale as the real model the 0.25 default was calibrated for: the
    copay question shares three tokens with a four-fact chunk and lands at 0.236,
    so a plainly relevant question would abstain at retrieval and never reach the
    flow these criteria are about. Retrieval, storage and the index stay real;
    only the threshold is put on the fixture's scale, and an off-topic question
    still scores 0.0 and still abstains. Calibrating the real threshold is M8.
    """
    from tara import config

    monkeypatch.setenv("TARA_ABSTAIN_THRESHOLD", "0.1")
    config.get_settings.cache_clear()
    ingest_document("gold_ppo_plan.pdf", make_pdf([_PLAN_PAGE]))
    return config.get_settings()


def _script_the_model(monkeypatch, answer_text: str, cite_first_chunk: bool = True):
    """Answer with `answer_text`, citing the top retrieved chunk if asked to."""
    def _generate(system_prompt, user_prompt, response_model, json_schema, **kwargs):
        cited: list[str] = []
        if cite_first_chunk:
            first_marker = user_prompt.split("[", 1)[1].split("]", 1)[0]
            cited = [first_marker]
        return GroundedAnswer(answer_text=answer_text, cited_chunk_ids=cited)

    monkeypatch.setattr(question_answerer, "generate_structured_object", _generate)


@pytest.mark.integration
def test_criterion_1_the_cited_page_contains_the_stated_fact(ingested_plan, monkeypatch):
    _script_the_model(monkeypatch, "Your specialist copay is $40.")

    answer = answer_question("what is my specialist visit copay?")

    assert answer.citations, "an answered question must carry a citation"
    assert answer.citations[0].page == 1
    assert "$40" in answer.citations[0].snippet


@pytest.mark.integration
def test_criterion_2_the_stated_number_matches_the_document(ingested_plan, monkeypatch):
    _script_the_model(monkeypatch, "Your annual deductible is $1,500.")

    answer = answer_question("what is my annual deductible?")

    assert "$1,500" in answer.text
    assert not answer.text.startswith(ABSTENTION_MESSAGE)


@pytest.mark.integration
def test_criterion_3_an_unanswerable_question_is_declined(ingested_plan, monkeypatch):
    _script_the_model(monkeypatch, "I do not see that.", cite_first_chunk=False)

    answer = answer_question("what colour is my car?")

    assert answer.text.startswith(ABSTENTION_MESSAGE)
    assert answer.citations == []


@pytest.mark.integration
def test_criterion_4_no_ungrounded_number_survives(ingested_plan, monkeypatch):
    _script_the_model(monkeypatch, "Your specialist copay is $95.")

    answer = answer_question("what is my specialist visit copay?")

    assert "$95" not in answer.text
    assert answer.text.startswith(ABSTENTION_MESSAGE)
