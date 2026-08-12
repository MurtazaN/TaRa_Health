"""Upload boundary validation: extension whitelist, size ceiling, empty check."""
from __future__ import annotations

import pytest

from tara.app_errors import UploadError
from tara.upload_validation import validate_upload, validated_file_suffix


@pytest.mark.unit
def test_validate_upload_rejects_bad_extension(isolated_env):
    with pytest.raises(UploadError, match="Unsupported"):
        validate_upload("notes.exe", 100)


@pytest.mark.unit
def test_validate_upload_rejects_oversize(isolated_env):
    with pytest.raises(UploadError, match="limit"):
        validate_upload("big.pdf", isolated_env.max_upload_bytes + 1)


@pytest.mark.unit
def test_validate_upload_rejects_empty(isolated_env):
    with pytest.raises(UploadError, match="empty"):
        validate_upload("empty.pdf", 0)


@pytest.mark.unit
def test_validate_upload_accepts_good(isolated_env):
    validate_upload("policy.PDF", 1000)  # case-insensitive suffix


@pytest.mark.unit
def test_validated_file_suffix_lowercases_and_whitelists():
    assert validated_file_suffix("Policy.PDF") == ".pdf"
    with pytest.raises(UploadError, match="Unsupported"):
        validated_file_suffix("script.sh")
