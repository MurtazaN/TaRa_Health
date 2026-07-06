"""SQLite connection + relational schema (design §3.2, §4).

Uses SQLCipher for at-rest encryption when a db_key is configured
(see config.Settings.db_key); falls back to plain sqlite3 for early development.
The vector table (vec_chunks) lives in storage.vector — it needs the sqlite-vec
extension loaded, so it is created separately against the same file.
"""
from __future__ import annotations

import sqlite3

from tara.config import get_settings


def connect() -> sqlite3.Connection:
    settings = get_settings()
    # The DB write needs its parent dir; creating it here is idempotent and local
    # (the cached settings factory stays side-effect free — see config.ensure_dirs).
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # TODO: when settings.db_key is set, open via pysqlcipher3 and run
    #       `PRAGMA key = ?` before any other statement. Until then, plain sqlite3.
    # check_same_thread=False: FastAPI runs sync handlers in a threadpool (§3.2).
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # foreign_keys is per-connection in SQLite and OFF by default; declared
    # ON DELETE CASCADE only fires when this is ON (§3.2).
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
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


def init_schema() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        # The vector virtual table is created by storage.vector (needs the extension loaded).
        conn.commit()
    finally:
        conn.close()


class IndexMismatchError(RuntimeError):
    """Raised when the configured embedding model/dim differs from what the index
    was built with (§3.2) — serving queries would return garbage distances."""


def read_index_meta(conn: sqlite3.Connection) -> tuple[str, int] | None:
    """Return the (embed_model, embed_dim) the index was built with, or None."""
    row = conn.execute("SELECT embed_model, embed_dim FROM index_meta WHERE id = 1").fetchone()
    if row is None:
        return None
    return row["embed_model"], row["embed_dim"]


def write_index_meta(conn: sqlite3.Connection, embed_model: str, embed_dim: int,
                     created_at: str) -> None:
    """Persist the embedding model/dim as the singleton index-metadata row (§3.2)."""
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (id, embed_model, embed_dim, created_at) "
        "VALUES (1, ?, ?, ?)",
        (embed_model, embed_dim, created_at),
    )


def ensure_index_meta(conn: sqlite3.Connection, embed_model: str, embed_dim: int,
                      created_at: str) -> None:
    """First index creation records the model/dim; afterwards a config change is a
    hard error (a re-index migration), not a silent corruption (§3.2)."""
    stored = read_index_meta(conn)
    if stored is None:
        write_index_meta(conn, embed_model, embed_dim, created_at)
        return
    if stored != (embed_model, embed_dim):
        raise IndexMismatchError(
            f"Index was built with {stored[0]} (dim {stored[1]}) but config is "
            f"{embed_model} (dim {embed_dim}). Re-index required."
        )
