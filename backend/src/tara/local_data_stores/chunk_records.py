"""Row-level operations on the `chunks` table — the only module that writes or
reads chunk rows, so the schema's column names live in exactly one place.

Functions take an open connection and never commit; the caller owns the
transaction (the ingestion pipeline commits documents + chunks atomically, §3.1g).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from tara.data_models import Chunk


@dataclass
class ChunkWithSource:
    """A stored chunk joined with its owning document's display facts."""
    chunk: Chunk
    source_filename: str
    document_status: str  # retrieval must skip anything not 'indexed' (§3.1g)


def insert_chunk_rows(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
    """Insert all chunk rows for a document in one batch."""
    conn.executemany(
        "INSERT INTO chunks (chunk_id, doc_id, page, char_start, char_end, text) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(chunk.chunk_id, chunk.doc_id, chunk.page, chunk.char_start,
          chunk.char_end, chunk.text) for chunk in chunks],
    )


def chunk_ids_for_document(conn: sqlite3.Connection, doc_id: str) -> list[str]:
    """Return the chunk_ids belonging to one document (used to delete their
    vec_chunks rows, which have no cascade; §3.2)."""
    return [
        row["chunk_id"]
        for row in conn.execute("SELECT chunk_id FROM chunks WHERE doc_id = ?", (doc_id,))
    ]


def fetch_chunk_with_filename(conn: sqlite3.Connection,
                              chunk_id: str) -> ChunkWithSource | None:
    """Return one chunk plus its document's filename and status, or None."""
    row = conn.execute(
        "SELECT c.doc_id, c.page, c.char_start, c.char_end, c.text, d.filename, d.status "
        "FROM chunks c JOIN documents d ON c.doc_id = d.doc_id WHERE c.chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if row is None:
        return None
    return ChunkWithSource(
        chunk=Chunk(
            chunk_id=chunk_id, doc_id=row["doc_id"], page=row["page"],
            char_start=row["char_start"], char_end=row["char_end"], text=row["text"],
        ),
        source_filename=row["filename"],
        document_status=row["status"],
    )
