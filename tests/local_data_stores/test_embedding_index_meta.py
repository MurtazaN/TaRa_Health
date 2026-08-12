"""index_meta singleton: first-index write, drift detection, singleton-ness."""
from __future__ import annotations

import pytest

from tara.app_errors import IndexMismatchError
from tara.local_data_stores import embedding_index_meta
from tara.local_data_stores.db_connection import connect_db

_CREATED_AT = "2026-01-01T00:00:00+00:00"


@pytest.mark.integration
def test_ensure_records_model_and_dim_on_first_index(offline_ingest_env):
    conn = connect_db()
    try:
        assert embedding_index_meta.read_index_meta(conn) is None
        embedding_index_meta.ensure_index_meta(conn, "model-a", 256, _CREATED_AT)
        conn.commit()
        assert embedding_index_meta.read_index_meta(conn) == ("model-a", 256)
    finally:
        conn.close()


@pytest.mark.integration
def test_ensure_accepts_matching_config(offline_ingest_env):
    conn = connect_db()
    try:
        embedding_index_meta.ensure_index_meta(conn, "model-a", 256, _CREATED_AT)
        embedding_index_meta.ensure_index_meta(conn, "model-a", 256, _CREATED_AT)  # no raise
    finally:
        conn.close()


@pytest.mark.integration
def test_ensure_raises_on_model_or_dim_drift(offline_ingest_env):
    conn = connect_db()
    try:
        embedding_index_meta.ensure_index_meta(conn, "model-a", 256, _CREATED_AT)
        with pytest.raises(IndexMismatchError, match="Re-index"):
            embedding_index_meta.ensure_index_meta(conn, "model-b", 1024, _CREATED_AT)
    finally:
        conn.close()


@pytest.mark.integration
def test_write_keeps_a_single_row(offline_ingest_env):
    conn = connect_db()
    try:
        embedding_index_meta.write_index_meta(conn, "model-a", 256, _CREATED_AT)
        embedding_index_meta.write_index_meta(conn, "model-b", 512, _CREATED_AT)

        assert conn.execute("SELECT COUNT(*) FROM index_meta").fetchone()[0] == 1
        assert embedding_index_meta.read_index_meta(conn) == ("model-b", 512)
    finally:
        conn.close()
