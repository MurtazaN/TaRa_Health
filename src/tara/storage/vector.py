"""Vector index backed by sqlite-vec. One row per chunk, keyed by chunk_id."""
from __future__ import annotations

import sqlite3

import sqlite_vec  # noqa: F401  (loaded as an extension)

from tara.config import get_settings


def _load_vec(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def init_vector_table(conn: sqlite3.Connection) -> None:
    _load_vec(conn)
    dim = get_settings().embed_dim
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
        f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[{dim}])"
    )
    conn.commit()


def add(conn: sqlite3.Connection, chunk_id: str, embedding: list[float]) -> None:
    """Insert one chunk embedding. TODO: batch for ingestion throughput."""
    raise NotImplementedError


def search(conn: sqlite3.Connection, query_vec: list[float], k: int,
           doc_ids: list[str] | None = None) -> list[tuple[str, float]]:
    """Return [(chunk_id, distance), ...]. Optionally restrict to doc_ids
    (used for document-type-filtered retrieval). TODO: implement KNN query."""
    raise NotImplementedError
