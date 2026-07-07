"""Original uploaded files, stored on disk under data_dir/blobs.

The blob filename is the doc_id plus the original suffix, so a document's blob is
found by its id alone (used by purge). The suffix is re-whitelisted here as
defense-in-depth behind the upload-boundary check (tara.validation).
TODO: encrypt blobs at rest with the same key strategy as the DB (§3.2/§7).
"""
from __future__ import annotations

from pathlib import Path

from tara.config import get_settings
from tara.validation import allowed_suffix


def save_blob(doc_id: str, filename: str, data: bytes) -> Path:
    blob_dir = get_settings().blob_dir
    blob_dir.mkdir(parents=True, exist_ok=True, mode=0o700)  # PHI on disk: owner-only
    path = blob_dir / f"{doc_id}{allowed_suffix(filename)}"
    path.write_bytes(data)
    return path


def load_blob(path: Path) -> bytes:
    return path.read_bytes()


def delete_blob(doc_id: str) -> None:
    """Remove the blob for a document (any suffix). Idempotent."""
    blob_dir = get_settings().blob_dir
    for path in blob_dir.glob(f"{doc_id}.*"):
        path.unlink(missing_ok=True)
