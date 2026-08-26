"""Span attributes are the leak path - a trace of a health app carries PHI."""
from __future__ import annotations

import pytest

from tara import config
from tara.execution_tracing.span_redaction import redact_span_attributes


@pytest.fixture
def redaction_on(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.integration
def test_string_values_are_redacted(redaction_on):
    redacted = redact_span_attributes({"question": "Does Michael Okonkwo have dental?"})
    assert "Michael Okonkwo" not in redacted["question"]


def test_numeric_values_pass_through_untouched(redaction_on):
    attributes = {"top_k": 6, "best_score": 0.88, "rerank_enabled": True}
    assert redact_span_attributes(attributes) == attributes


@pytest.mark.integration
def test_mixed_attributes_keep_their_keys(redaction_on):
    redacted = redact_span_attributes({"question": "Michael Okonkwo asked", "top_k": 6})
    assert set(redacted) == {"question", "top_k"}
    assert redacted["top_k"] == 6


def test_empty_attribute_map_returns_empty(redaction_on):
    assert redact_span_attributes({}) == {}
