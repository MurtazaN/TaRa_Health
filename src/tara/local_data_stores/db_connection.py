"""Opens connections to the on-device metadata database.

Every relational read/write in the app goes through a connection from
`connect_db()`; the record modules (document_records, chunk_records,
embedding_index_meta) operate on a connection the caller passes in, so one
request can span several operations in a single transaction.
"""
from __future__ import annotations

import sqlite3

from tara.config import get_settings


def connect_db() -> sqlite3.Connection:
    """Open a connection to the on-device metadata database, ready for use
    (row access by column name, foreign keys ON, safe across threads).

    Also creates the database's parent directory if missing — idempotent, and
    kept here so the cached settings factory stays side-effect free (see
    config.ensure_data_dirs).
    """
    settings = get_settings()

    # Owner-only, same as config.ensure_data_dirs: this directory holds PHI.
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # TODO: when settings.db_key is set, open via pysqlcipher3 and run
    #       `PRAGMA key = ?` before any other statement. Until then, plain sqlite3.
    # check_same_thread=False: FastAPI runs sync handlers in a threadpool (§3.2).
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # foreign_keys is per-connection in SQLite and OFF by default; declared
    # ON DELETE CASCADE only fires when this is ON (§3.2).
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
