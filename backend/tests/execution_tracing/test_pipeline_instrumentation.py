"""Asserts the ingestion and retrieval instrumentation emits the spans it claims.

Task 5 attached spans to both pipelines, but every span name and attribute in
that change was a string literal no assertion touched: a rename, a dropped
`record_span_attribute()`, or a mis-scoped `with` block would have shipped
green. These tests pin the two span trees so the instrumentation is a property
of the codebase rather than a claim in a report.

`test_no_span_carries_phi` and `test_no_span_carries_an_exception_message` are
the load-bearing pair — they are M3's acceptance criterion, expressed as code.
"""
from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from tara.document_ingestion.ingestion_pipeline import ingest_document
from tara.local_data_stores import vector_index
from tara.semantic_search.chunk_retriever import retrieve_chunks

PHI_NAME = "Michael Okonkwo"
PHI_MEMBER_ID = "XQZ8842190"
PHI_FILENAME = "Michael_Okonkwo_member_XQZ8842190.pdf"


@pytest.fixture
def captured_spans(monkeypatch):
    """Route `traced_span()` at an in-memory exporter and hand back that exporter.

    Patching the `get_tracer` seam inside span_emitter — rather than calling
    `trace.set_tracer_provider()` — keeps the provider local to this test.
    A global install cannot be undone within a process and would leak into
    every later test in the session.
    """
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        "tara.execution_tracing.span_emitter.get_tracer",
        lambda: tracer_provider.get_tracer("tara"),
    )
    return exporter


def _spans_by_name(exporter: InMemorySpanExporter) -> dict[str, object]:
    """Map span name -> finished span. Each name is emitted at most once per flow."""
    return {span.name: span for span in exporter.get_finished_spans()}


def _parent_span_id(span) -> int | None:
    return span.parent.span_id if span.parent is not None else None


def _everything_recorded_on_the_spans(exporter: InMemorySpanExporter) -> str:
    """Every byte a span carries, flattened into one searchable string.

    Names, attribute names and values, event names, event attributes, and
    status descriptions — so a PHI assertion cannot pass by looking in the
    wrong place.
    """
    recorded_parts: list[str] = []
    for span in exporter.get_finished_spans():
        recorded_parts.append(span.name)
        recorded_parts.append(str(span.status.description))
        for attribute_name, attribute_value in (span.attributes or {}).items():
            recorded_parts.append(str(attribute_name))
            recorded_parts.append(str(attribute_value))
        for event in span.events:
            recorded_parts.append(event.name)
            for event_attribute_name, event_attribute_value in (event.attributes or {}).items():
                recorded_parts.append(str(event_attribute_name))
                recorded_parts.append(str(event_attribute_value))
    return "\n".join(recorded_parts)


def test_ingest_emits_the_expected_span_tree(offline_ingest_env, make_pdf, captured_spans):
    pdf_bytes = make_pdf([["Deductible is $1,500 per year.", "Copay is $40 per visit."]])

    ingest_document("benefits_summary.pdf", pdf_bytes)

    emitted_spans = _spans_by_name(captured_spans)
    assert set(emitted_spans) == {
        "ingest_document", "extract_text_spans", "chunk_spans", "embed_chunks",
    }
    ingest_span = emitted_spans["ingest_document"]
    assert _parent_span_id(ingest_span) is None, "ingest_document must be the only root"
    for child_span_name in ("extract_text_spans", "chunk_spans", "embed_chunks"):
        assert _parent_span_id(emitted_spans[child_span_name]) == ingest_span.context.span_id, (
            f"{child_span_name} must be parented by ingest_document"
        )

    chunk_count = emitted_spans["chunk_spans"].attributes["chunk_count"]
    assert isinstance(chunk_count, int) and chunk_count >= 1
    assert ingest_span.attributes["byte_count"] == len(pdf_bytes)
    assert ingest_span.attributes["replace"] is False


