"""traced_span is the only span-creation path, so redaction cannot be skipped."""
from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode
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
    finished = captured_spans.get_finished_spans()[0]
    assert finished.name == "failing_step"
    assert finished.status.status_code is StatusCode.ERROR
    recorded_events = {event.name: dict(event.attributes) for event in finished.events}
    assert recorded_events["exception"]["exception.type"] == "ValueError"
    assert "exception.message" not in recorded_events["exception"]
    assert "exception.stacktrace" not in recorded_events["exception"]


def test_exception_message_with_a_phi_bearing_filename_does_not_reach_the_span(captured_spans):
    """The real leak: an ingestion error's message can carry the uploaded filename.

    `redact_phi()` does not recognise underscore-joined names, so a filename
    like this one cannot be cleaned by redaction — it must never reach the
    span in the first place. Guards against a regression back to OTel's
    default `record_exception=True`/`set_status_on_exception=True` behavior.
    """
    with pytest.raises(ValueError):
        with traced_span("failing_step"):
            raise ValueError("No extractable text in 'Michael_Okonkwo_member_XQZ8842190.pdf'.")
    finished = captured_spans.get_finished_spans()[0]
    recorded_events = {event.name: dict(event.attributes) for event in finished.events}
    assert "Okonkwo" not in str(finished.status.description)
    assert "XQZ8842190" not in str(finished.status.description)
    for event_attributes in recorded_events.values():
        for attribute_value in event_attributes.values():
            assert "Okonkwo" not in str(attribute_value)
            assert "XQZ8842190" not in str(attribute_value)
