"""Retrieve the chunks most relevant to a question.

Phase 1 / Slice 1: unfiltered vector search + an abstention guard. Document-type
inference and post-filtered retrieval (§3.4 steps 2-3) arrive in Slice 6; the
`doc_type_hint` argument is accepted now but not yet used.
"""
from __future__ import annotations

from dataclasses import dataclass

from tara.app_errors import IndexMismatchError
from tara.config import get_settings
from tara.data_models import Chunk
from tara.execution_tracing.span_emitter import record_span_attribute, traced_span
from tara.local_data_stores import chunk_records, embedding_index_meta, vector_index
from tara.local_data_stores.db_connection import connect_db
from tara.semantic_search import text_embedder


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
    stored_index_meta = embedding_index_meta.read_index_meta(conn)
    if stored_index_meta is None:
        return False
    settings = get_settings()
    if stored_index_meta != (settings.embed_model, settings.embed_dim):
        raise IndexMismatchError(
            f"Index built with {stored_index_meta[0]} (dim {stored_index_meta[1]}) but config is "
            f"{settings.embed_model} (dim {settings.embed_dim}). Re-index required."
        )
    return True


def retrieve_chunks(question: str, doc_type_hint: str | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    with traced_span("retrieve_chunks", top_k=settings.top_k) as retrieval_span:
        conn = connect_db()
        try:
            vector_index.load_vector_extension(conn)
            if not _is_index_ready(conn):
                # Nothing indexed yet also returns [], so record `abstained` here
                # too — "retrieval returned nothing" must be one queryable
                # condition, not two with different attribute shapes.
                record_span_attribute(retrieval_span, "index_ready", False)
                record_span_attribute(retrieval_span, "abstained", True)
                return []
            with traced_span("embed_query"):
                question_embedding = text_embedder.embed_query(question)
            # Unfiltered for now; the doc-type filter arrives in Slice 6.
            with traced_span("find_nearest_chunks") as search_span:
                nearest_hits = vector_index.find_nearest_chunks(
                    conn, question_embedding, settings.top_k,
                )
                record_span_attribute(search_span, "hit_count", len(nearest_hits))
            results: list[RetrievedChunk] = []
            for chunk_id, distance in nearest_hits:
                chunk_with_source = chunk_records.fetch_chunk_with_filename(conn, chunk_id)
                if chunk_with_source is None or chunk_with_source.document_status != "indexed":
                    continue  # only indexed documents are visible to retrieval (§3.1g)
                results.append(RetrievedChunk(
                    chunk=chunk_with_source.chunk,
                    filename=chunk_with_source.source_filename,
                    score=_l2_distance_to_cosine_similarity(distance),
                ))
        finally:
            conn.close()

        # Abstention guard: weak best hit => treat as unsupported (§3.4).
        best_score = results[0].score if results else 0.0
        record_span_attribute(retrieval_span, "best_score", best_score)
        if not results or best_score < settings.abstain_threshold:
            record_span_attribute(retrieval_span, "abstained", True)
            return []
        record_span_attribute(retrieval_span, "abstained", False)
        record_span_attribute(retrieval_span, "returned_count", len(results))
        return results
