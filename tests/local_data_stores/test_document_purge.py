"""Document purge: complete deletion across all three stores, idempotency, and
the orphan-blob sweep that keeps 'delete is complete' true after a crash."""
from __future__ import annotations

import pytest

from tara.local_data_stores import vector_index
from tara.local_data_stores.db_connection import connect_db
from tara.local_data_stores.document_purge import purge_document, reconcile_orphan_blobs


@pytest.mark.integration
def test_purge_removes_rows_vectors_and_blob(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    document = ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    blob_dir = offline_ingest_env.blob_dir
    assert list(blob_dir.glob(f"{document.doc_id}.*"))  # blob present

    assert purge_document(document.doc_id) is True

    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)  # vec0 is per-connection
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 0
    finally:
        conn.close()
    assert not list(blob_dir.glob(f"{document.doc_id}.*"))  # blob gone
    assert purge_document(document.doc_id) is False  # idempotent no-op


@pytest.mark.integration
def test_reconcile_removes_orphan_blobs_only(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    document = ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    orphan_blob = offline_ingest_env.blob_dir / "deadbeefdeadbeef.pdf"
    orphan_blob.write_bytes(b"orphaned phi")

    removed_doc_ids = reconcile_orphan_blobs()

    assert "deadbeefdeadbeef" in removed_doc_ids
    assert not orphan_blob.exists()
    assert list(offline_ingest_env.blob_dir.glob(f"{document.doc_id}.*"))  # real blob kept
