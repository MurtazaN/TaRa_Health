"""Reads and writes the index_meta singleton row — the record of which embedding
model (and dimension) the vector index was built with (design §3.2).

This is what stops a config change from silently corrupting search: the vec0
table bakes its dimension in at creation, so once anything is indexed, a
different embed model/dim is a re-index migration, not a soft switch.
"""
from __future__ import annotations

import sqlite3

from tara.app_errors import IndexMismatchError


def read_index_meta(conn: sqlite3.Connection) -> tuple[str, int] | None:
    """Return the (embed_model, embed_dim) the index was built with, or None."""
    row = conn.execute("SELECT embed_model, embed_dim FROM index_meta WHERE id = 1").fetchone()
    if row is None:
        return None
    return row["embed_model"], row["embed_dim"]


def write_index_meta(conn: sqlite3.Connection, embed_model: str, embed_dim: int,
                     created_at: str) -> None:
    """Persist the embedding model/dim as the singleton index-metadata row."""
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (id, embed_model, embed_dim, created_at) "
        "VALUES (1, ?, ?, ?)",
        (embed_model, embed_dim, created_at),
    )


def ensure_index_meta(conn: sqlite3.Connection, embed_model: str, embed_dim: int,
                      created_at: str) -> None:
    """First index creation records the model/dim; afterwards a config change is a
    hard error (a re-index migration), not a silent corruption."""
    stored_index_meta = read_index_meta(conn)
    if stored_index_meta is None:
        write_index_meta(conn, embed_model, embed_dim, created_at)
        return
    if stored_index_meta != (embed_model, embed_dim):
        raise IndexMismatchError(
            f"Index was built with {stored_index_meta[0]} (dim {stored_index_meta[1]}) "
            f"but config is {embed_model} (dim {embed_dim}). Re-index required."
        )
