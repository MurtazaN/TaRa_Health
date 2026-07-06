"""Slice 1 ingestion: boundary validation, position-preserving extraction,
page-bounded deterministic chunking, and the transactional/idempotent pipeline."""
from __future__ import annotations

import pytest

from tara.ingestion.chunk import chunk
from tara.ingestion.detect import SourceKind, UploadError, detect, validate_upload
from tara.ingestion.extract import extract, page_canonical_text
from tara.storage import vector
from tara.storage.db import connect


# --- detect / boundary validation (§3.1a) ---

@pytest.mark.unit
def test_validate_upload_rejects_bad_extension(tara_env):
    with pytest.raises(UploadError, match="Unsupported"):
        validate_upload("notes.exe", 100)


@pytest.mark.unit
def test_validate_upload_rejects_oversize(tara_env):
    with pytest.raises(UploadError, match="limit"):
        validate_upload("big.pdf", tara_env.max_upload_bytes + 1)


@pytest.mark.unit
def test_validate_upload_rejects_empty(tara_env):
    with pytest.raises(UploadError, match="empty"):
        validate_upload("empty.pdf", 0)


@pytest.mark.unit
def test_validate_upload_accepts_good(tara_env):
    validate_upload("policy.PDF", 1000)  # case-insensitive suffix


@pytest.mark.unit
def test_detect_native_text_pdf(tara_env, make_pdf, tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf([["Specialist copay is $40 per visit."]]))
    assert detect(path) is SourceKind.PDF_TEXT


@pytest.mark.unit
def test_detect_image_routes_to_ocr(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n")  # not opened; suffix decides
    assert detect(path) is SourceKind.IMAGE


# --- extraction preserves provenance (§3.1b) ---

@pytest.mark.unit
def test_extract_preserves_page_and_span_invariant(make_pdf, tmp_path):
    import pymupdf

    data = make_pdf([
        ["Specialist copay is $40 per visit.", "Deductible is $1500 annually."],
        ["Glucose result is 95 mg/dL."],
    ])
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)

    spans = extract(path)
    assert [s.page for s in spans] == [1, 2]  # one span per page, in order

    # The core citation invariant: a span's char range indexes its page text.
    with pymupdf.open(path) as doc:
        for span in spans:
            page_text = page_canonical_text(doc[span.page - 1])
            assert page_text[span.char_start:span.char_end] == span.text
    assert "$40" in spans[0].text
    assert "95" in spans[1].text


# --- chunking (§3.1d) ---

@pytest.mark.unit
def test_chunk_is_page_bounded_and_deterministic(make_pdf, tmp_path):
    data = make_pdf([["copay $40", "deductible $1500"], ["glucose 95"]])
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)
    spans = extract(path)

    chunks = chunk("docABC", spans, target_tokens=1000, overlap=0)
    # No chunk spans two pages.
    assert all(c.page in (1, 2) for c in chunks)
    # Deterministic ids of the form "{doc}:{page}:{char_start}".
    assert all(c.chunk_id == f"docABC:{c.page}:{c.char_start}" for c in chunks)
    # chunk.text is the exact slice of its page's canonical text.
    by_page = {s.page: s.text for s in spans}
    for c in chunks:
        assert by_page[c.page][c.char_start:c.char_end] == c.text
    # Same inputs -> same ids (idempotent).
    again = chunk("docABC", spans, target_tokens=1000, overlap=0)
    assert [c.chunk_id for c in chunks] == [d.chunk_id for d in again]


@pytest.mark.unit
def test_chunk_splits_large_pages(make_pdf, tmp_path):
    lines = [f"line number {i} with some filler words here" for i in range(40)]
    path = tmp_path / "big.pdf"
    path.write_bytes(make_pdf([lines]))
    spans = extract(path)
    chunks = chunk("d", spans, target_tokens=20, overlap=0)
    assert len(chunks) > 1  # a big page produced multiple chunks
    assert all(c.page == 1 for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)  # unique ids


# --- pipeline: transactional + idempotent (§3.1f, §3.1g) ---

@pytest.mark.integration
def test_ingest_indexes_document_with_chunks_and_vectors(ingest_env, make_pdf):
    from tara.ingestion.pipeline import ingest

    doc = ingest("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    assert doc.status == "indexed"
    assert doc.page_count == 1
    assert doc.content_hash  # sha256 recorded

    conn = connect()
    try:
        vector.load(conn)  # vec0 is per-connection
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_vecs = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert n_chunks == n_vecs > 0  # every chunk got a vector
    finally:
        conn.close()


@pytest.mark.integration
def test_reingest_same_file_is_deduped(ingest_env, make_pdf):
    from tara.ingestion.pipeline import ingest

    data = make_pdf([["Specialist copay is $40 per visit."]])
    first = ingest("policy.pdf", data)
    second = ingest("policy-again.pdf", data)  # same bytes, different name

    assert second.doc_id == first.doc_id  # idempotent
    conn = connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.integration
def test_purge_removes_rows_vectors_and_blob(ingest_env, make_pdf):
    from tara.ingestion.pipeline import ingest
    from tara.storage.purge import purge_document

    doc = ingest("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    blob_dir = ingest_env.blob_dir
    assert list(blob_dir.glob(f"{doc.doc_id}.*"))  # blob present

    assert purge_document(doc.doc_id) is True

    conn = connect()
    try:
        vector.load(conn)  # vec0 is per-connection
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 0
    finally:
        conn.close()
    assert not list(blob_dir.glob(f"{doc.doc_id}.*"))  # blob gone
    assert purge_document(doc.doc_id) is False  # idempotent no-op


@pytest.mark.integration
def test_failed_extraction_cleans_up_blob_and_leaves_no_indexed_doc(ingest_env, make_pdf, monkeypatch):
    from tara.ingestion import pipeline

    monkeypatch.setattr(pipeline, "extract", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        pipeline.ingest("policy.pdf", make_pdf([["Specialist copay is $40."]]))

    conn = connect()
    try:
        indexed = conn.execute("SELECT COUNT(*) FROM documents WHERE status='indexed'").fetchone()[0]
        assert indexed == 0
    finally:
        conn.close()
    assert not list(ingest_env.blob_dir.glob("*"))  # orphan blob removed
