"""Complete, buildable document deletion (design §3.2, §7).

Because vec_chunks has no foreign-key link to chunks, vector rows must be deleted
explicitly. Ordering matters: remove vectors first, then the document row (whose
ON DELETE CASCADE removes its chunks), then the blob — so a mid-way failure never
leaves a "document gone but vectors remain" state.
"""
from __future__ import annotations

from tara.storage import blobs, vector
from tara.storage.db import connect


def purge_document(doc_id: str) -> bool:
    """Delete a document's vectors, chunks, row, and blob. Returns False if the
    document did not exist. Idempotent."""
    conn = connect()
    try:
        vector.load(conn)
        chunk_ids = [
            row["chunk_id"]
            for row in conn.execute("SELECT chunk_id FROM chunks WHERE doc_id = ?", (doc_id,))
        ]
        exists = conn.execute(
            "SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone() is not None

        vector.delete(conn, chunk_ids)                 # 1) vectors (no cascade)
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))  # 2) row -> cascades chunks
        conn.commit()
    finally:
        conn.close()

    blobs.delete(doc_id)  # 3) blob on disk
    # NOTE: queries-row redaction (§7) is deferred until the audit log is written
    # (Slice 2+); the queries table has no doc linkage yet.
    return exists


def reconcile_orphan_blobs() -> list[str]:
    """Delete blob files with no owning `documents` row and return their doc_ids.

    Makes "delete is complete" (§7) self-healing: if the process is killed after a
    purge/failed-ingest commits but before the blob is unlinked, the leftover PHI
    file is swept on the next startup. Idempotent."""
    from tara.config import get_settings

    conn = connect()
    try:
        known = {row["doc_id"] for row in conn.execute("SELECT doc_id FROM documents")}
    finally:
        conn.close()

    removed: list[str] = []
    for path in get_settings().blob_dir.glob("*"):
        if not path.is_file():
            continue
        doc_id = path.stem
        if doc_id not in known:
            path.unlink(missing_ok=True)
            removed.append(doc_id)
    return removed
