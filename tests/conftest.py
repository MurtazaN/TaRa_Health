"""Shared fixtures. Put sample documents (a benefits summary, a lab report, an
EOB, etc.) under tests/fixtures/ to drive the eval harness.

Slice 1 tests run fully offline: `offline_ingest_env` points storage at a tmp dir and
replaces the text embedder with a deterministic bag-of-words fake so no LM Studio /
network call is needed. The fake produces unit vectors, so cosine similarity
(and the chunk retriever's L2->cosine conversion) behaves like the real thing.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Point TaRa's storage at an isolated tmp dir and reset the cached settings.

    Env vars take precedence over the real .env in pydantic-settings, so this
    keeps tests hermetic regardless of the developer's local .env.
    """
    from tara import config

    monkeypatch.setenv("TARA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TARA_MODEL_MODE", "local")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    config.ensure_dirs(settings)
    yield settings
    config.get_settings.cache_clear()


def fake_embed_one(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-words embedding hashed into `dim` buckets, unit-normalized."""
    vec = [0.0] * dim
    for token in re.findall(r"[a-z0-9$]+", text.lower()):
        bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        vec[bucket] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


@pytest.fixture
def make_pdf():
    """Factory: build an in-memory text PDF from lines-per-page. Returns bytes."""
    import pymupdf

    def _make(lines_per_page: list[list[str]]) -> bytes:
        doc = pymupdf.open()
        for lines in lines_per_page:
            page = doc.new_page()
            y = 72
            for line in lines:
                page.insert_text((72, y), line)
                y += 20
        data = doc.tobytes()
        doc.close()
        return bytes(data)

    return _make


@pytest.fixture
def offline_ingest_env(tmp_path, monkeypatch):
    """Isolated store + initialized schema + a deterministic offline text_embedder."""
    from tara import config
    from tara.embeddings import text_embedder
    from tara.storage.db import connect_db, init_db_schema
    from tara.storage.vector import init_vector_table

    monkeypatch.setenv("TARA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TARA_MODEL_MODE", "local")
    monkeypatch.setenv("TARA_EMBED_DIM", "256")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    config.ensure_dirs(settings)

    dim = settings.embed_dim
    monkeypatch.setattr(text_embedder, "embed_texts", lambda texts: [fake_embed_one(t, dim) for t in texts])
    monkeypatch.setattr(text_embedder, "embed_query", lambda text: fake_embed_one(text, dim))

    init_db_schema()
    conn = connect_db()
    try:
        init_vector_table(conn)
    finally:
        conn.close()

    yield settings
    config.get_settings.cache_clear()
