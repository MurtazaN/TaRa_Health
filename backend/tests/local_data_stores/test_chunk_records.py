"""chunks-table row operations: batch insert, per-document lookup, and the
chunk+filename join the retriever depends on."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tara.data_models import Chunk, Document
from tara.local_data_stores import chunk_records, document_records
from tara.local_data_stores.db_connection import connect_db


def _insert_document(conn, doc_id: str = "doc1", status: str = "indexed") -> None:
    document_records.insert_document_row(conn, Document(
        doc_id=doc_id, filename=f"{doc_id}.pdf", doc_type="other",
        content_hash=f"H_{doc_id}", status=status, page_count=1,
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))


@pytest.mark.integration
def test_insert_and_lookup_chunk_ids_for_document(offline_ingest_env):
    conn = connect_db()
    try:
        _insert_document(conn)
        chunks = [Chunk(chunk_id=f"doc1:1:{start}", doc_id="doc1", page=1,
                        char_start=start, char_end=start + 5, text="copay")
                  for start in (0, 10)]
        chunk_records.insert_chunk_rows(conn, chunks)
        conn.commit()

        assert chunk_records.chunk_ids_for_document(conn, "doc1") == ["doc1:1:0", "doc1:1:10"]
    finally:
        conn.close()


@pytest.mark.integration
def test_fetch_chunk_with_filename_returns_chunk_and_source(offline_ingest_env):
    conn = connect_db()
    try:
        _insert_document(conn)
        chunk = Chunk(chunk_id="doc1:1:0", doc_id="doc1", page=1,
                      char_start=0, char_end=5, text="copay")
        chunk_records.insert_chunk_rows(conn, [chunk])
        conn.commit()

        chunk_with_source = chunk_records.fetch_chunk_with_filename(conn, "doc1:1:0")
        assert chunk_with_source is not None
        assert chunk_with_source.chunk == chunk
        assert chunk_with_source.source_filename == "doc1.pdf"
        assert chunk_with_source.document_status == "indexed"

        assert chunk_records.fetch_chunk_with_filename(conn, "missing:1:0") is None
    finally:
        conn.close()
