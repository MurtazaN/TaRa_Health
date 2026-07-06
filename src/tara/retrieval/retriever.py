"""Retrieve the chunks most relevant to a question.

Phase 1 / Slice 1: unfiltered vector search + an abstention guard. Document-type
inference and post-filtered retrieval (§3.4 steps 2-3) arrive in Slice 6; the
`doc_type_hint` argument is accepted now but not yet used.
"""
from __future__ import annotations

from dataclasses import dataclass

from tara.config import get_settings
from tara.embeddings import embedder
from tara.storage import db, vector
from tara.storage.models import Chunk


@dataclass
class RetrievedChunk:
    chunk: Chunk
    filename: str
    score: float  # cosine similarity in [-1, 1]; higher is more relevant


def _similarity(l2_distance: float) -> float:
    """Convert L2 distance between unit vectors to cosine similarity."""
    return 1.0 - (l2_distance * l2_distance) / 2.0


def _require_fresh_index(conn) -> bool:
    """True if the index is usable. Raises if the stored embed model/dim differs
    from config (stale index; §3.2). Returns False if nothing is indexed yet."""
    stored = db.read_index_meta(conn)
    if stored is None:
        return False
    settings = get_settings()
    if stored != (settings.embed_model, settings.embed_dim):
        raise db.IndexMismatchError(
            f"Index built with {stored[0]} (dim {stored[1]}) but config is "
            f"{settings.embed_model} (dim {settings.embed_dim}). Re-index required."
        )
    return True


def retrieve(question: str, doc_type_hint: str | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    conn = db.connect()
    try:
        vector.load(conn)
        if not _require_fresh_index(conn):
            return []
        qvec = embedder.embed_query(question)
        hits = vector.search(conn, qvec, settings.top_k)  # doc-type filter: Slice 6
        results: list[RetrievedChunk] = []
        for chunk_id, distance in hits:
            row = conn.execute(
                "SELECT c.doc_id, c.page, c.char_start, c.char_end, c.text, d.filename, d.status "
                "FROM chunks c JOIN documents d ON c.doc_id = d.doc_id WHERE c.chunk_id = ?",
                (chunk_id,),
            ).fetchone()
            if row is None or row["status"] != "indexed":
                continue  # only indexed documents are visible to retrieval (§3.1g)
            results.append(RetrievedChunk(
                chunk=Chunk(
                    chunk_id=chunk_id, doc_id=row["doc_id"], page=row["page"],
                    char_start=row["char_start"], char_end=row["char_end"], text=row["text"],
                ),
                filename=row["filename"],
                score=_similarity(distance),
            ))
    finally:
        conn.close()

    # Abstention guard: weak best hit => treat as unsupported (§3.4).
    if not results or results[0].score < settings.abstain_threshold:
        return []
    return results
