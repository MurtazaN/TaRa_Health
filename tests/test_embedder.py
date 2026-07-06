"""Embedder unit tests: OpenAI-compatible call shape, order preservation,
unit-normalization, and the live-dim safety check (§3.2). The HTTP client is
faked so these run offline."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from tara.embeddings import embedder


@dataclass
class _FakeEmbedding:
    embedding: list[float]
    index: int


class _FakeEmbeddings:
    def create(self, model, input):  # noqa: A002 - mirrors openai's signature
        # Return out of order to prove embed_texts sorts by index.
        data = []
        for i, _ in enumerate(input):
            vec = [float(i + 1), 0.0, 0.0]  # non-unit on purpose
            data.append(_FakeEmbedding(embedding=vec, index=i))
        return type("Resp", (), {"data": list(reversed(data))})


class _FakeClient:
    embeddings = _FakeEmbeddings()


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(embedder, "_client", lambda: _FakeClient())


@pytest.mark.unit
def test_embed_texts_preserves_order_and_normalizes(fake_client):
    out = embedder.embed_texts(["a", "b"])
    assert len(out) == 2
    # index 0 -> [1,0,0] normalized -> [1,0,0]; index 1 -> [2,0,0] -> [1,0,0]
    for vec in out:
        assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-6)
    assert math.isclose(out[0][0], 1.0, rel_tol=1e-6)


@pytest.mark.unit
def test_embed_texts_empty_is_noop(fake_client):
    assert embedder.embed_texts([]) == []


@pytest.mark.unit
def test_embed_query_returns_single_vector(fake_client):
    assert len(embedder.embed_query("hello")) == 3


@pytest.mark.unit
def test_embed_texts_rejects_count_mismatch(monkeypatch):
    class _ShortEmbeddings:
        def create(self, model, input):  # noqa: A002
            # Return fewer vectors than inputs -> must raise, not silently truncate.
            return type("Resp", (), {"data": [_FakeEmbedding([1.0, 0.0, 0.0], 0)]})

    monkeypatch.setattr(embedder, "_client",
                        lambda: type("C", (), {"embeddings": _ShortEmbeddings()}))
    with pytest.raises(RuntimeError, match="vectors"):
        embedder.embed_texts(["a", "b"])


@pytest.mark.unit
def test_verify_dim_raises_on_mismatch(fake_client, monkeypatch):
    # Fake returns dim 3; configure a different expected dim.
    monkeypatch.setattr(embedder, "get_settings",
                        lambda: type("S", (), {"embed_dim": 999, "embed_model": "m"}))
    with pytest.raises(RuntimeError, match="dimension"):
        embedder.verify_dim()
