"""Chunking: page-bounded, deterministic ids, exact-offset slices, and overlap."""
from __future__ import annotations

import pytest

from tara.document_ingestion.text_chunking import chunk_spans
from tara.document_ingestion.text_extraction import ExtractedSpan, extract_text_spans


@pytest.mark.unit
def test_chunk_is_page_bounded_and_deterministic(make_pdf, tmp_path):
    data = make_pdf([["copay $40", "deductible $1500"], ["glucose 95"]])
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)
    spans = extract_text_spans(path)

    chunks = chunk_spans("docABC", spans, target_tokens=1000, overlap_tokens=0)
    # No chunk spans two pages.
    assert all(chunk.page in (1, 2) for chunk in chunks)
    # Deterministic ids of the form "{doc}:{page}:{char_start}".
    assert all(chunk.chunk_id == f"docABC:{chunk.page}:{chunk.char_start}" for chunk in chunks)
    # chunk.text is the exact slice of its page's canonical text.
    text_by_page = {span.page: span.text for span in spans}
    for chunk in chunks:
        assert text_by_page[chunk.page][chunk.char_start:chunk.char_end] == chunk.text
    # Same inputs -> same ids (idempotent).
    again = chunk_spans("docABC", spans, target_tokens=1000, overlap_tokens=0)
    assert [chunk.chunk_id for chunk in chunks] == [chunk.chunk_id for chunk in again]


@pytest.mark.unit
def test_chunk_splits_large_pages(make_pdf, tmp_path):
    lines = [f"line number {i} with some filler words here" for i in range(40)]
    path = tmp_path / "big.pdf"
    path.write_bytes(make_pdf([lines]))
    spans = extract_text_spans(path)
    chunks = chunk_spans("d", spans, target_tokens=20, overlap_tokens=0)
    assert len(chunks) > 1  # a big page produced multiple chunks
    assert all(chunk.page == 1 for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)  # unique ids


@pytest.mark.unit
def test_consecutive_chunks_overlap_when_overlap_tokens_positive():
    page_text = "\n".join(f"word{i} filler words on this line" for i in range(30))
    span = ExtractedSpan(page=1, char_start=0, char_end=len(page_text), text=page_text)

    chunks = chunk_spans("doc1", [span], target_tokens=20, overlap_tokens=10)

    assert len(chunks) > 1
    for previous_chunk, next_chunk in zip(chunks, chunks[1:]):
        # The next chunk starts before the previous one ends: shared context.
        assert next_chunk.char_start < previous_chunk.char_end
        # But always advances, so chunking terminates and ids stay unique.
        assert next_chunk.char_start > previous_chunk.char_start
    # Overlap must not break the exact-slice citation invariant.
    for chunk in chunks:
        assert page_text[chunk.char_start:chunk.char_end] == chunk.text


@pytest.mark.unit
def test_chunk_spans_defaults_come_from_config(monkeypatch):
    """Chunk sizing is coupled to the embedding model's limit, so it must be
    configuration — not a hard-coded function default no operator can reach."""
    from tara import config
    from tara.document_ingestion.text_chunking import chunk_spans
    from tara.document_ingestion.text_extraction import ExtractedSpan

    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "10")
    monkeypatch.setenv("TARA_CHUNK_OVERLAP_TOKENS", "0")
    config.get_settings.cache_clear()

    page_text = "\n".join(f"line number {i} with several words" for i in range(40))
    spans = [ExtractedSpan(page=1, char_start=0, char_end=len(page_text), text=page_text)]
    chunks = chunk_spans("doc-1", spans)

    config.get_settings.cache_clear()
    # A 10-token budget over ~40 lines must produce many small chunks, not one big one.
    assert len(chunks) > 5
