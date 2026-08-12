"""Ingestion pipeline orchestration: transactional writes, content-hash dedup,
replace safety, and failure cleanup (Epic 1 ingestion contract)."""
from __future__ import annotations

import pytest

from tara.local_data_stores import vector_index
from tara.local_data_stores.db_connection import connect_db


@pytest.mark.integration
def test_ingest_indexes_document_with_chunks_and_vectors(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    document = ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    assert document.status == "indexed"
    assert document.page_count == 1
    assert document.content_hash  # sha256 recorded

    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)  # vec0 is per-connection
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vector_count = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert chunk_count == vector_count > 0  # every chunk got a vector
    finally:
        conn.close()


@pytest.mark.integration
def test_reingest_same_file_is_deduped(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    data = make_pdf([["Specialist copay is $40 per visit."]])
    first = ingest_document("policy.pdf", data)
    second = ingest_document("policy-again.pdf", data)  # same bytes, different name

    assert second.doc_id == first.doc_id  # idempotent
    conn = connect_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.integration
def test_failed_extraction_cleans_up_blob_and_leaves_no_indexed_doc(offline_ingest_env, make_pdf, monkeypatch):
    from tara.document_ingestion import ingestion_pipeline

    monkeypatch.setattr(ingestion_pipeline, "extract_text_spans",
                        lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        ingestion_pipeline.ingest_document("policy.pdf", make_pdf([["Specialist copay is $40."]]))

    conn = connect_db()
    try:
        indexed_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status='indexed'").fetchone()[0]
        assert indexed_count == 0
    finally:
        conn.close()
    assert not list(offline_ingest_env.blob_dir.glob("*"))  # orphan blob removed


@pytest.mark.integration
def test_replace_failure_preserves_prior_document(offline_ingest_env, make_pdf, monkeypatch):
    from tara.document_ingestion import ingestion_pipeline

    data = make_pdf([["Specialist copay is $40 per visit."]])
    original = ingestion_pipeline.ingest_document("policy.pdf", data)

    # Re-index the same file, but embedding fails part-way through.
    monkeypatch.setattr(ingestion_pipeline.text_embedder, "embed_texts",
                        lambda texts: (_ for _ in ()).throw(RuntimeError("embed down")))
    with pytest.raises(RuntimeError, match="embed down"):
        ingestion_pipeline.ingest_document("policy.pdf", data, replace=True)

    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        row = conn.execute("SELECT status FROM documents WHERE doc_id=?",
                           (original.doc_id,)).fetchone()
        assert row is not None and row["status"] == "indexed"  # prior version intact
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] > 0  # vectors kept
    finally:
        conn.close()


@pytest.mark.integration
def test_replace_reindexes_same_file(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    data = make_pdf([["Specialist copay is $40 per visit."]])
    first = ingest_document("policy.pdf", data)
    second = ingest_document("policy.pdf", data, replace=True)

    assert second.doc_id != first.doc_id  # re-indexed under a fresh id
    conn = connect_db()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status='indexed'"
        ).fetchone()[0] == 1  # old purged, one indexed doc remains
    finally:
        conn.close()


@pytest.mark.integration
def test_failed_document_is_invisible_to_retrieval(offline_ingest_env, make_pdf, monkeypatch):
    from tara.document_ingestion import ingestion_pipeline
    from tara.semantic_search.chunk_retriever import retrieve_chunks

    # Force a post-commit failure so a doc row exists but ends 'indexing_failed'.
    monkeypatch.setattr(ingestion_pipeline.vector_index, "add_embeddings",
                        lambda conn, items: (_ for _ in ()).throw(RuntimeError("vec down")))
    with pytest.raises(RuntimeError):
        ingestion_pipeline.ingest_document(
            "policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))

    assert retrieve_chunks("specialist copay") == []  # not visible
