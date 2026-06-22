"""End-to-end ingestion: upload bytes -> stored, classified, chunked, embedded,
and indexed locally. Returns the Document record.

    save blob -> extract (+page/char spans) -> classify -> chunk
              -> embed -> write rows + vectors
"""
from __future__ import annotations

import uuid
from pathlib import Path

from tara.embeddings.embedder import embed_texts
from tara.ingestion.chunk import chunk as chunk_spans
from tara.ingestion.classify import classify
from tara.ingestion.extract import extract
from tara.storage import blobs
from tara.storage.models import Document


def ingest(filename: str, data: bytes) -> Document:
    doc_id = uuid.uuid4().hex
    path = blobs.save(doc_id, filename, data)

    spans = extract(path)
    full_text = "\n".join(s.text for s in spans)
    doc_type = classify(full_text)
    chunks = chunk_spans(doc_id, spans)

    _embeddings = embed_texts([c.text for c in chunks])  # noqa: F841

    # TODO: persist Document + chunks (storage.db) and embeddings (storage.vector),
    #       then return the populated Document.
    raise NotImplementedError
