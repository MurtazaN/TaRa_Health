"""Span attributes are the leak path - a trace of a health app carries PHI."""
from __future__ import annotations

import pytest

from tara import config
from tara.execution_tracing.span_redaction import redact_span_attributes


@pytest.fixture
def settings_cache_isolated(monkeypatch):
    """Clear the cached `Settings` so each test sees a fresh read of the env."""
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.integration
def test_string_values_are_redacted(settings_cache_isolated):
    redacted = redact_span_attributes({"question": "Does Michael Okonkwo have dental?"})
    assert "Michael Okonkwo" not in redacted["question"]


def test_numeric_values_pass_through_untouched(settings_cache_isolated):
    attributes = {"top_k": 6, "best_score": 0.88, "rerank_enabled": True}
    expected = dict(attributes)
    redacted = redact_span_attributes(attributes)
    assert redacted == expected
    assert attributes == expected      # the caller's dict is not mutated
    assert redacted is not attributes  # a new dict, not the same object


@pytest.mark.integration
def test_mixed_attributes_keep_their_keys(settings_cache_isolated):
    redacted = redact_span_attributes({"question": "Michael Okonkwo asked", "top_k": 6})
    assert set(redacted) == {"question", "top_k"}
    assert redacted["top_k"] == 6


def test_empty_attribute_map_returns_a_new_empty_map(settings_cache_isolated):
    empty_attributes: dict[str, object] = {}
    redacted = redact_span_attributes(empty_attributes)
    assert redacted == {}
    assert redacted is not empty_attributes


@pytest.mark.integration
def test_sequence_valued_attributes_are_redacted(settings_cache_isolated):
    redacted = redact_span_attributes({"excerpts": ["Michael Okonkwo has a dental claim"]})
    assert "Michael Okonkwo" not in redacted["excerpts"][0]


@pytest.mark.integration
def test_bytes_valued_attributes_are_redacted(settings_cache_isolated):
    """OTel accepts `bytes` and decodes it to a plain string on the span, so a
    bytes attribute leaks exactly like a raw string would. `ingest_document`
    holds the uploaded document's raw bytes, which makes this one careless
    `record_span_attribute(span, "head", file_bytes[:200])` away from live.
    """
    redacted = redact_span_attributes({"raw": b"Member Michael Okonkwo id XQZ8842190"})
    assert isinstance(redacted["raw"], bytes)
    assert b"Michael Okonkwo" not in redacted["raw"]


@pytest.mark.integration
def test_bytes_nested_in_a_sequence_are_redacted(settings_cache_isolated):
    redacted = redact_span_attributes({"heads": [b"Michael Okonkwo signed here"]})
    assert isinstance(redacted["heads"][0], bytes)
    assert b"Michael Okonkwo" not in redacted["heads"][0]
