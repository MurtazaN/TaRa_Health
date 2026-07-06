"""Decide how to extract: native-text PDF vs scanned PDF vs image, and validate
the upload at the system boundary (design §3.1a).

The branch matters because scans need OCR while digital PDFs do not.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

import pymupdf

from tara.config import get_settings

# Allowed upload extensions (§3.1a). Lower-cased suffixes.
ALLOWED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tiff"})

# A PDF with less than this much extractable text across all pages is treated as
# a scan and routed to OCR rather than the native-text path.
_MIN_TEXT_CHARS = 16


class UploadError(ValueError):
    """An upload failed boundary validation (bad extension or too large)."""


class SourceKind(str, Enum):
    PDF_TEXT = "pdf_text"     # digital PDF with a real text layer -> PyMuPDF (fast)
    PDF_SCAN = "pdf_scan"     # scanned PDF -> Docling w/ OCR
    IMAGE = "image"           # jpg/png/etc -> Docling w/ OCR


def validate_upload(filename: str, size_bytes: int) -> None:
    """Fail fast on a malformed/oversized upload before any processing (§3.1a).

    Validate on the raw filename + byte count *before* the blob is written, so a
    bad upload never touches disk or the extractor.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UploadError(f"Unsupported file type '{suffix or filename}'. Allowed: {allowed}.")
    max_bytes = get_settings().max_upload_bytes
    if size_bytes > max_bytes:
        raise UploadError(f"File is {size_bytes} bytes; the limit is {max_bytes} bytes.")
    if size_bytes <= 0:
        raise UploadError("File is empty.")


def detect(path: Path) -> SourceKind:
    """Classify how to extract. Assumes the upload already passed validate_upload.

    Heuristic (§3.1a/b): a PDF that yields little/no extractable text is a scan and
    routes to OCR; otherwise it takes the fast native-text path.
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
