"""Blob store: save/load/delete round-trips, suffix whitelisting, idempotency."""
from __future__ import annotations

import pytest

from tara.app_errors import UploadError
from tara.local_data_stores import blob_store


@pytest.mark.unit
def test_save_blob_writes_bytes_under_doc_id_with_lowercased_suffix(isolated_env):
    blob_path = blob_store.save_blob("doc1", "Policy.PDF", b"pdf bytes")
    assert blob_path.name == "doc1.pdf"
    assert blob_path.parent == isolated_env.blob_dir
    assert blob_store.load_blob(blob_path) == b"pdf bytes"


@pytest.mark.unit
def test_save_blob_rejects_unsupported_extension(isolated_env):
    with pytest.raises(UploadError, match="Unsupported"):
        blob_store.save_blob("doc1", "notes.exe", b"x")


@pytest.mark.unit
def test_delete_blob_removes_file_and_is_idempotent(isolated_env):
    blob_path = blob_store.save_blob("doc1", "policy.pdf", b"pdf bytes")

    blob_store.delete_blob("doc1")
    assert not blob_path.exists()

    blob_store.delete_blob("doc1")  # second delete: no error
