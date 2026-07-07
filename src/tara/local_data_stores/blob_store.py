"""Original uploaded files ("blobs"), stored on disk under config.blob_dir.

The blob filename is the doc_id plus the original suffix, so a document's blob is
found by its id alone (used by purge). The suffix is re-whitelisted here as
defense-in-depth behind the upload-boundary check (tara.upload_validation).
TODO: encrypt blobs at rest with the same key strategy as the DB (§3.2/§7).
"""
from __future__ import annotations

from pathlib import Path

from tara.config import get_settings
from tara.upload_validation import validated_file_suffix


def save_blob(doc_id: str, filename: str, file_bytes: bytes) -> Path:
    blob_dir = get_settings().blob_dir
    blob_dir.mkdir(parents=True, exist_ok=True, mode=0o700)  # PHI on disk: owner-only
    blob_path = blob_dir / f"{doc_id}{validated_file_suffix(filename)}"
    blob_path.write_bytes(file_bytes)
    return blob_path


def load_blob(blob_path: Path) -> bytes:
    return blob_path.read_bytes()


def delete_blob(doc_id: str) -> None:
    """Remove the blob for a document (any suffix). Idempotent."""
    blob_dir = get_settings().blob_dir
    for blob_path in blob_dir.glob(f"{doc_id}.*"):
        blob_path.unlink(missing_ok=True)
