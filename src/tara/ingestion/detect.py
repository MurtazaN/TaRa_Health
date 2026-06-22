"""Decide how to extract: native-text PDF vs scanned PDF vs image.
The branch matters because scans need OCR while digital PDFs do not.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path


class SourceKind(str, Enum):
    PDF_TEXT = "pdf_text"     # digital PDF with a real text layer -> PyMuPDF4LLM (fast)
    PDF_SCAN = "pdf_scan"     # scanned PDF -> Docling w/ OCR
    IMAGE = "image"           # jpg/png/etc -> Docling w/ OCR


def detect(path: Path) -> SourceKind:
    """TODO: inspect the file. Heuristic: if a PDF yields little/no extractable
    text, treat it as a scan and route to OCR."""
    raise NotImplementedError
