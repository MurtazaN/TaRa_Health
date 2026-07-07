"""Upload boundary validation (design §3.1a), shared across layers.

Lives at the package root because three layers need it — the API surface
(app.py), the ingestion pipeline, and the blob store — and none of them should
import it from another layer (storage importing from ingestion was an inversion).
Fail fast: a malformed upload is rejected before any byte touches disk or a parser.
"""
from __future__ import annotations

from pathlib import Path

from tara.config import get_settings

# Allowed upload extensions (§3.1a). Lower-cased suffixes.
ALLOWED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tiff"})


class UploadError(ValueError):
    """An upload failed boundary validation (extension, size, or page count)."""


def allowed_suffix(filename: str) -> str:
    """Return the file's lower-cased suffix, or raise UploadError if not whitelisted."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UploadError(f"Unsupported file type '{suffix or filename}'. Allowed: {allowed}.")
    return suffix


def validate_upload(filename: str, size_bytes: int) -> None:
    """Fail fast on a malformed/oversized upload before any processing (§3.1a).

    Validates the raw filename + byte count *before* the blob is written, so a
    bad upload never touches disk or the extractor.
    """
    allowed_suffix(filename)
    max_bytes = get_settings().max_upload_bytes
    if size_bytes > max_bytes:
        raise UploadError(f"File is {size_bytes} bytes; the limit is {max_bytes} bytes.")
    if size_bytes <= 0:
        raise UploadError("File is empty.")
