"""documents-table row operations: insert/find/mark/delete round-trips."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tara.data_models import Document
from tara.local_data_stores import document_records
from tara.local_data_stores.db_connection import connect_db


def _make_document(doc_id: str = "doc1", content_hash: str = "HASH1",
                   status: str = "indexing") -> Document:
    return Document(doc_id=doc_id, filename="policy.pdf", doc_type="other",
                    content_hash=content_hash, status=status, page_count=2,
                    uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.mark.integration
def test_insert_and_find_indexed_by_hash_roundtrip(offline_ingest_env):
    conn = connect_db()
    try:
        document = _make_document(status="indexed")
        document_records.insert_document_row(conn, document)
        conn.commit()

        found = document_records.find_indexed_document_by_hash(conn, "HASH1")
        assert found == document  # full round-trip, incl. parsed datetime
    finally:
        conn.close()


@pytest.mark.integration
def test_find_indexed_by_hash_ignores_unindexed_documents(offline_ingest_env):
    conn = connect_db()
    try:
        document_records.insert_document_row(conn, _make_document(status="indexing"))
        conn.commit()
        assert document_records.find_indexed_document_by_hash(conn, "HASH1") is None

        document_records.mark_document_status(conn, "doc1", "indexed")
        conn.commit()
        assert document_records.find_indexed_document_by_hash(conn, "HASH1") is not None
    finally:
        conn.close()


@pytest.mark.integration
def test_exists_delete_and_all_doc_ids(offline_ingest_env):
    conn = connect_db()
    try:
        document_records.insert_document_row(conn, _make_document("docA", "H_A"))
        document_records.insert_document_row(conn, _make_document("docB", "H_B"))
        conn.commit()

        assert document_records.document_row_exists(conn, "docA") is True
        assert document_records.all_doc_ids(conn) == {"docA", "docB"}

        document_records.delete_document_row(conn, "docA")
        conn.commit()
        assert document_records.document_row_exists(conn, "docA") is False
        assert document_records.all_doc_ids(conn) == {"docB"}
    finally:
        conn.close()
