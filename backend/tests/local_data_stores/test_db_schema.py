"""Schema + connection contracts: tables build, foreign-key cascade fires, and
the partial-unique content_hash index blocks duplicate indexed documents."""
from __future__ import annotations

import sqlite3

import pytest

from tara.local_data_stores.db_connection import connect_db
from tara.local_data_stores.db_schema import init_db_schema


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


@pytest.mark.integration
def test_schema_builds_with_all_contract_columns(isolated_env):
    init_db_schema()
    conn = connect_db()
    try:
        assert {"content_hash", "status"} <= _columns(conn, "documents")
        assert {"retrieved_chunk_ids", "model_route"} <= _columns(conn, "queries")
        assert {"embed_model", "embed_dim", "created_at"} <= _columns(conn, "index_meta")
    finally:
        conn.close()


@pytest.mark.integration
def test_connect_db_enables_foreign_keys(isolated_env):
    conn = connect_db()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.integration
def test_document_delete_cascades_to_chunks(isolated_env):
    init_db_schema()
    conn = connect_db()
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, uploaded_at) VALUES (?, ?, ?)",
            ("d1", "policy.pdf", "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO chunks (chunk_id, doc_id, page, char_start, char_end, text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("d1:1:0", "d1", 1, 0, 10, "hello"),
        )
        conn.commit()

        conn.execute("DELETE FROM documents WHERE doc_id = ?", ("d1",))
        conn.commit()

        remaining = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert remaining == 0  # cascade fired
    finally:
        conn.close()


@pytest.mark.integration
def test_content_hash_unique_among_indexed_only(isolated_env):
    init_db_schema()
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
