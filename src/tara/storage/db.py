"""SQLite connection + schema. Uses SQLCipher for at-rest encryption when a
db_key is configured (see config.Settings.db_key); falls back to plain sqlite3
for early development.
"""
from __future__ import annotations

import sqlite3

from tara.config import get_settings


def connect() -> sqlite3.Connection:
    settings = get_settings()
    # TODO: when settings.db_key is set, open via pysqlcipher3 and run
    #       `PRAGMA key = ?` before any other statement. Until then, plain sqlite3.
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    doc_type    TEXT NOT NULL DEFAULT 'other',
    page_count  INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    page        INTEGER NOT NULL,
    char_start  INTEGER NOT NULL,
    char_end    INTEGER NOT NULL,
    text        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

-- Optional audit log for the eval harness / user transparency.
CREATE TABLE IF NOT EXISTS queries (
    query_id    TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    answer      TEXT,
    citations   TEXT,          -- JSON
    safety_flag TEXT NOT NULL DEFAULT 'none',
    created_at  TEXT NOT NULL
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
