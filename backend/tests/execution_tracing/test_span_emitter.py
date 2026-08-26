"""traced_span is the only span-creation path, so redaction cannot be skipped."""
from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tara import config
from tara.execution_tracing.span_emitter import record_span_attribute, traced_span


@pytest.fixture
def captured_spans(monkeypatch):
    """Install a real in-memory tracer provider and hand back its exporter."""
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        "tara.execution_tracing.span_emitter.get_tracer",
        lambda: provider.get_tracer("tara"),
    )
    yield exporter
    config.get_settings.cache_clear()


def test_span_is_emitted_with_its_name(captured_spans):
    with traced_span("retrieve_chunks"):
        pass
    finished = captured_spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "retrieve_chunks"


def test_numeric_attributes_are_recorded_exactly(captured_spans):
    with traced_span("retrieve_chunks", top_k=6, best_score=0.88):
        pass
    attributes = captured_spans.get_finished_spans()[0].attributes
    assert attributes["top_k"] == 6
    assert attributes["best_score"] == pytest.approx(0.88)


@pytest.mark.integration
def test_string_attributes_are_redacted_before_reaching_the_span(captured_spans):
    with traced_span("ask_question", question="Is Michael Okonkwo covered?"):
        pass
    recorded_question = captured_spans.get_finished_spans()[0].attributes["question"]
    assert "Michael Okonkwo" not in recorded_question


@pytest.mark.integration
def test_late_attributes_are_also_redacted(captured_spans):
    with traced_span("ask_question") as span:
        record_span_attribute(span, "answer", "Michael Okonkwo pays $40.")
    recorded_answer = captured_spans.get_finished_spans()[0].attributes["answer"]
    assert "Michael Okonkwo" not in recorded_answer
    assert "$40" in recorded_answer


def test_exception_inside_the_span_propagates(captured_spans):
    with pytest.raises(ValueError):
        with traced_span("failing_step"):
            raise ValueError("boom")
    assert captured_spans.get_finished_spans()[0].name == "failing_step"
