"""Text extraction that PRESERVES page number and character span for every piece
of text — this provenance is what makes citations possible downstream.

- Digital PDFs  -> PyMuPDF4LLM (fast)
- Scans/images  -> Docling (layout-aware + OCR), fully local
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tara.ingestion.detect import SourceKind, detect


@dataclass
class ExtractedSpan:
    page: int
    char_start: int
    char_end: int
    text: str


def extract(path: Path) -> list[ExtractedSpan]:
    kind = detect(path)
    if kind is SourceKind.PDF_TEXT:
        return _extract_pymupdf(path)
    return _extract_docling(path)


def _extract_pymupdf(path: Path) -> list[ExtractedSpan]:
    """TODO: use pymupdf4llm to get markdown + page mapping; build spans."""
    raise NotImplementedError


def _extract_docling(path: Path) -> list[ExtractedSpan]:
    """TODO: use Docling's DocumentConverter (OCR enabled) and map elements
    back to page + char offsets."""
    raise NotImplementedError