def test_retrieve_emits_the_expected_span_tree(offline_ingest_env, make_pdf, captured_spans):
    pdf_bytes = make_pdf([["Deductible is $1,500 per year.", "Copay is $40 per visit."]])
    ingest_document("benefits_summary.pdf", pdf_bytes)
    captured_spans.clear()  # drop the ingestion tree; assert only the retrieval one

    retrieved_chunks = retrieve_chunks("What is the deductible per year and the copay per visit?")

    assert retrieved_chunks, "the fake embedder must score this question above the abstain floor"
    emitted_spans = _spans_by_name(captured_spans)
    assert set(emitted_spans) == {"retrieve_chunks", "embed_query", "find_nearest_chunks"}
    retrieval_span = emitted_spans["retrieve_chunks"]
    assert _parent_span_id(retrieval_span) is None, "retrieve_chunks must be the root"
    for child_span_name in ("embed_query", "find_nearest_chunks"):
        assert _parent_span_id(emitted_spans[child_span_name]) == retrieval_span.context.span_id

    retrieval_attributes = retrieval_span.attributes
    assert "top_k" in retrieval_attributes
    assert "best_score" in retrieval_attributes
    assert retrieval_attributes["abstained"] is False
    assert retrieval_attributes["returned_count"] == len(retrieved_chunks)


def test_retrieve_records_abstained_when_the_index_is_not_ready(
    offline_ingest_env, captured_spans,
):
    """"Returned nothing" must be one queryable condition, not two.

    An empty index returns `[]` just as an abstention does. If only the
    abstention path set `abstained`, a trace query for `abstained = true`
    would silently undercount the retrievals that produced no answer.
    """
    assert retrieve_chunks("What is the deductible?") == []

    retrieval_span = _spans_by_name(captured_spans)["retrieve_chunks"]
    assert retrieval_span.attributes["index_ready"] is False
    assert retrieval_span.attributes["abstained"] is True


def test_no_span_carries_phi(offline_ingest_env, make_pdf, captured_spans):
    """M3's stated acceptance criterion: a trace of a real PHI-bearing document
    contains no PHI. If you are reading this because it failed, an attribute,
    an event, or a status description somewhere in the ingestion or retrieval
    path started carrying a filename, a question, or chunk text. The fix is to
    record a count or a score instead — not to relax this assertion.
    """
    pdf_bytes = make_pdf([[
        f"Member {PHI_NAME} id {PHI_MEMBER_ID}.",
        "Deductible is $1,500 per year.",
    ]])

    ingest_document(PHI_FILENAME, pdf_bytes)
    retrieve_chunks(f"Is {PHI_NAME} with member id {PHI_MEMBER_ID} covered?")

    everything_recorded = _everything_recorded_on_the_spans(captured_spans)
    assert PHI_NAME not in everything_recorded
    assert "Okonkwo" not in everything_recorded
    assert PHI_MEMBER_ID not in everything_recorded
    assert PHI_FILENAME not in everything_recorded


def test_no_span_carries_an_exception_message(
    offline_ingest_env, make_pdf, captured_spans, monkeypatch,
):
    """An escaping exception must reach the span as its bare type.

    This depends on `record_exception=False, set_status_on_exception=False` in
    span_emitter's `start_as_current_span()` call. OTel's defaults are the
    opposite, so a refactor that drops those two kwargs re-enables the leak
    silently — the pipeline still works and every other test still passes.
    """
    pdf_bytes = make_pdf([[f"Member {PHI_NAME} id {PHI_MEMBER_ID}."]])
    leaky_error_message = f"failed for {PHI_NAME} {PHI_MEMBER_ID}"

    def _raise_with_a_phi_bearing_message(*args, **kwargs):
        raise RuntimeError(leaky_error_message)

    monkeypatch.setattr(vector_index, "add_embeddings", _raise_with_a_phi_bearing_message)

    with pytest.raises(RuntimeError, match=PHI_MEMBER_ID):
        ingest_document(PHI_FILENAME, pdf_bytes)

    ingest_span = _spans_by_name(captured_spans)["ingest_document"]
    assert ingest_span.status.status_code is StatusCode.ERROR
    assert ingest_span.status.description == "RuntimeError"

    everything_recorded = _everything_recorded_on_the_spans(captured_spans)
    for leaked_fragment in (leaky_error_message, PHI_NAME, "Okonkwo", PHI_MEMBER_ID, "failed for"):
        assert leaked_fragment not in everything_recorded
