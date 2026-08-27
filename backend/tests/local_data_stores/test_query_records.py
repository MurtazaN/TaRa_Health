"""The audit row: written on every terminal outcome, declines included."""
from __future__ import annotations

import json

import pytest

from tara.data_models import Citation
from tara.local_data_stores.db_connection import connect_db
from tara.local_data_stores.db_schema import init_db_schema
from tara.local_data_stores.query_records import insert_query_record


@pytest.fixture
def initialised_store(isolated_env):
    init_db_schema()
    return isolated_env


def _read_only_row():
    conn = connect_db()
    try:
        return conn.execute("SELECT * FROM queries").fetchone()
    finally:
        conn.close()


@pytest.mark.integration
def test_an_answered_query_is_recorded_in_full(initialised_store):
    query_id = insert_query_record(
        question="what is my specialist copay?",
        retrieved_chunk_ids=["d:1:0", "d:1:800"],
        answer="Your copay is $40.",
        citations=[Citation(chunk_id="d:1:0", filename="plan.pdf", page=1,
                            char_start=0, char_end=42, snippet="copay $40")],
        safety_flag="none",
        model_route="local",
    )

    row = _read_only_row()
    assert row["query_id"] == query_id
    assert row["question"] == "what is my specialist copay?"
    assert json.loads(row["retrieved_chunk_ids"]) == ["d:1:0", "d:1:800"]
    assert json.loads(row["citations"])[0]["chunk_id"] == "d:1:0"
    assert row["safety_flag"] == "none"
    assert row["model_route"] == "local"
    assert row["created_at"]


@pytest.mark.integration
def test_a_decline_is_recorded_too(initialised_store):
    # An eval harness needs the declines as much as the answers: "how often did
    # it refuse" is unanswerable if refusals are not written down.
    insert_query_record(
        question="what colour is my car?",
        retrieved_chunk_ids=[],
        answer="I do not see that in your documents.",
        citations=[],
        safety_flag="none",
        model_route="local",
    )

    row = _read_only_row()
    assert json.loads(row["retrieved_chunk_ids"]) == []
    assert json.loads(row["citations"]) == []


@pytest.mark.integration
def test_each_call_gets_its_own_identifier(initialised_store):
    first_id = insert_query_record("q1", [], "a", [], "none", "local")
    second_id = insert_query_record("q2", [], "a", [], "none", "local")
    assert first_id != second_id
