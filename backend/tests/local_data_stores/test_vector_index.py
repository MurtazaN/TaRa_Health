"""sqlite-vec KNN wrapper: nearest-chunk search, doc_id post-filtering, and
explicit deletes (no cascade reaches vec_chunks)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tara.data_models import Chunk, Document
from tara.local_data_stores import chunk_records, document_records, vector_index
from tara.local_data_stores.db_connection import connect_db
from tests.conftest import fake_embed_one


def _index_one_chunk(conn, doc_id: str, dim: int) -> str:
    document_records.insert_document_row(conn, Document(
        doc_id=doc_id, filename=f"{doc_id}.pdf", doc_type="other",
        content_hash=f"H_{doc_id}", status="indexed", page_count=1,
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    chunk_id = f"{doc_id}:1:0"
    chunk_records.insert_chunk_rows(conn, [Chunk(
        chunk_id=chunk_id, doc_id=doc_id, page=1, char_start=0, char_end=5, text="copay")])
    vector_index.add_embedding(conn, chunk_id, fake_embed_one("copay", dim))
    return chunk_id


@pytest.mark.integration
def test_find_nearest_chunks_post_filters_by_doc_id(offline_ingest_env):
    dim = offline_ingest_env.embed_dim
    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        for doc_id in ("docA", "docB"):
            _index_one_chunk(conn, doc_id, dim)
        conn.commit()

        question_embedding = fake_embed_one("copay", dim)
        allowed_hits = vector_index.find_nearest_chunks(
            conn, question_embedding, max_results=5, doc_ids=["docA"])
        assert {chunk_id for chunk_id, _ in allowed_hits} == {"docA:1:0"}  # docB filtered out
    finally:
        conn.close()


@pytest.mark.integration
def test_find_nearest_chunks_returns_empty_for_nonpositive_max_results(offline_ingest_env):
    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        assert vector_index.find_nearest_chunks(conn, [0.0], max_results=0) == []
    finally:
        conn.close()


@pytest.mark.integration
def test_delete_embeddings_removes_vector_rows(offline_ingest_env):
    dim = offline_ingest_env.embed_dim
    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        chunk_id = _index_one_chunk(conn, "docA", dim)
        conn.commit()

        vector_index.delete_embeddings(conn, [chunk_id])
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 0
    finally:
        conn.close()
