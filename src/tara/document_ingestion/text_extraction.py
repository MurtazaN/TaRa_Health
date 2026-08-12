"""Text extraction that PRESERVES page number and character span for every piece
of text — this provenance is what makes citations possible downstream (§3.1b).

- Digital PDFs  -> PyMuPDF raw word positions (fast, position-preserving)
- Scans/images  -> Docling (layout-aware + OCR), fully local  [Slice 5]

Char spans index into a *canonical page text* (words joined by spaces, lines by
newlines), NOT a reflowed markdown rendering — a markdown layer rearranges
characters and breaks the offset<->source mapping citations depend on (§3.1b).
The citation layer re-derives the same canonical text to resolve a span, so the
derivation here is the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

import pymupdf

from tara.document_ingestion.source_kind_detection import SourceKind, detect_source_kind


@dataclass
class ExtractedSpan:
    """A contiguous slice of one page's canonical text. Invariant:
    ``canonical_page_text[char_start:char_end] == text``."""
    page: int          # 1-based
    char_start: int
    char_end: int
    text: str


def extract_text_spans(path: Path) -> list[ExtractedSpan]:
    source_kind = detect_source_kind(path)
    if source_kind is SourceKind.PDF_TEXT:
        return _extract_native_pdf_spans(path)
    return _extract_ocr_spans(path)


def page_canonical_text(page: pymupdf.Page) -> str:
    """Deterministic reading-order text for a page: words joined by single spaces,
    lines joined by single newlines. Reused by the citation layer so spans resolve."""
    # Each word tuple is (x0, y0, x1, y1, word, block_no, line_no, word_no).
    words = page.get_text("words")
    if not words:
        return ""
    words.sort(key=lambda word: (word[5], word[6], word[7]))
    lines = [
        " ".join(word[4] for word in line_words)
        for _, line_words in groupby(words, key=lambda word: (word[5], word[6]))
    ]
    return "\n".join(lines)


def _extract_native_pdf_spans(path: Path) -> list[ExtractedSpan]:
    spans: list[ExtractedSpan] = []
    with pymupdf.open(path) as pdf_document:
        for page_number, page in enumerate(pdf_document, start=1):
            page_text = page_canonical_text(page)
            if page_text:
                spans.append(ExtractedSpan(
                    page=page_number, char_start=0,
                    char_end=len(page_text), text=page_text,
                ))
    return spans


def _extract_ocr_spans(path: Path) -> list[ExtractedSpan]:
    """OCR path for scans/images (Slice 5). Citations resolve to page level there
    because OCR char offsets aren't pixel-mappable (§3.1b)."""
    raise NotImplementedError("OCR extraction (scans/images) lands in Slice 5.")
