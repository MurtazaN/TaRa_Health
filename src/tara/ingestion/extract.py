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

from tara.ingestion.detect import SourceKind, detect


@dataclass
class ExtractedSpan:
    """A contiguous slice of one page's canonical text. Invariant:
    ``canonical_page_text[char_start:char_end] == text``."""
    page: int          # 1-based
    char_start: int
    char_end: int
    text: str


def extract(path: Path) -> list[ExtractedSpan]:
    kind = detect(path)
    if kind is SourceKind.PDF_TEXT:
        return _extract_pymupdf(path)
    return _extract_docling(path)


def page_canonical_text(page: pymupdf.Page) -> str:
    """Deterministic reading-order text for a page: words joined by single spaces,
    lines joined by single newlines. Reused by the citation layer so spans resolve."""
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    if not words:
        return ""
    words.sort(key=lambda w: (w[5], w[6], w[7]))
    lines = [
        " ".join(w[4] for w in group)
        for _, group in groupby(words, key=lambda w: (w[5], w[6]))
    ]
    return "\n".join(lines)


def _extract_pymupdf(path: Path) -> list[ExtractedSpan]:
    spans: list[ExtractedSpan] = []
    with pymupdf.open(path) as doc:
        for pageno, page in enumerate(doc, start=1):
            text = page_canonical_text(page)
            if text:
                spans.append(ExtractedSpan(page=pageno, char_start=0, char_end=len(text), text=text))
    return spans


def _extract_docling(path: Path) -> list[ExtractedSpan]:
    """OCR path for scans/images (Slice 5). Citations resolve to page level there
    because OCR char offsets aren't pixel-mappable (§3.1b)."""
    raise NotImplementedError("OCR extraction (scans/images) lands in Slice 5.")
