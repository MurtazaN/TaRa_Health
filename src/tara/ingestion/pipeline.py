"""Ingests one uploaded document: bytes in -> stored, chunked, embedded, and
indexed locally. `ingest_document()` returns the resulting Document record.

    validate -> dedup -> save blob -> extract text spans -> chunk -> embed
             -> [txn: write documents + chunks] -> write vectors -> status=indexed

Transactional + idempotent per §3.1f/§3.1g. Two guarantees worth calling out:
  * The failure-prone steps (parse + network embedding) run BEFORE any store
    mutation, so a failure never destroys an existing document — in particular a
    `replace=True` re-index only purges the prior version once the new one is
    validated (avoids unrecoverable data loss).
  * A partial-unique index on content_hash makes the dedup check race-safe: a lost
    race surfaces as IntegrityError and returns the winning document.
Doc-type classification is deferred to Slice 6 (doc_type='other').
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone

from tara.config import get_settings
from tara.embeddings import text_embedder
from tara.ingestion.chunk import chunk_spans
from tara.ingestion.extract import extract_text_spans
from tara.storage import blobs, db, vector
from tara.storage.models import Document
from tara.storage.purge import purge_document
from tara.validation import validate_upload


class IngestionError(RuntimeError):
    """Ingestion failed after validation (e.g. extraction produced no text)."""


def _document_from_row(row: sqlite3.Row) -> Document:
    return Document(
        doc_id=row["doc_id"],
        filename=row["filename"],
        doc_type=row["doc_type"],
        content_hash=row["content_hash"],
        status=row["status"],
        page_count=row["page_count"],
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
    )


def _find_indexed_document_by_hash(conn: sqlite3.Connection, content_hash: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM documents WHERE content_hash = ? AND status = 'indexed'",
        (content_hash,),
    ).fetchone()


def ingest_document(filename: str, data: bytes, *, replace: bool = False) -> Document:
    settings = get_settings()
    validate_upload(filename, len(data))
    content_hash = hashlib.sha256(data).hexdigest()

    conn = db.connect_db()
    try:
        vector.load_vector_extension(conn)
        existing = _find_indexed_document_by_hash(conn, content_hash)
        if existing is not None and not replace:
            return _document_from_row(existing)  # idempotent: no duplicate (§3.1f)

        now = datetime.now(timezone.utc)
        db.ensure_index_meta(conn, settings.embed_model, settings.embed_dim, now.isoformat())
        vector.init_vector_table(conn)  # idempotent; commits
        conn.commit()

        doc_id = uuid.uuid4().hex
        path = blobs.save_blob(doc_id, filename, data)
        is_doc_committed = False
        try:
            # Failure-prone work first, before mutating any store (see module docstring).
            spans = extract_text_spans(path)
            if not spans:
                raise IngestionError(f"No extractable text in '{filename}'.")
            chunks = chunk_spans(doc_id, spans)
            vectors = text_embedder.embed_texts([c.text for c in chunks])  # asserts count
            page_count = max(s.page for s in spans)

            # Only now is it safe to destroy the prior version (§3.1f replace path).
            if replace and existing is not None:
                purge_document(existing["doc_id"])

            # One transaction: documents row + all chunks rows (status='indexing').
            conn.execute(
                "INSERT INTO documents (doc_id, filename, doc_type, content_hash, status, "
                "page_count, uploaded_at) VALUES (?, ?, 'other', ?, 'indexing', ?, ?)",
                (doc_id, filename, content_hash, page_count, now.isoformat()),
            )
            conn.executemany(
                "INSERT INTO chunks (chunk_id, doc_id, page, char_start, char_end, text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(c.chunk_id, c.doc_id, c.page, c.char_start, c.char_end, c.text) for c in chunks],
            )
            conn.commit()
            is_doc_committed = True

            vector.add_embeddings(conn, list(zip((c.chunk_id for c in chunks), vectors)))
            try:
                conn.execute("UPDATE documents SET status = 'indexed' WHERE doc_id = ?", (doc_id,))
                conn.commit()
            except sqlite3.IntegrityError:
                # Lost the dedup race: another ingest indexed this content first.
                conn.rollback()
                purge_document(doc_id)
                winner = _find_indexed_document_by_hash(conn, content_hash)
                if winner is None:
                    raise
                return _document_from_row(winner)

            return Document(
                doc_id=doc_id, filename=filename, doc_type="other",
                content_hash=content_hash, status="indexed",
                page_count=page_count, uploaded_at=now,
            )
        except Exception:
            _clean_up_failed_ingest(conn, doc_id, is_doc_committed)
            raise
    finally:
        conn.close()


def _clean_up_failed_ingest(conn: sqlite3.Connection, doc_id: str, is_doc_committed: bool) -> None:
    """Best-effort recovery so a failed ingest leaves no inconsistent state (§3.1g).
    A committed doc is marked 'indexing_failed' (invisible to retrieval) with its
    partial vectors removed; the orphan blob is always deleted. Never masks the
    original error."""
    try:
        conn.rollback()
        chunk_ids = [
            row["chunk_id"]
            for row in conn.execute("SELECT chunk_id FROM chunks WHERE doc_id = ?", (doc_id,))
        ]
        vector.delete_embeddings(conn, chunk_ids)
        if is_doc_committed:
            conn.execute(
                "UPDATE documents SET status = 'indexing_failed' WHERE doc_id = ?", (doc_id,)
            )
        conn.commit()
    except Exception:
        pass
    try:
        blobs.delete_blob(doc_id)
    except Exception:
        pass
