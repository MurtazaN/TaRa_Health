"""Slice 1 ingestion: boundary validation, position-preserving extraction,
page-bounded deterministic chunking, and the transactional/idempotent ingestion_pipeline."""
from __future__ import annotations

import sqlite3

import pytest

from tara.document_ingestion.text_chunking import chunk_spans
from tara.document_ingestion.source_kind_detection import SourceKind, detect_source_kind
from tara.document_ingestion.text_extraction import extract_text_spans, page_canonical_text
from tara.storage import vector_index
from tara.storage.metadata_db import connect_db
from tara.upload_validation import UploadError, validate_upload


# --- detect / boundary validation (§3.1a) ---

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
def test_detect_native_text_pdf(isolated_env, make_pdf, tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf([["Specialist copay is $40 per visit."]]))
    assert detect_source_kind(path) is SourceKind.PDF_TEXT


@pytest.mark.unit
def test_detect_image_routes_to_ocr(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n")  # not opened; suffix decides
    assert detect_source_kind(path) is SourceKind.IMAGE


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

    spans = extract_text_spans(path)
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
    spans = extract_text_spans(path)

    chunks = chunk_spans("docABC", spans, target_tokens=1000, overlap_tokens=0)
    # No chunk spans two pages.
    assert all(c.page in (1, 2) for c in chunks)
    # Deterministic ids of the form "{doc}:{page}:{char_start}".
    assert all(c.chunk_id == f"docABC:{c.page}:{c.char_start}" for c in chunks)
    # chunk.text is the exact slice of its page's canonical text.
    by_page = {s.page: s.text for s in spans}
    for c in chunks:
        assert by_page[c.page][c.char_start:c.char_end] == c.text
    # Same inputs -> same ids (idempotent).
    again = chunk_spans("docABC", spans, target_tokens=1000, overlap_tokens=0)
    assert [c.chunk_id for c in chunks] == [d.chunk_id for d in again]


@pytest.mark.unit
def test_chunk_splits_large_pages(make_pdf, tmp_path):
    lines = [f"line number {i} with some filler words here" for i in range(40)]
    path = tmp_path / "big.pdf"
    path.write_bytes(make_pdf([lines]))
    spans = extract_text_spans(path)
    chunks = chunk_spans("d", spans, target_tokens=20, overlap_tokens=0)
    assert len(chunks) > 1  # a big page produced multiple chunks
    assert all(c.page == 1 for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)  # unique ids


# --- ingestion_pipeline: transactional + idempotent (§3.1f, §3.1g) ---

@pytest.mark.integration
def test_ingest_indexes_document_with_chunks_and_vectors(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    doc = ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    assert doc.status == "indexed"
    assert doc.page_count == 1
    assert doc.content_hash  # sha256 recorded

    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)  # vec0 is per-connection
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_vecs = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert n_chunks == n_vecs > 0  # every chunk got a vector
    finally:
        conn.close()


@pytest.mark.integration
def test_reingest_same_file_is_deduped(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    data = make_pdf([["Specialist copay is $40 per visit."]])
    first = ingest_document("policy.pdf", data)
    second = ingest_document("policy-again.pdf", data)  # same bytes, different name

    assert second.doc_id == first.doc_id  # idempotent
    conn = connect_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.integration
def test_purge_removes_rows_vectors_and_blob(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document
    from tara.storage.document_purge import purge_document

    doc = ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    blob_dir = offline_ingest_env.blob_dir
    assert list(blob_dir.glob(f"{doc.doc_id}.*"))  # blob present

    assert purge_document(doc.doc_id) is True

    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)  # vec0 is per-connection
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 0
    finally:
        conn.close()
    assert not list(blob_dir.glob(f"{doc.doc_id}.*"))  # blob gone
    assert purge_document(doc.doc_id) is False  # idempotent no-op


@pytest.mark.integration
def test_failed_extraction_cleans_up_blob_and_leaves_no_indexed_doc(offline_ingest_env, make_pdf, monkeypatch):
    from tara.document_ingestion import ingestion_pipeline

    monkeypatch.setattr(ingestion_pipeline, "extract_text_spans", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        ingestion_pipeline.ingest_document("policy.pdf", make_pdf([["Specialist copay is $40."]]))

    conn = connect_db()
    try:
        indexed = conn.execute("SELECT COUNT(*) FROM documents WHERE status='indexed'").fetchone()[0]
        assert indexed == 0
    finally:
        conn.close()
    assert not list(offline_ingest_env.blob_dir.glob("*"))  # orphan blob removed


# --- replace flow: no data loss on failure (CRITICAL fix) ---

@pytest.mark.integration
def test_replace_failure_preserves_prior_document(offline_ingest_env, make_pdf, monkeypatch):
    from tara.document_ingestion import ingestion_pipeline

    data = make_pdf([["Specialist copay is $40 per visit."]])
    original = ingestion_pipeline.ingest_document("policy.pdf", data)

    # Re-index the same file, but embedding fails part-way through.
    monkeypatch.setattr(ingestion_pipeline.text_embedder, "embed_texts",
                        lambda texts: (_ for _ in ()).throw(RuntimeError("embed down")))
    with pytest.raises(RuntimeError, match="embed down"):
        ingestion_pipeline.ingest_document("policy.pdf", data, replace=True)

    conn = connect_db()
    try:
        vector_index.load_vector_extension(conn)
        row = conn.execute("SELECT status FROM documents WHERE doc_id=?", (original.doc_id,)).fetchone()
        assert row is not None and row["status"] == "indexed"  # prior version intact
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] > 0  # vectors kept
    finally:
        conn.close()


@pytest.mark.integration
def test_replace_reindexes_same_file(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document

    data = make_pdf([["Specialist copay is $40 per visit."]])
    first = ingest_document("policy.pdf", data)
    second = ingest_document("policy.pdf", data, replace=True)

    assert second.doc_id != first.doc_id  # re-indexed under a fresh id
    conn = connect_db()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status='indexed'"
        ).fetchone()[0] == 1  # old purged, one indexed doc remains
    finally:
        conn.close()


# --- dedup uniqueness (TOCTOU fix): schema constraint ---

@pytest.mark.integration
def test_content_hash_unique_among_indexed_only(offline_ingest_env):
    conn = connect_db()
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, content_hash, status, uploaded_at) "
            "VALUES ('a', 'a.pdf', 'HASH', 'indexed', '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO documents (doc_id, filename, content_hash, status, uploaded_at) "
                "VALUES ('b', 'b.pdf', 'HASH', 'indexed', '2026-01-01T00:00:00+00:00')"
            )
            conn.commit()
        conn.rollback()
        # Two *failed* attempts with the same hash are allowed (retry not blocked).
        conn.execute(
            "INSERT INTO documents (doc_id, filename, content_hash, status, uploaded_at) "
            "VALUES ('c', 'c.pdf', 'H2', 'indexing_failed', '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO documents (doc_id, filename, content_hash, status, uploaded_at) "
            "VALUES ('d', 'd.pdf', 'H2', 'indexing_failed', '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()


# --- security hardening: page cap + orphan-blob reconciliation ---

@pytest.mark.unit
def test_pdf_page_cap_rejects_oversized(make_pdf, tmp_path, monkeypatch):
    from tara import config
    from tara.document_ingestion.source_kind_detection import detect_source_kind

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


@pytest.mark.integration
def test_reconcile_removes_orphan_blobs_only(offline_ingest_env, make_pdf):
    from tara.document_ingestion.ingestion_pipeline import ingest_document
    from tara.storage.document_purge import reconcile_orphan_blobs

    doc = ingest_document("policy.pdf", make_pdf([["Specialist copay is $40 per visit."]]))
    orphan = offline_ingest_env.blob_dir / "deadbeefdeadbeef.pdf"
    orphan.write_bytes(b"orphaned phi")

    removed = reconcile_orphan_blobs()

    assert "deadbeefdeadbeef" in removed
    assert not orphan.exists()
    assert list(offline_ingest_env.blob_dir.glob(f"{doc.doc_id}.*"))  # real blob kept
