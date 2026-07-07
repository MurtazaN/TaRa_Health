"""Row-level operations on the `documents` table — the only module that writes
or reads document rows, so the schema's column names live in exactly one place.

Functions take an open connection and never commit; the caller owns the
transaction (the ingestion pipeline commits documents + chunks atomically, §3.1g).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from tara.data_models import DocStatus, Document


def document_from_row(row: sqlite3.Row) -> Document:
    """Build a Document dataclass from a `documents` table row."""
    return Document(
        doc_id=row["doc_id"],
        filename=row["filename"],
        doc_type=row["doc_type"],
        content_hash=row["content_hash"],
        status=row["status"],
        page_count=row["page_count"],
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
    )


def insert_document_row(conn: sqlite3.Connection, document: Document) -> None:
    """Insert one document row exactly as the dataclass describes it."""
    conn.execute(
        "INSERT INTO documents (doc_id, filename, doc_type, content_hash, status, "
        "page_count, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (document.doc_id, document.filename, document.doc_type, document.content_hash,
         document.status, document.page_count, document.uploaded_at.isoformat()),
    )


def find_indexed_document_by_hash(conn: sqlite3.Connection,
                                  content_hash: str) -> Document | None:
    """Return the indexed document with this content hash, or None.
    Only status='indexed' counts — in-flight/failed attempts don't dedup (§3.1f)."""
    row = conn.execute(
        "SELECT * FROM documents WHERE content_hash = ? AND status = 'indexed'",
        (content_hash,),
    ).fetchone()
    return document_from_row(row) if row is not None else None


def mark_document_status(conn: sqlite3.Connection, doc_id: str,
                         status: DocStatus) -> None:
    """Set a document's lifecycle status (indexing | indexed | indexing_failed)."""
    conn.execute("UPDATE documents SET status = ? WHERE doc_id = ?", (status, doc_id))


def document_row_exists(conn: sqlite3.Connection, doc_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone() is not None


def delete_document_row(conn: sqlite3.Connection, doc_id: str) -> None:
    """Delete one document row. Its chunk rows go with it via ON DELETE CASCADE;
    vec_chunks rows do NOT — the caller must delete those explicitly (§3.2)."""
    conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))


def all_doc_ids(conn: sqlite3.Connection) -> set[str]:
    """Return every doc_id with a `documents` row, regardless of status."""
    return {row["doc_id"] for row in conn.execute("SELECT doc_id FROM documents")}
