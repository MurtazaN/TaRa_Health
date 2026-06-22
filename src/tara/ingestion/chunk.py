"""Chunk extracted text for retrieval while carrying page + char span through.
Prefer structural chunking (sections, table rows) over naive fixed windows.
"""
from __future__ import annotations

from tara.ingestion.extract import ExtractedSpan
from tara.storage.models import Chunk


def chunk(doc_id: str, spans: list[ExtractedSpan],
          target_tokens: int = 800, overlap: int = 100) -> list[Chunk]:
    """TODO: merge/split spans into ~target_tokens chunks with overlap,
    preserving the originating page and char offsets on each Chunk."""
    raise NotImplementedError
