"""Slice 1 retrieval: the right chunk is returned with correct provenance, and
weak matches abstain (§3.4). Vector post-filtering is unit-tested directly."""
from __future__ import annotations

import pytest

from tara.chunk_retrieval.chunk_retriever import retrieve_chunks


@pytest.mark.integration
def test_retrieve_returns_expected_chunk_with_provenance(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    ingest_document("policy.pdf", make_pdf([
        ["Specialist copay is $40 per visit."],
        ["Annual deductible is $1500 for the plan year."],
    ]))

    results = retrieve_chunks("what is my specialist copay")
    assert results, "expected a grounded hit"
    top = results[0]
    assert "$40" in top.chunk.text
    assert top.filename == "policy.pdf"
    assert top.chunk.page == 1
    # Provenance is well-formed: the span points back into the chunk text.
    assert top.chunk.char_start >= 0
    assert top.chunk.char_end > top.chunk.char_start
    assert top.score >= offline_ingest_env.abstain_threshold


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
def test_failed_document_is_invisible_to_retrieval(offline_ingest_env, make_pdf, monkeypatch):
    from tara.document_ingestion import ingestion_pipeline

    # Force a post-commit failure so a doc row exists but ends 'indexing_failed'.
    monkeypatch.setattr(ingestion_pipeline.vector_index, "add_embeddings",
                        lambda conn, items: (_ for _ in ()).throw(RuntimeError("vec down")))
    with pytest.raises(RuntimeError):
        ingestion_pipeline.ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))

    assert retrieve_chunks("specialist copay") == []  # not visible


# --- vector post-filter (§3.4) ---

@pytest.mark.integration
def test_vector_search_post_filters_by_doc_id(offline_ingest_env):
    from tara.storage import vector_index
    from tara.storage.metadata_db import connect_db
    from tests.conftest import fake_embed_one

    dim = offline_ingest_env.embed_dim
    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        # Two docs; both have a chunk whose text matches the query.
        for doc_id in ("docA", "docB"):
            conn.execute(
                "INSERT INTO documents (doc_id, filename, status, uploaded_at) "
                "VALUES (?, ?, 'indexed', '2026-01-01T00:00:00+00:00')",
                (doc_id, f"{doc_id}.pdf"),
            )
            cid = f"{doc_id}:1:0"
            conn.execute(
                "INSERT INTO chunks (chunk_id, doc_id, page, char_start, char_end, text) "
                "VALUES (?, ?, 1, 0, 5, 'copay')",
                (cid, doc_id),
            )
            vector_index.add_embedding(conn, cid, fake_embed_one("copay", dim))
        conn.commit()

        q = fake_embed_one("copay", dim)
        allowed = vector_index.find_nearest_chunks(conn, q, max_results=5, doc_ids=["docA"])
        assert {cid for cid, _ in allowed} == {"docA:1:0"}  # docB filtered out
    finally:
        conn.close()
