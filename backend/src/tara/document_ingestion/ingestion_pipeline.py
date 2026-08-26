"""Ingests one uploaded document: bytes in -> stored, chunked, embedded, and
indexed locally. `ingest_document()` is the single entry point (called by
web_app's /upload) and returns the resulting Document record.

    validate -> dedup -> save blob -> extract text spans -> chunk -> embed
             -> [txn: document row + chunk rows] -> write vectors -> status=indexed

This module owns only the ORCHESTRATION invariants (§3.1f/§3.1g); every store
touch is a named call into local_data_stores. The invariants:
  * The failure-prone steps (parse + network embedding) run BEFORE any store
    mutation, so a failure never destroys an existing document — in particular a
    `replace=True` re-index only purges the prior version once the new one is
    validated (avoids unrecoverable data loss).
  * A partial-unique index on content_hash makes the dedup check race-safe: a
    lost race surfaces as IntegrityError and returns the winning document.
Doc-type classification is deferred to Slice 6 (doc_type='other').
"""
from __future__ import annotations

import dataclasses
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone

from tara.app_errors import IngestionError
from tara.config import get_settings
from tara.data_models import Document
from tara.document_ingestion.text_chunking import chunk_spans
from tara.document_ingestion.text_extraction import extract_text_spans
from tara.execution_tracing.span_emitter import record_span_attribute, traced_span
from tara.local_data_stores import (
    blob_store,
    chunk_records,
    document_records,
    embedding_index_meta,
    vector_index,
)
from tara.local_data_stores.db_connection import connect_db
from tara.local_data_stores.document_purge import purge_document
from tara.semantic_search import text_embedder
from tara.upload_validation import validate_upload


def ingest_document(filename: str, file_bytes: bytes, *, replace: bool = False) -> Document:
    settings = get_settings()
    validate_upload(filename, len(file_bytes))
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    with traced_span("ingest_document", byte_count=len(file_bytes), replace=replace):
        conn = connect_db()
        try:
            vector_index.load_vector_extension(conn)
            existing_document = document_records.find_indexed_document_by_hash(conn, content_hash)
            if existing_document is not None and not replace:
                return existing_document  # idempotent: no duplicate (§3.1f)

            now = datetime.now(timezone.utc)
            embedding_index_meta.ensure_index_meta(
                conn, settings.embed_model, settings.embed_dim, now.isoformat(),
            )
            vector_index.init_vector_table(conn)  # idempotent; commits
            conn.commit()

            doc_id = uuid.uuid4().hex
            blob_path = blob_store.save_blob(doc_id, filename, file_bytes)
            is_doc_committed = False
            try:
                # Failure-prone work first, before mutating any store (see module docstring).
                with traced_span("extract_text_spans") as extraction_span:
                    text_spans = extract_text_spans(blob_path)
                    record_span_attribute(extraction_span, "span_count", len(text_spans))
                if not text_spans:
                    raise IngestionError(f"No extractable text in '{filename}'.")
                with traced_span("chunk_spans") as chunking_span:
                    chunks = chunk_spans(doc_id, text_spans)
                    record_span_attribute(chunking_span, "chunk_count", len(chunks))
                with traced_span("embed_chunks", chunk_count=len(chunks)):
                    chunk_embeddings = text_embedder.embed_texts([chunk.text for chunk in chunks])

                # Only now is it safe to destroy the prior version (§3.1f replace path).
                if replace and existing_document is not None:
                    purge_document(existing_document.doc_id)

                document = Document(
                    doc_id=doc_id, filename=filename, doc_type="other",
                    content_hash=content_hash, status="indexing",
                    page_count=max(span.page for span in text_spans), uploaded_at=now,
                )
                # One transaction: the document row and all its chunk rows (§3.1g).
                document_records.insert_document_row(conn, document)
                chunk_records.insert_chunk_rows(conn, chunks)
                conn.commit()
                is_doc_committed = True

                vector_index.add_embeddings(
                    conn, list(zip((chunk.chunk_id for chunk in chunks), chunk_embeddings)),
                )
                try:
                    document_records.mark_document_status(conn, doc_id, "indexed")
                    conn.commit()
                except sqlite3.IntegrityError:
                    # Lost the dedup race: another ingest indexed this content first.
                    conn.rollback()
                    purge_document(doc_id)
                    winning_document = document_records.find_indexed_document_by_hash(
                        conn, content_hash,
                    )
                    if winning_document is None:
                        raise
                    return winning_document

                return dataclasses.replace(document, status="indexed")
            except Exception:
                _clean_up_failed_ingest(conn, doc_id, is_doc_committed)
                raise
        finally:
            conn.close()


def _clean_up_failed_ingest(conn: sqlite3.Connection, doc_id: str, is_doc_committed: bool) -> None:
    """Best-effort recovery so a failed ingest leaves no inconsistent state (§3.1g).
    A committed doc is marked 'indexing_failed' (invisible to retrieval) with its
    partial vectors removed; the orphan blob is always deleted. Never masks the
    original error."""
    try:
        conn.rollback()
        chunk_ids = chunk_records.chunk_ids_for_document(conn, doc_id)
        vector_index.delete_embeddings(conn, chunk_ids)
        if is_doc_committed:
            document_records.mark_document_status(conn, doc_id, "indexing_failed")
        conn.commit()
    except Exception:
        pass
    try:
        blob_store.delete_blob(doc_id)
    except Exception:
        pass
