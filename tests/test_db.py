"""Schema + connection contracts (design §3.2, §4): the schema builds, the new
v0.3 columns/tables exist, and the ON DELETE CASCADE actually fires (which only
happens with PRAGMA foreign_keys = ON)."""
from __future__ import annotations

import pytest

from tara.storage.db import connect, init_schema


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


@pytest.mark.integration
def test_schema_builds_with_v03_columns(tara_env):
    init_schema()
    conn = connect()
    try:
        assert {"content_hash", "status"} <= _columns(conn, "documents")
        assert {"retrieved_chunk_ids", "model_route"} <= _columns(conn, "queries")
        assert {"embed_model", "embed_dim", "created_at"} <= _columns(conn, "index_meta")
    finally:
        conn.close()


@pytest.mark.integration
def test_connect_enables_foreign_keys(tara_env):
    conn = connect()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.integration
def test_document_delete_cascades_to_chunks(tara_env):
    init_schema()
    conn = connect()
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
