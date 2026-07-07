"""Vector index backed by sqlite-vec. One row per chunk, keyed by chunk_id.

Callers must `load_vector_extension(conn)` once on a connection before using the
add/search/delete functions (init_vector_table does this itself). Distances are
L2; because embeddings are unit-normalized (see embeddings.text_embedder), L2 distance
is monotonic with cosine similarity, so nearest-by-distance == most-similar.
"""
from __future__ import annotations

import sqlite3

import sqlite_vec
from sqlite_vec import serialize_float32

from tara.config import get_settings

# sqlite-vec can't filter on non-vector columns inside the KNN query, so
# document-type filtering is done by over-fetching then post-filtering (§3.4).
_POSTFILTER_OVERFETCH = 5


def load_vector_extension(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension on this connection (idempotent, per-connection)."""
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)


def init_vector_table(conn: sqlite3.Connection) -> None:
    load_vector_extension(conn)
    dim = get_settings().embed_dim
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
        f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[{dim}])"
    )
    conn.commit()


def add_embedding(conn: sqlite3.Connection, chunk_id: str, embedding: list[float]) -> None:
    conn.execute(
        "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, serialize_float32(embedding)),
    )


def add_embeddings(conn: sqlite3.Connection, items: list[tuple[str, list[float]]]) -> None:
    """Batch insert (chunk_id, embedding) pairs for ingestion throughput."""
    conn.executemany(
        "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        [(cid, serialize_float32(vec)) for cid, vec in items],
    )


def delete_embeddings(conn: sqlite3.Connection, chunk_ids: list[str]) -> None:
    """Delete vector rows by chunk_id (no FK to chunks, so this is explicit; §3.2)."""
    if not chunk_ids:
        return
    placeholders = ",".join("?" * len(chunk_ids))
    conn.execute(f"DELETE FROM vec_chunks WHERE chunk_id IN ({placeholders})", chunk_ids)


def find_nearest_chunks(conn: sqlite3.Connection, query_vec: list[float], k: int,
           doc_ids: list[str] | None = None) -> list[tuple[str, float]]:
    """Return the k nearest [(chunk_id, distance), ...], ascending by distance.

    When `doc_ids` is given, over-fetch and keep the first k whose owning document
    is in the allowed set (post-filtering, §3.4).
    """
    if k <= 0:
        return []
    fetch = k * _POSTFILTER_OVERFETCH if doc_ids is not None else k
    rows = conn.execute(
        "SELECT chunk_id, distance FROM vec_chunks "
        "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (serialize_float32(query_vec), fetch),
    ).fetchall()
    hits = [(row["chunk_id"], row["distance"]) for row in rows]
    if doc_ids is None:
        return hits[:k]

    allowed = set(doc_ids)
    ids = [cid for cid, _ in hits]
    placeholders = ",".join("?" * len(ids))
    owner = {
        row["chunk_id"]: row["doc_id"]
        for row in conn.execute(
            f"SELECT chunk_id, doc_id FROM chunks WHERE chunk_id IN ({placeholders})", ids
        )
    } if ids else {}
    filtered = [(cid, dist) for cid, dist in hits if owner.get(cid) in allowed]
    return filtered[:k]
