"""Vector index backed by sqlite-vec. One row per chunk, keyed by chunk_id.

Callers must `load_vector_extension(conn)` once on a connection before using the
add/search/delete functions (init_vector_table does this itself). Distances are
L2; because embeddings are unit-normalized (see semantic_search.text_embedder),
L2 distance is monotonic with cosine similarity, so nearest-by-distance ==
most-similar.
"""
from __future__ import annotations

import sqlite3

import sqlite_vec
from sqlite_vec import serialize_float32

from tara.config import get_settings

# sqlite-vec can't filter on non-vector columns inside the KNN query, so
# document-type filtering is done by over-fetching then post-filtering (§3.4).
_POSTFILTER_OVERFETCH_MULTIPLIER = 5


def load_vector_extension(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension on this connection (idempotent, per-connection)."""
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)


def init_vector_table(conn: sqlite3.Connection) -> None:
    load_vector_extension(conn)
    embedding_dim = get_settings().embed_dim
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
        f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[{embedding_dim}])"
    )
    conn.commit()


def add_embedding(conn: sqlite3.Connection, chunk_id: str, embedding: list[float]) -> None:
    conn.execute(
        "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, serialize_float32(embedding)),
    )


def add_embeddings(conn: sqlite3.Connection,
                   chunk_embedding_pairs: list[tuple[str, list[float]]]) -> None:
    """Batch insert (chunk_id, embedding) pairs for ingestion throughput."""
    conn.executemany(
        "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        [(chunk_id, serialize_float32(embedding))
         for chunk_id, embedding in chunk_embedding_pairs],
    )


def delete_embeddings(conn: sqlite3.Connection, chunk_ids: list[str]) -> None:
    """Delete vector rows by chunk_id (no FK to chunks, so this is explicit; §3.2)."""
    if not chunk_ids:
        return
    placeholders = ",".join("?" * len(chunk_ids))
    conn.execute(f"DELETE FROM vec_chunks WHERE chunk_id IN ({placeholders})", chunk_ids)


def find_nearest_chunks(conn: sqlite3.Connection, query_embedding: list[float],
                        max_results: int,
                        doc_ids: list[str] | None = None) -> list[tuple[str, float]]:
    """Return the max_results nearest [(chunk_id, distance), ...], ascending by distance.

    When `doc_ids` is given, over-fetch and keep the first max_results whose
    owning document is in the allowed set (post-filtering, §3.4).
    """
    if max_results <= 0:
        return []
    fetch_count = (max_results * _POSTFILTER_OVERFETCH_MULTIPLIER
                   if doc_ids is not None else max_results)
    rows = conn.execute(
        "SELECT chunk_id, distance FROM vec_chunks "
        "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (serialize_float32(query_embedding), fetch_count),
    ).fetchall()
    nearest_hits = [(row["chunk_id"], row["distance"]) for row in rows]
    if doc_ids is None:
        return nearest_hits[:max_results]

    allowed_doc_ids = set(doc_ids)
    hit_chunk_ids = [chunk_id for chunk_id, _ in nearest_hits]
    placeholders = ",".join("?" * len(hit_chunk_ids))
    doc_id_by_chunk_id = {
        row["chunk_id"]: row["doc_id"]
        for row in conn.execute(
            f"SELECT chunk_id, doc_id FROM chunks WHERE chunk_id IN ({placeholders})",
            hit_chunk_ids,
        )
    } if hit_chunk_ids else {}
    allowed_hits = [
        (chunk_id, distance) for chunk_id, distance in nearest_hits
        if doc_id_by_chunk_id.get(chunk_id) in allowed_doc_ids
    ]
    return allowed_hits[:max_results]
