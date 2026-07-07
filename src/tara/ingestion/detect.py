"""Decide how to extract: native-text PDF vs scanned PDF vs image (design §3.1a/b).

The branch matters because scans need OCR while digital PDFs do not. Upload
boundary validation lives in tara.validation; this module assumes the file
already passed it.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

import pymupdf

from tara.config import get_settings
from tara.validation import UploadError

# A PDF with less than this much extractable text across all pages is treated as
# a scan and routed to OCR rather than the native-text path.
_MIN_TEXT_CHARS = 16


class SourceKind(str, Enum):
    PDF_TEXT = "pdf_text"     # digital PDF with a real text layer -> PyMuPDF (fast)
    PDF_SCAN = "pdf_scan"     # scanned PDF -> Docling w/ OCR
    IMAGE = "image"           # jpg/png/etc -> Docling w/ OCR


def detect_source_kind(path: Path) -> SourceKind:
    """Classify how to extract. Assumes the upload already passed validate_upload.

    Heuristic (§3.1a/b): a PDF that yields little/no extractable text is a scan and
    routes to OCR; otherwise it takes the fast native-text path. The page ceiling
    bounds CPU/memory on a pathological (but byte-small) file.
    """
    suffix = path.suffix.lower()
    if suffix != ".pdf":
        return SourceKind.IMAGE
    max_pages = get_settings().max_pdf_pages
    with pymupdf.open(path) as doc:
        if doc.page_count > max_pages:
            raise UploadError(
                f"PDF has {doc.page_count} pages; the limit is {max_pages}."
            )
        total_text = sum(len(page.get_text("text").strip()) for page in doc)
    return SourceKind.PDF_TEXT if total_text >= _MIN_TEXT_CHARS else SourceKind.PDF_SCAN
