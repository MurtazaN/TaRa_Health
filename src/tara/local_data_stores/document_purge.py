"""Deletes a document completely: its vectors, chunk rows, document row, and the
original uploaded file. Implements the "delete is real and complete" contract of
design §3.2/§7.

Deletion order is the one invariant this module protects. No foreign key reaches
the vec_chunks table, so vector rows never cascade — they are deleted explicitly,
and first. A crash mid-purge can therefore only leave rows that a retry removes,
never orphaned vectors that keep surfacing search hits for a deleted document.
"""
from __future__ import annotations

from tara.config import get_settings
from tara.local_data_stores import blob_store, chunk_records, document_records, vector_index
from tara.local_data_stores.db_connection import connect_db


def purge_document(doc_id: str) -> bool:
    """Delete every stored trace of one document. Returns False if the document
    did not exist. Idempotent: purging an already-absent document is a no-op."""
    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        chunk_ids = chunk_records.chunk_ids_for_document(conn, doc_id)
        document_existed = document_records.document_row_exists(conn, doc_id)

        # Vectors first: nothing cascades to vec_chunks, so this is the only
        # deletion that would dangle if the purge stopped part-way.
        vector_index.delete_embeddings(conn, chunk_ids)
        # Deleting the document row cascades to its chunk rows (foreign_keys ON).
        document_records.delete_document_row(conn, doc_id)
        conn.commit()
    finally:
        conn.close()

    # The file on disk is outside the transaction above. If the process dies
    # before this line, reconcile_orphan_blobs() removes the leftover file on
    # the next startup, so deletion still completes.
    blob_store.delete_blob(doc_id)
    # TODO (Slice 2+): redact this document's rows in the `queries` audit log
    #       once answering starts writing it (§7 retention policy).
    return document_existed


def reconcile_orphan_blobs() -> list[str]:
    """Delete blob files with no owning `documents` row and return their doc_ids.

    Makes "delete is complete" (§7) self-healing: if the process is killed after a
    purge/failed-ingest commits but before the blob is unlinked, the leftover PHI
    file is swept on the next startup. Idempotent."""
    conn = connect_db()
    try:
        known_doc_ids = document_records.all_doc_ids(conn)
    finally:
        conn.close()

    removed_doc_ids: list[str] = []
    for blob_path in get_settings().blob_dir.glob("*"):
        if not blob_path.is_file():
            continue
        doc_id = blob_path.stem
        if doc_id not in known_doc_ids:
            blob_path.unlink(missing_ok=True)
            removed_doc_ids.append(doc_id)
    return removed_doc_ids
