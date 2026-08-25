"""Embedder unit tests: in-process call shape, the query/document prompt split,
unit-normalization, and the startup guards. The model is faked so these run
offline — the real model is 1.19 GB and must never be downloaded in CI."""
from __future__ import annotations

import math
import os

import pytest

from tara.semantic_search import text_embedder


class _FakeSentenceTransformer:
    """Records how it was called. Returns non-unit vectors on purpose."""

    max_seq_length = 512

    def __init__(self):
        self.calls: list[tuple[object, dict]] = []

    def encode(self, sentences, **kwargs):
        self.calls.append((sentences, kwargs))
        if isinstance(sentences, str):
            return [3.0, 4.0, 0.0]                       # norm 5 -> proves normalize
        return [[float(i + 1), 0.0, 0.0] for i, _ in enumerate(sentences)]


@pytest.fixture
def fake_model(monkeypatch):
    model = _FakeSentenceTransformer()
    # Patching the accessor also sidesteps its @lru_cache.
    monkeypatch.setattr(text_embedder, "_model", lambda: model)
    return model


@pytest.mark.unit
def test_embed_query_applies_the_query_prompt(fake_model):
    # THE critical assertion. Omitting prompt_name embeds a question as a document:
    # a valid unit vector in the wrong region, so retrieval favours passages that
    # RESEMBLE the question over passages that ANSWER it. Nothing raises.
    text_embedder.embed_query("what is my deductible?")
    _, kwargs = fake_model.calls[0]
    assert kwargs["prompt_name"] == "query"


@pytest.mark.unit
def test_embed_texts_applies_no_prompt(fake_model):
    # Documents use the model's empty "document" prompt, i.e. no prompt at all.
    text_embedder.embed_texts(["a", "b"])
    _, kwargs = fake_model.calls[0]
    assert "prompt_name" not in kwargs


@pytest.mark.unit
def test_embed_texts_preserves_order_and_normalizes(fake_model):
    out = text_embedder.embed_texts(["a", "b"])
    assert len(out) == 2
    for vector in out:
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-6)
    assert math.isclose(out[0][0], 1.0, rel_tol=1e-6)


@pytest.mark.unit
def test_embed_query_normalizes(fake_model):
    vector = text_embedder.embed_query("hello")
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-6)


@pytest.mark.unit
def test_embed_texts_empty_is_noop(fake_model):
    assert text_embedder.embed_texts([]) == []
    assert fake_model.calls == []


@pytest.mark.unit
def test_model_is_constructed_with_the_pinned_revision(monkeypatch):
    """Spec assertion 2. Every other test patches _model wholesale, so without
    this one nothing proves the revision pin is actually passed through."""
    captured: dict = {}

    class _RecordingSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            captured["model"] = model_name_or_path
            captured["kwargs"] = kwargs

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer",
                        _RecordingSentenceTransformer)
    text_embedder._model.cache_clear()
    text_embedder._model()
    text_embedder._model.cache_clear()

    assert captured["model"] == "Qwen/Qwen3-Embedding-0.6B"
    assert captured["kwargs"]["revision"] == "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    # Defaults false so a fresh install can fetch the weights once; the point is
    # that the flag is WIRED, so a host that must stay offline can set it instead
    # of silently pulling 1.19 GB on the first ingestion (M5 §4.3).
    assert captured["kwargs"]["local_files_only"] is False


@pytest.mark.unit
def test_offline_only_setting_reaches_the_model_loader(monkeypatch):
    captured: dict = {}

    class _RecordingSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            captured["kwargs"] = kwargs

    import sentence_transformers
    from tara import config
    monkeypatch.setenv("TARA_EMBED_MODEL_OFFLINE_ONLY", "true")
    config.get_settings.cache_clear()
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer",
                        _RecordingSentenceTransformer)
    text_embedder._model.cache_clear()
    text_embedder._model()
    text_embedder._model.cache_clear()
    config.get_settings.cache_clear()

    assert captured["kwargs"]["local_files_only"] is True


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("TARA_TEST_REAL_EMBED_MODEL"),
    reason="loads the real 1.19 GB model; opt in with TARA_TEST_REAL_EMBED_MODEL=1",
)
def test_real_model_loads_and_matches_configured_dimension():
    """Spec 9.5. The only test that touches the real weights. Never runs in CI.

    Print max_seq_length: Task 3's chunk sizing depends on it being comfortably
    above chunk_target_tokens, and this model ships no sentence_bert_config.json,
    so the effective value must be observed rather than assumed.
    """
    text_embedder._model.cache_clear()
    print(f"max_seq_length={text_embedder.model_max_sequence_length()}")
    assert len(text_embedder.embed_query("what is my deductible?")) == 1024
    text_embedder._model.cache_clear()


@pytest.mark.unit
def test_embed_texts_rejects_count_mismatch(monkeypatch):
    class _ShortModel:
        max_seq_length = 512

        def encode(self, sentences, **kwargs):
            return [[1.0, 0.0, 0.0]]        # fewer vectors than inputs

    monkeypatch.setattr(text_embedder, "_model", lambda: _ShortModel())
    with pytest.raises(RuntimeError, match="vectors"):
        text_embedder.embed_texts(["a", "b"])


@pytest.mark.unit
def test_verify_chunk_size_rejects_oversized_chunks(fake_model, monkeypatch):
    # sentence-transformers truncates SILENTLY past max_seq_length, so an
    # oversized chunk would lose text from its vector while the full text is
    # still stored and cited.
    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "5000")
    from tara import config
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="max_seq_length"):
        text_embedder.verify_chunk_size_fits_model()
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_verify_chunk_size_rejects_chunks_inside_the_safety_margin(fake_model, monkeypatch):
    """M5 §5.5: the guard leaves margin rather than sitting on the limit.

    500 fits under the fake model's 512-token limit but lands inside the 10%
    margin. Chunk sizes are estimated as characters // 4 and the chunker's inner
    loop can overshoot target_tokens by a whole line, so a bare `>` against the
    limit would pass here and still truncate a real chunk.
    """
    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "500")
    from tara import config
    config.get_settings.cache_clear()
    assert text_embedder.usable_chunk_token_ceiling() == 460   # 512 less 10%
    with pytest.raises(RuntimeError, match="safety margin"):
        text_embedder.verify_chunk_size_fits_model()
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_verify_chunk_size_accepts_a_fitting_chunk(fake_model, monkeypatch):
    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "200")
    from tara import config
    config.get_settings.cache_clear()
    text_embedder.verify_chunk_size_fits_model()   # must not raise
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_verify_embedding_dimension_rejects_a_mismatch(fake_model, monkeypatch):
    monkeypatch.setenv("TARA_EMBED_DIM", "1024")
    from tara import config
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="TARA_EMBED_DIM"):
        text_embedder.verify_embedding_dimension()   # fake returns dim 3
    config.get_settings.cache_clear()
