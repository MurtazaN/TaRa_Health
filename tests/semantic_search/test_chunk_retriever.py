"""Chunk retrieval: right chunk with provenance, abstention on weak matches,
and a hard stop when the index was built with a different embedding model."""
from __future__ import annotations

import pytest

from tara.app_errors import IndexMismatchError
from tara.semantic_search.chunk_retriever import retrieve_chunks


@pytest.mark.integration
def test_retrieve_returns_expected_chunk_with_provenance(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    ingest_document("policy.pdf", make_pdf([
        ["Specialist copay is $40 per visit."],
        ["Annual deductible is $1500 for the plan year."],
    ]))

    results = retrieve_chunks("what is my specialist copay")
    assert results, "expected a grounded hit"
    top_result = results[0]
    assert "$40" in top_result.chunk.text
    assert top_result.filename == "policy.pdf"
    assert top_result.chunk.page == 1
    # Provenance is well-formed: the span points back into the chunk text.
    assert top_result.chunk.char_start >= 0
    assert top_result.chunk.char_end > top_result.chunk.char_start
    assert top_result.score >= offline_ingest_env.abstain_threshold


@pytest.mark.integration
def test_retrieve_abstains_on_unsupported_question(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    # No overlap with any indexed text -> below the abstention threshold.
    assert retrieve_chunks("banana kiwi mango orchestra volcano") == []


@pytest.mark.integration
def test_retrieve_on_empty_index_returns_empty(offline_ingest_env):
    assert retrieve_chunks("anything at all") == []


@pytest.mark.integration
def test_retrieve_raises_on_stale_index(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document
    from tara.local_data_stores import embedding_index_meta
    from tara.local_data_stores.db_connection import connect_db

    ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))

    # Simulate a config change after indexing: stored meta no longer matches.
    conn = connect_db()
    try:
        embedding_index_meta.write_index_meta(
            conn, "some-other-model", 999, "2026-01-01T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(IndexMismatchError, match="Re-index"):
        retrieve_chunks("specialist copay")
