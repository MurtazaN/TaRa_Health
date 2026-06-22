"""Original uploaded files, stored on disk under data_dir/blobs.
TODO: encrypt blobs at rest with the same key strategy as the DB.
"""
from __future__ import annotations

from pathlib import Path

from tara.config import get_settings


def save(doc_id: str, filename: str, data: bytes) -> Path:
    path = get_settings().blob_dir / f"{doc_id}{Path(filename).suffix}"
    path.write_bytes(data)
    return path


def load(path: Path) -> bytes:
    return path.read_bytes()
