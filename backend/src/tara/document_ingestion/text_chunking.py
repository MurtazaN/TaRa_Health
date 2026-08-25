"""Chunk extracted text for retrieval while carrying page + char span through.

Packs whole lines into ~target_tokens chunks (structural-ish), never crossing a
page boundary (§3.1d), with deterministic ids so re-ingest is idempotent and
historical citations stay valid. Each chunk's text is the exact slice of its
page's canonical text at [char_start, char_end], preserving the citation invariant.
"""
from __future__ import annotations

from tara.document_ingestion.text_extraction import ExtractedSpan
from tara.data_models import Chunk

# Rough token estimate; local models don't need exact token accounting for chunking.
_CHARS_PER_TOKEN = 4


def _approximate_token_count(char_count: int) -> int:
    return max(1, char_count // _CHARS_PER_TOKEN)


def _line_char_offsets(text: str) -> list[tuple[int, int]]:
    """Return [(start, end), ...] for each line in `text` (offsets into `text`).
    end is exclusive and excludes the trailing newline."""
    line_offsets: list[tuple[int, int]] = []
    position = 0
    for line in text.split("\n"):
        line_offsets.append((position, position + len(line)))
        position += len(line) + 1  # +1 for the "\n" separator
    return line_offsets


def _chunk_single_span(doc_id: str, span: ExtractedSpan,
                       target_tokens: int, overlap_tokens: int) -> list[Chunk]:
    page_text = span.text
    line_offsets = _line_char_offsets(page_text)
    line_count = len(line_offsets)
    chunks: list[Chunk] = []
    first_line = 0
    while first_line < line_count:
        # Always take at least one line, then keep adding until the budget is hit.
        tokens_taken, next_line = 0, first_line
        while next_line < line_count and (tokens_taken < target_tokens or next_line == first_line):
            line_start, line_end = line_offsets[next_line]
            tokens_taken += _approximate_token_count(line_end - line_start)
            next_line += 1
        chunk_local_start = line_offsets[first_line][0]
        chunk_local_end = line_offsets[next_line - 1][1]
        char_start = span.char_start + chunk_local_start
        char_end = span.char_start + chunk_local_end
        chunks.append(Chunk(
            chunk_id=Chunk.make_chunk_id(doc_id, span.page, char_start),
            doc_id=doc_id,
            page=span.page,
            char_start=char_start,
            char_end=char_end,
            text=page_text[chunk_local_start:chunk_local_end],
        ))
        if next_line >= line_count:
            break
        # Step back so the next chunk overlaps ~overlap_tokens, but always advance.
        overlap_taken, overlap_start_line = 0, next_line - 1
        while overlap_start_line > first_line and overlap_taken < overlap_tokens:
            line_start, line_end = line_offsets[overlap_start_line]
            overlap_taken += _approximate_token_count(line_end - line_start)
            overlap_start_line -= 1
        first_line = max(overlap_start_line + 1, first_line + 1)
    return chunks


def chunk_spans(doc_id: str, spans: list[ExtractedSpan],
                target_tokens: int | None = None,
                overlap_tokens: int | None = None) -> list[Chunk]:
    """Pack spans into ~target_tokens chunks, page-bounded, preserving provenance.

    Sizing defaults to configuration rather than a literal, because it is coupled
    to the embedding model's sequence limit — sentence-transformers truncates
    silently past it (M5 §5.5). Explicit arguments still win, for tests.
    """
    from tara.config import get_settings

    settings = get_settings()
    resolved_target = settings.chunk_target_tokens if target_tokens is None else target_tokens
    resolved_overlap = settings.chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
    chunks: list[Chunk] = []
    for span in spans:
        chunks.extend(_chunk_single_span(doc_id, span, resolved_target, resolved_overlap))
    return chunks
