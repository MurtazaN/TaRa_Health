"""Retrieve the chunks most relevant to a question, optionally filtered by the
document type the question implies (cost -> insurance docs, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass

from tara.config import get_settings
from tara.embeddings.embedder import embed_query
from tara.storage.models import Chunk


@dataclass
class RetrievedChunk:
    chunk: Chunk
    filename: str
    score: float


def retrieve(question: str, doc_type_hint: str | None = None) -> list[RetrievedChunk]:
    k = get_settings().top_k
    _qvec = embed_query(question)  # noqa: F841
    # TODO: vector.search(_qvec, k, doc_ids filtered by doc_type_hint),
    #       join chunk rows + filenames, return RetrievedChunk list.
    raise NotImplementedError
