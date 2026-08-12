"""Source-kind detection: native-text PDF vs scan vs image, and the page cap."""
from __future__ import annotations

import pytest

from tara.app_errors import UploadError
from tara.document_ingestion.source_kind_detection import SourceKind, detect_source_kind


@pytest.mark.unit
def test_detect_native_text_pdf(isolated_env, make_pdf, tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf([["Specialist copay is $40 per visit."]]))
    assert detect_source_kind(path) is SourceKind.PDF_TEXT


@pytest.mark.unit
def test_detect_image_routes_to_ocr(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n")  # not opened; suffix decides
    assert detect_source_kind(path) is SourceKind.IMAGE


@pytest.mark.unit
def test_pdf_page_cap_rejects_oversized(make_pdf, tmp_path, monkeypatch):
    from tara import config

    monkeypatch.setenv("TARA_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("TARA_MAX_PDF_PAGES", "1")
    config.get_settings.cache_clear()
    try:
        path = tmp_path / "multi.pdf"
        path.write_bytes(make_pdf([["page one"], ["page two"]]))
        with pytest.raises(UploadError, match="pages"):
            detect_source_kind(path)
    finally:
        config.get_settings.cache_clear()
