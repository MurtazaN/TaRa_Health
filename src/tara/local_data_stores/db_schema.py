"""Defines and creates the metadata database's relational schema
(documents, chunks, index_meta, queries — design §3.2, §4).

The vec_chunks virtual table is NOT here: it lives in
local_data_stores.vector_index because it needs the sqlite-vec extension loaded,
so it is created separately against the same database file.
"""
from __future__ import annotations

from tara.local_data_stores.db_connection import connect_db

METADATA_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    doc_type     TEXT NOT NULL DEFAULT 'other',
    content_hash TEXT NOT NULL DEFAULT '',        -- re-ingest dedup (§3.1f)
    status       TEXT NOT NULL DEFAULT 'indexing', -- indexing | indexed | indexing_failed (§3.1g)
    page_count   INTEGER NOT NULL DEFAULT 0,
    uploaded_at  TEXT NOT NULL
);

-- Fast dedup lookups by content hash (§3.1f).
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);

-- At most one *indexed* document per content hash: closes the check-then-insert
-- race that could otherwise persist duplicate indexed docs (§3.1f). Scoped to
-- status='indexed' so a prior failed/in-flight attempt never blocks a retry.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_hash_unique
    ON documents(content_hash) WHERE status = 'indexed' AND content_hash != '';

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    page        INTEGER NOT NULL,
    char_start  INTEGER NOT NULL,
    char_end    INTEGER NOT NULL,
    text        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

-- Guards embedding model/dimension integrity (§3.2). Singleton: the CHECK(id=1)
-- forces exactly one row, so the drift check compares against an unambiguous
-- stored value. Writers use `INSERT OR REPLACE INTO index_meta (id, ...) VALUES (1, ...)`.
CREATE TABLE IF NOT EXISTS index_meta (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    embed_model TEXT NOT NULL,
    embed_dim   INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

-- Audit / eval log; written on every answered query (§4, §7).
CREATE TABLE IF NOT EXISTS queries (
    query_id            TEXT PRIMARY KEY,
    question            TEXT NOT NULL,
    retrieved_chunk_ids TEXT,          -- JSON array; needed by the §8 retrieval eval
    answer              TEXT,
    citations           TEXT,          -- JSON
    safety_flag         TEXT NOT NULL DEFAULT 'none',   -- none | emergency
    model_route         TEXT,          -- local | hosted (PHI egress audit, §7)
    created_at          TEXT NOT NULL
);
"""


def init_db_schema() -> None:
    """Create all relational tables and indexes. Idempotent; run once at startup."""
    conn = connect_db()
    try:
        conn.executescript(METADATA_DB_SCHEMA)
        conn.commit()
    finally:
        conn.close()
