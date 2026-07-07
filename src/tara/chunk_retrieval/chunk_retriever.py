"""Retrieve the chunks most relevant to a question.

Phase 1 / Slice 1: unfiltered vector search + an abstention guard. Document-type
inference and post-filtered retrieval (§3.4 steps 2-3) arrive in Slice 6; the
`doc_type_hint` argument is accepted now but not yet used.
"""
from __future__ import annotations

from dataclasses import dataclass

from tara.config import get_settings
from tara.storage import metadata_db, vector_index
from tara.storage.data_models import Chunk
from tara.text_embeddings import text_embedder


@dataclass
class RetrievedChunk:
    chunk: Chunk
    filename: str
    score: float  # cosine similarity in [-1, 1]; higher is more relevant


def _l2_distance_to_cosine_similarity(l2_distance: float) -> float:
    """Convert L2 distance between unit vectors to cosine similarity."""
    return 1.0 - (l2_distance * l2_distance) / 2.0


def _is_index_ready(conn) -> bool:
    """True if the index is usable. Raises if the stored embed model/dim differs
    from config (stale index; §3.2). Returns False if nothing is indexed yet."""
    stored_index_meta = metadata_db.read_index_meta(conn)
    if stored_index_meta is None:
        return False
    settings = get_settings()
    if stored_index_meta != (settings.embed_model, settings.embed_dim):
        raise metadata_db.IndexMismatchError(
            f"Index built with {stored_index_meta[0]} (dim {stored_index_meta[1]}) but config is "
            f"{settings.embed_model} (dim {settings.embed_dim}). Re-index required."
        )
    return True


def retrieve_chunks(question: str, doc_type_hint: str | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    conn = metadata_db.connect_db()
    try:
        vector_index.load_vector_extension(conn)
        if not _is_index_ready(conn):
            return []
        question_embedding = text_embedder.embed_query(question)
        # Unfiltered for now; the doc-type filter arrives in Slice 6.
        nearest_hits = vector_index.find_nearest_chunks(conn, question_embedding, settings.top_k)
        results: list[RetrievedChunk] = []
        for chunk_id, distance in nearest_hits:
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
                score=_l2_distance_to_cosine_similarity(distance),
            ))
    finally:
        conn.close()

    # Abstention guard: weak best hit => treat as unsupported (§3.4).
    if not results or results[0].score < settings.abstain_threshold:
        return []
    return results
