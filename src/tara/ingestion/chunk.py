"""Chunk extracted text for retrieval while carrying page + char span through.

Packs whole lines into ~target_tokens chunks (structural-ish), never crossing a
page boundary (§3.1d), with deterministic ids so re-ingest is idempotent and
historical citations stay valid. Each chunk's text is the exact slice of its
page's canonical text at [char_start, char_end], preserving the citation invariant.
"""
from __future__ import annotations

from tara.ingestion.extract import ExtractedSpan
from tara.storage.models import Chunk

# Rough token estimate; local models don't need exact token accounting for chunking.
_CHARS_PER_TOKEN = 4


def _approximate_token_count(char_len: int) -> int:
    return max(1, char_len // _CHARS_PER_TOKEN)


def _line_char_offsets(text: str) -> list[tuple[int, int]]:
    """Return [(start, end), ...] for each line in `text` (offsets into `text`).
    end is exclusive and excludes the trailing newline."""
    offsets: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        offsets.append((pos, pos + len(line)))
        pos += len(line) + 1  # +1 for the "\n" separator
    return offsets


def _chunk_single_span(doc_id: str, span: ExtractedSpan,
                       target_tokens: int, overlap: int) -> list[Chunk]:
    text = span.text
    lines = _line_char_offsets(text)
    chunks: list[Chunk] = []
    i, n = 0, len(lines)
    while i < n:
        tokens, j = 0, i
        # Always take at least one line, then keep adding until the budget is hit.
        while j < n and (tokens < target_tokens or j == i):
            ls, le = lines[j]
            tokens += _approximate_token_count(le - ls)
            j += 1
        local_start = lines[i][0]
        local_end = lines[j - 1][1]
        char_start = span.char_start + local_start
        char_end = span.char_start + local_end
        chunks.append(Chunk(
            chunk_id=Chunk.make_id(doc_id, span.page, char_start),
            doc_id=doc_id,
            page=span.page,
            char_start=char_start,
            char_end=char_end,
            text=text[local_start:local_end],
        ))
        if j >= n:
            break
        # Step back so the next chunk overlaps ~`overlap` tokens, but always advance.
        back, k = 0, j - 1
        while k > i and back < overlap:
            ls, le = lines[k]
            back += _approximate_token_count(le - ls)
            k -= 1
        i = max(k + 1, i + 1)
    return chunks


def chunk_spans(doc_id: str, spans: list[ExtractedSpan],
                target_tokens: int = 800, overlap: int = 100) -> list[Chunk]:
    """Pack spans into ~target_tokens chunks, page-bounded, preserving provenance."""
    chunks: list[Chunk] = []
    for span in spans:
        chunks.extend(_chunk_single_span(doc_id, span, target_tokens, overlap))
    return chunks
