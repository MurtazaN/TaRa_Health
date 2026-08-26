# Epic 0 · M3 — execution_tracing

- **Parent:** [Epic 0 — Foundation](README.md) — overview · decisions · build order · global constraints.
- **Seams:** depends on [M1](M1_repo_restructure.md) and on `redact_phi()` from [M2](M2_phi_redaction.md). Instruments Epic 1 [M1 ingestion](../epic1_grounded_qa/M1_ingestion_pipeline.md) and [M3 retrieval](../epic1_grounded_qa/M3_retrieval.md); the answering spans land with Epic 1 M4 per [M4 §3.1](M4_epic1_handoff.md).

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make a request's internal execution visible as a trace, so answer quality can be attributed to retrieval or to the model rather than guessed at.

**Architecture:** A new `execution_tracing` plane configures OpenTelemetry and exposes one `traced_span()` context manager. Every string attribute passes through M2's `redact_phi()` *at set time*, so protected health information never enters a span. Arize Phoenix runs as a second Compose service and receives spans over OTLP. Tracing is off by default.

**Design sections:** [Epic 0 README](README.md) §5 row 2, §6.1, §7, §8.1

**Tech Stack:** OpenTelemetry Python SDK · OTLP HTTP exporter · Arize Phoenix

**Prerequisite:** [M2](M2_phi_redaction.md) must be complete. `redact_span_attributes()` calls `redact_phi()` directly; building this module first would mean either a wide-open trace or a stub.

## Global Constraints

- See [README.md](README.md#global-constraints). Every task's requirements implicitly include that section.
- **This module is behaviour-neutral.** With `TARA_TRACING_ENABLED=false` (the default) nothing changes; the suite must stay at its M2-completion count plus the tests this module adds.
- **Redaction happens at attribute-set time, not at export time.** A value that never enters a span cannot leak through a misconfigured exporter or a backend swapped in later.
- **Span attributes carry counts, scores, and identifiers — never chunk text or filenames.**

## File Structure

Every file the module ships, as built — rows 8-10 are test artifacts added beyond the plan, and rows 11-19 are files outside the plane that this module modifies.

| # | Path | Responsibility |
|---|---|---|
| 1 | `backend/src/tara/execution_tracing/__init__.py` | Empty, per the existing package convention. |
| 2 | `backend/src/tara/execution_tracing/span_redaction.py` | `redact_span_attributes(dict) -> dict` — redacts `str` and `bytes`, at the top level and one level inside a `list`/`tuple`. |
| 3 | `backend/src/tara/execution_tracing/tracer_setup.py` | `configure_tracing()` (lock-guarded, idempotent, warns when tracing is on with redaction off), `_build_tracer_provider()`, `get_tracer()`. |
| 4 | `backend/src/tara/execution_tracing/span_emitter.py` | `traced_span()` and `record_span_attribute()` — the only way this app makes spans. |
| 5 | `backend/tests/execution_tracing/__init__.py` | Empty. |
| 6 | `backend/tests/execution_tracing/test_span_redaction.py` | Redaction-of-attributes tests, including the `str`/`bytes` sequence cases. |
| 7 | `backend/tests/execution_tracing/test_span_emitter.py` | Span emission tests, against a real in-memory exporter. |
| 8 | `backend/tests/execution_tracing/test_tracer_setup.py` | **Beyond plan** (deviation 9). Disabled path, latch ordering, provider construction, enabled path, idempotency, and the redaction-off warning. |
| 9 | `backend/tests/execution_tracing/test_span_discipline.py` | **Beyond plan** (deviations 8, 11). Source scan: no module outside `span_emitter.py` creates or mutates a raw span. |
| 10 | `backend/tests/execution_tracing/test_pipeline_instrumentation.py` | **Beyond plan** (deviation 7). Asserts the seven span names, their attributes, and that no span carries PHI. |
| 11 | `backend/pyproject.toml` | OTel SDK and OTLP-over-HTTP exporter dependencies (Task 1). |
| 12 | `backend/src/tara/config.py` | `tracing_enabled`, `otlp_endpoint`, `service_name` (Task 1). |
| 13 | `.env.example` | The three tracing keys, plus the note on the unreachable-collector shutdown delay (deviation 16). |
| 14 | `backend/src/tara/web_app.py` | `configure_tracing()` as the first statement of `main()`. |
| 15 | `backend/src/tara/document_ingestion/ingestion_pipeline.py` | Ingestion spans (Task 5). |
| 16 | `backend/src/tara/semantic_search/chunk_retriever.py` | Retrieval spans (Task 5). |
| 17 | `deployment/docker/compose.yaml` | `phoenix` service, `phoenix-data` volume, `PHOENIX_WORKING_DIR`, and the backend's tracing env. |
| 18 | `CLAUDE.md` | The tracing plane's cross-cutting constraint. |
| 19 | `docs/epic0_foundation/README.md` | Status, build-order row, and §8.1 Compose services. |

---

### Task 1: Add the OpenTelemetry dependencies and tracing settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/tara/config.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: M1's repaired manifest; M2's completed redaction module.
- Produces: `Settings.tracing_enabled: bool`, `Settings.otlp_endpoint: str`, `Settings.service_name: str`. Tasks 3 and 6 read these.

**Context an engineer needs:**
- The Presidio dependencies and the `phi_redaction_*` settings already landed in [M2](M2_phi_redaction.md) Task 1. Do not re-add them.
- Tracing defaults to **off** because a span carries the user's question and retrieved document text. Redaction is the second line of defence, not the first.

- [x] **Step 1: Add the dependencies**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    # Execution tracing (vendor-neutral OTLP; the backend is a config swap)
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
```

**Deliberately not added:** `openinference-semantic-conventions` supplies attribute names for *model-call* spans (prompt, completion, token counts). This module instruments ingestion and retrieval, which have no model-call spans, so it would be a dependency with no call site. It arrives with Epic 1 M4 — see [M4 §3.1](M4_epic1_handoff.md).

**Also deliberately not added:** OpenLLMetry. See [README §11](README.md) for the recorded reasoning and its revisit trigger.

- [x] **Step 2: Add the settings**

In `backend/src/tara/config.py`, add inside `class Settings`, directly after the PHI-redaction block M2 created:

```python
    # ---- Execution tracing (README §6.1) ----
    # Off by default: a span carries the question and retrieved document text.
    # `span_redaction` strips PHI before any value reaches a span, so a trace
    # shows retrieval behaviour without carrying identity.
    tracing_enabled: bool = False
    otlp_endpoint: str = "http://localhost:6006/v1/traces"
    service_name: str = "tara-backend"
```

- [x] **Step 3: Document the settings**

Append to `.env.example`:

```bash
# ---- Execution tracing ----
# Off by default. Spans carry the question and retrieved text; PHI redaction
# runs before any value reaches a span, but tracing is still opt-in.
TARA_TRACING_ENABLED=false
TARA_OTLP_ENDPOINT=http://localhost:6006/v1/traces
TARA_SERVICE_NAME=tara-backend
```

- [x] **Step 4: Install and verify nothing changed**

```bash
uv pip install -e "./backend[dev]"
cd backend && python -m pytest -q 2>&1 | grep -E "passed|failed" | tail -1
```

- [x] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/tara/config.py .env.example
git commit -m "build: add OpenTelemetry dependencies and tracing settings

Tracing defaults to off because a span carries the question and the
retrieved document text. Instrumentation is vendor-neutral OTLP, so the
viewing backend is an endpoint change rather than a code change."
```

---

### Task 2: Build the span redaction helper

**Files:**
- Create: `backend/src/tara/execution_tracing/__init__.py` (empty)
- Create: `backend/src/tara/execution_tracing/span_redaction.py`
- Test: `backend/tests/execution_tracing/__init__.py` (empty)
- Test: `backend/tests/execution_tracing/test_span_redaction.py`

**Interfaces:**
- Consumes: `redact_phi(text) -> str` from [M2](M2_phi_redaction.md).
- Produces: `redact_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]`. Task 4's `traced_span()` calls it.

**Context an engineer needs:**
- Non-string values pass through untouched. Counts, scores, and token totals carry no identity, and they are precisely the numbers a trace exists to show.
- This runs before the value reaches the span, which is stronger than redacting on export.

- [x] **Step 1: Write the failing tests**

Create `backend/tests/execution_tracing/__init__.py` (empty file), then `backend/tests/execution_tracing/test_span_redaction.py`:

```python
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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_redaction.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tara.execution_tracing'`

- [x] **Step 3: Write the implementation**

Create `backend/src/tara/execution_tracing/__init__.py` as an empty file, then `backend/src/tara/execution_tracing/span_redaction.py`:

```python
"""Strips PHI out of span attributes before they reach a span.

Runs at attribute-set time rather than at export time: a value that never
enters a span cannot leak through a misconfigured exporter or a backend
swapped in later.
"""
from __future__ import annotations

from typing import Any

from tara.phi_redaction import redact_phi


def redact_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Return `attributes` with every string value PHI-redacted.

    Non-string values pass through untouched — counts, scores, and durations
    carry no identity, and they are the numbers a trace exists to show.
    """
    return {
        attribute_name: (
            redact_phi(attribute_value)
            if isinstance(attribute_value, str)
            else attribute_value
        )
        for attribute_name, attribute_value in attributes.items()
    }
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_redaction.py -q`
Expected: `4 passed`

- [x] **Step 5: Commit**

```bash
git add backend/src/tara/execution_tracing/ backend/tests/execution_tracing/
git commit -m "feat: redact span attributes at set time

Applies phi_redaction to every string attribute before it reaches a
span. Numeric values pass through - they carry no identity and are the
numbers a trace exists to show.

Set-time rather than export-time redaction, so a value that never
enters a span cannot leak through a swapped exporter."
```

---

### Task 3: Configure the tracer provider

**Files:**
- Create: `backend/src/tara/execution_tracing/tracer_setup.py`
- Modify: `backend/src/tara/web_app.py` (call `configure_tracing()` in `main()`)

**Interfaces:**
- Consumes: `Settings.tracing_enabled`, `Settings.otlp_endpoint`, `Settings.service_name` from Task 1.
- Produces: `configure_tracing() -> None` and `get_tracer() -> Tracer`. Task 4's `traced_span()` calls `get_tracer()`.

**Context an engineer needs:**
- `configure_tracing()` must be idempotent and safe to call when tracing is disabled — that is what keeps this phase behaviour-neutral.
- `get_tracer()` is safe to call before configuration; OpenTelemetry returns a no-op tracer, so instrumented code never has to check whether tracing is on.
- The provider is installed in `main()`, the composition root — not at import time, which would fire during tests.

- [x] **Step 1: Write the implementation**

Create `backend/src/tara/execution_tracing/tracer_setup.py`:

```python
"""Installs the OpenTelemetry tracer provider once per process.

Tracing is opt-in because a span carries the user's question and retrieved
document text. Instrumentation is vendor-neutral OpenTelemetry, so the viewing
backend (Phoenix by default, Langfuse as a documented swap) is an endpoint
change rather than a code change — the same rule `LLMClient` follows for models.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from tara.config import get_settings

_TRACER_NAME = "tara"
_is_tracing_configured = False


def configure_tracing() -> None:
    """Install the tracer provider. Idempotent; a no-op when tracing is disabled.

    Called from the composition root rather than at import time, so importing
    the package never opens a network exporter.
    """
    global _is_tracing_configured
    if _is_tracing_configured:
        return
    _is_tracing_configured = True

    settings = get_settings()
    if not settings.tracing_enabled:
        return

    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name}),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)),
    )
    trace.set_tracer_provider(tracer_provider)


def get_tracer() -> trace.Tracer:
    """Return the application tracer.

    Safe before `configure_tracing()`: OpenTelemetry returns a no-op tracer, so
    instrumented code never has to check whether tracing is enabled.
    """
    return trace.get_tracer(_TRACER_NAME)
```

- [x] **Step 2: Wire it into the composition root**

In `backend/src/tara/web_app.py`, inside `main()`, add the import and the call as the **first** statement in the function body, before `ensure_data_dirs()`:

```python
    from tara.execution_tracing.tracer_setup import configure_tracing

    configure_tracing()  # before anything else, so startup work is traced too
```

- [x] **Step 3: Verify tracing stays off by default**

```bash
cd backend && python -c "
from tara.execution_tracing.tracer_setup import configure_tracing, get_tracer
configure_tracing()
with get_tracer().start_as_current_span('probe') as span:
    print('recording:', span.is_recording())
"
```

Expected: `recording: False` — the no-op tracer, because `tracing_enabled` defaults to false.

- [x] **Step 4: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: the M2-completion count plus this module's new tests.

- [x] **Step 5: Commit**

```bash
git add backend/src/tara/execution_tracing/tracer_setup.py backend/src/tara/web_app.py
git commit -m "feat: configure the OpenTelemetry tracer provider

Idempotent, opt-in, and installed from the composition root rather
than at import time so importing the package never opens an exporter.

get_tracer() is safe before configuration - OTel returns a no-op
tracer - so instrumented code never branches on whether tracing is on."
```

---

### Task 4: Build the span emitter

**Files:**
- Create: `backend/src/tara/execution_tracing/span_emitter.py`
- Test: `backend/tests/execution_tracing/test_span_emitter.py`

**Interfaces:**
- Consumes: `get_tracer()` from Task 3, `redact_span_attributes()` from Task 2.
- Produces: `traced_span(span_name: str, **attributes) -> Iterator[Span]` and `record_span_attribute(span, attribute_name, attribute_value) -> None`. Task 5 calls both.

**Context an engineer needs:**
- `traced_span()` is the **only** way this application creates spans. Centralizing it is what guarantees redaction cannot be forgotten at a call site.
- The test uses OpenTelemetry's `InMemorySpanExporter` with a `SimpleSpanProcessor`, so it asserts on real spans without a network call or a running Phoenix.
- Attribute names follow OpenInference conventions where one exists; project-specific names are used otherwise.

- [x] **Step 1: Write the failing tests**

Create `backend/tests/execution_tracing/test_span_emitter.py`:

```python
"""traced_span is the only span-creation path, so redaction cannot be skipped."""
from __future__ import annotations

import pytest
from opentelemetry import trace
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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_emitter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tara.execution_tracing.span_emitter'`

- [x] **Step 3: Write the implementation**

Create `backend/src/tara/execution_tracing/span_emitter.py`:

```python
"""Emits one named, timed span per unit of work, with PHI-redacted attributes.

`traced_span()` is the single way this application creates spans. Centralizing
creation is what guarantees redaction cannot be forgotten at a call site — a
per-call-site `set_attribute` would eventually leak.

OTel's `start_as_current_span` defaults to recording an escaping exception's
message and stacktrace, and copying the message into the span status
description — none of which passes through `redact_span_attributes()`. An
ingestion error carries the uploaded filename (e.g. a member id or a name
joined with underscores), and redaction cannot be trusted to clean it:
Presidio does not recognise underscore-joined names, so the filename would
reach the span unredacted. Those defaults are disabled here; only the
exception's type — diagnostic and identity-free — is recorded.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry.trace import Span, Status, StatusCode

from tara.execution_tracing.span_redaction import redact_span_attributes
from tara.execution_tracing.tracer_setup import get_tracer


@contextmanager
def traced_span(span_name: str, /, **attributes: Any) -> Iterator[Span]:
    """Open a span named `span_name`, carrying `attributes` with PHI removed.

    A no-op tracer is returned when tracing is disabled, so callers never branch.
    `span_name` is positional-only so it cannot collide with an attribute of
    the same name passed through `**attributes`.

    An exception escaping the `with` block is recorded by type only — its
    message and stacktrace are dropped rather than redacted, because a
    filename-bearing message cannot be trusted to come back clean.
    """
    with get_tracer().start_as_current_span(
        span_name, record_exception=False, set_status_on_exception=False,
    ) as span:
        for attribute_name, attribute_value in redact_span_attributes(attributes).items():
            span.set_attribute(attribute_name, attribute_value)
        try:
            yield span
        except BaseException as raised_error:
            span.set_status(Status(StatusCode.ERROR, type(raised_error).__qualname__))
            span.add_event("exception", {"exception.type": type(raised_error).__qualname__})
            raise


def record_span_attribute(span: Span, attribute_name: str, attribute_value: Any) -> None:
    """Set one attribute on an already-open span, redacting it first.

    Needed for values only known at the end of a step — a result count, an
    answer — which cannot be passed to `traced_span()` up front.

    OTel silently drops attribute values of an unsupported type (`None`, a
    `dict`, ...): it logs a warning to stderr and records nothing for that
    attribute rather than raising, so a caller passing such a value gets no
    attribute on the span and no exception telling it why.
    """
    redacted_attributes = redact_span_attributes({attribute_name: attribute_value})
    span.set_attribute(attribute_name, redacted_attributes[attribute_name])
```


> **As built, this deviates from the code above.** Review of Task 4 found that
> OTel's `start_as_current_span()` defaults to `record_exception=True,
> set_status_on_exception=True`, which writes an escaping exception's message,
> its stacktrace, and the span status description onto the span **without**
> passing them through `redact_span_attributes()`. That is live, not
> theoretical: Task 5 wraps `ingest_document()` in a span, and
> `ingestion_pipeline.py` raises `IngestionError(f"No extractable text in
> '{filename}'.")` inside it — putting the uploaded filename on the span.
> Redaction cannot rescue it, because Presidio does not recognise
> underscore-joined names and real uploads are named that way
> (`redact_phi("Michael_Okonkwo_member_XQZ8842190.pdf")` returns the string
> unchanged). The message and stacktrace are therefore **dropped**, not
> redacted; only the exception type is recorded. The block above is the
> corrected, shipped version.


- [x] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_emitter.py -q`
Expected: `5 passed`

- [x] **Step 5: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: the M2-completion count plus this module's new tests.

- [x] **Step 6: Commit**

```bash
git add backend/src/tara/execution_tracing/span_emitter.py backend/tests/execution_tracing/test_span_emitter.py
git commit -m "feat: add traced_span, the single span-creation path

Centralizing span creation is what guarantees redaction cannot be
forgotten at a call site. record_span_attribute covers values only
known at the end of a step.

Tested against a real in-memory OTel exporter, so the assertions are
on actual spans rather than on a mock."
```

---

### Task 5: Instrument ingestion and retrieval

**Files:**
- Modify: `backend/src/tara/document_ingestion/ingestion_pipeline.py`
- Modify: `backend/src/tara/semantic_search/chunk_retriever.py`

**Interfaces:**
- Consumes: `traced_span()`, `record_span_attribute()` from Task 4.
- Produces: spans named `ingest_document`, `extract_text_spans`, `chunk_spans`, `embed_chunks`, `retrieve_chunks`, `embed_query`, `find_nearest_chunks`. Epic 1 M4 adds the answering spans.

**Context an engineer needs:**
- **Only ingestion and retrieval are instrumented in this module**, because they are the two flows that actually work today. `answer_question()` cannot run end to end — `screen_for_emergency()` raises `NotImplementedError` — so its spans land with Epic 1 M4 and M5.
- Import direction holds: capability → plane is permitted.
- Attributes must be primitives. Never put a chunk's text or a filename on a span; put counts, scores, and identifiers.

- [x] **Step 1: Instrument the retrieval path**

In `backend/src/tara/semantic_search/chunk_retriever.py`, add the import:

```python
from tara.execution_tracing.span_emitter import record_span_attribute, traced_span
```

Wrap the body of `retrieve_chunks()`. The existing logic is unchanged; only the `with` blocks and the attribute calls are new:

```python
def retrieve_chunks(question: str, doc_type_hint: str | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    with traced_span("retrieve_chunks", top_k=settings.top_k) as retrieval_span:
        conn = connect_db()
        try:
            vector_index.load_vector_extension(conn)
            if not _is_index_ready(conn):
                record_span_attribute(retrieval_span, "index_ready", False)
                return []
            with traced_span("embed_query"):
                question_embedding = text_embedder.embed_query(question)
            # Unfiltered for now; the doc-type filter arrives in Slice 6.
            with traced_span("find_nearest_chunks") as search_span:
                nearest_hits = vector_index.find_nearest_chunks(
                    conn, question_embedding, settings.top_k,
                )
                record_span_attribute(search_span, "hit_count", len(nearest_hits))
            results: list[RetrievedChunk] = []
            for chunk_id, distance in nearest_hits:
                chunk_with_source = chunk_records.fetch_chunk_with_filename(conn, chunk_id)
                if chunk_with_source is None or chunk_with_source.document_status != "indexed":
                    continue  # only indexed documents are visible to retrieval (§3.1g)
                results.append(RetrievedChunk(
                    chunk=chunk_with_source.chunk,
                    filename=chunk_with_source.source_filename,
                    score=_l2_distance_to_cosine_similarity(distance),
                ))
        finally:
            conn.close()

        # Abstention guard: weak best hit => treat as unsupported (§3.4).
        best_score = results[0].score if results else 0.0
        record_span_attribute(retrieval_span, "best_score", best_score)
        if not results or best_score < settings.abstain_threshold:
            record_span_attribute(retrieval_span, "abstained", True)
            return []
        record_span_attribute(retrieval_span, "abstained", False)
        record_span_attribute(retrieval_span, "returned_count", len(results))
        return results
```

- [x] **Step 2: Instrument the ingestion path**

In `backend/src/tara/document_ingestion/ingestion_pipeline.py`, add the import:

```python
from tara.execution_tracing.span_emitter import record_span_attribute, traced_span
```

Wrap the three failure-prone steps inside `ingest_document()`. Replace:

```python
            text_spans = extract_text_spans(blob_path)
            if not text_spans:
                raise IngestionError(f"No extractable text in '{filename}'.")
            chunks = chunk_spans(doc_id, text_spans)
            chunk_embeddings = text_embedder.embed_texts([chunk.text for chunk in chunks])
```

With:

```python
            with traced_span("extract_text_spans") as extraction_span:
                text_spans = extract_text_spans(blob_path)
                record_span_attribute(extraction_span, "span_count", len(text_spans))
            if not text_spans:
                raise IngestionError(f"No extractable text in '{filename}'.")
            with traced_span("chunk_spans") as chunking_span:
                chunks = chunk_spans(doc_id, text_spans)
                record_span_attribute(chunking_span, "chunk_count", len(chunks))
            with traced_span("embed_chunks", chunk_count=len(chunks)):
                chunk_embeddings = text_embedder.embed_texts([chunk.text for chunk in chunks])
```

Then wrap the whole function body in an outer span by inserting immediately after `content_hash = hashlib.sha256(file_bytes).hexdigest()`:

```python
    with traced_span("ingest_document", byte_count=len(file_bytes), replace=replace):
```

and indenting the remainder of the function body one level.

- [x] **Step 3: Verify behaviour is unchanged**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: the M2-completion count plus this module's new tests. — instrumentation must not change any test outcome.

- [x] **Step 4: Lint and typecheck**

```bash
make lint && make typecheck
```

Expected: both clean.

- [x] **Step 5: Commit**

```bash
git add backend/src/tara/semantic_search/chunk_retriever.py backend/src/tara/document_ingestion/ingestion_pipeline.py
git commit -m "feat: instrument the ingestion and retrieval paths

Spans for ingest_document, extract_text_spans, chunk_spans,
embed_chunks, retrieve_chunks, embed_query, and find_nearest_chunks,
carrying counts and scores only - never chunk text or filenames.

Answering spans are deliberately absent: answer_question cannot run
end to end until M5 implements screen_for_emergency, so they land in
Epic 1 M4 alongside it."
```

---

### Task 6: Add Phoenix to the stack and verify a trace end to end

**Files:**
- Modify: `deployment/docker/compose.yaml`
- Modify: `.env.example`
- Modify: `CLAUDE.md` (Architecture section — document the tracing plane)

**Interfaces:**
- Consumes: everything above.
- Produces: a running Phoenix at `http://localhost:6006` receiving redacted spans.

**Context an engineer needs:**
- Phoenix listens on 6006 for the user interface and OTLP over HTTP, and on 4317 for OTLP over gRPC. This project uses the HTTP exporter, so 6006 is the one that matters.
- From inside the backend container the endpoint is `http://phoenix:6006/v1/traces`; from the host it is `http://localhost:6006/v1/traces`.
- Because `/ask` cannot run until M5, **the end-to-end verification uses `/upload`**, which works today.
- **Publish loopback-only**, the same fix Epic 0 M1's final-review fix wave applies to the backend service (F1): Phoenix will hold span data derived from health documents, and an all-interfaces publish (`"6006:6006"`) would expose it to anyone on the local network. Recorded here so the fix is not re-litigated when this task is actually built.

- [x] **Step 1: Add the Phoenix service**

In `deployment/docker/compose.yaml`, add to `services`:

```yaml
  phoenix:
    image: arizephoenix/phoenix:latest
    ports:
      - "127.0.0.1:6006:6006"   # UI + OTLP over HTTP; loopback-only, same reasoning as the backend service
      - "127.0.0.1:4317:4317"   # OTLP over gRPC; loopback-only
    volumes:
      - phoenix-data:/mnt/data
```

Add to the `tara-backend` service's `environment` block:

```yaml
      TARA_TRACING_ENABLED: "true"
      TARA_OTLP_ENDPOINT: "http://phoenix:6006/v1/traces"
```

Add to the `tara-backend` service:

```yaml
    depends_on:
      - phoenix
```

Add to the top-level `volumes` block:

```yaml
  phoenix-data:
```

- [x] **Step 2: Document the new settings in .env.example** — **SUPERSEDED: verify only, append nothing.** Task 1 Step 3 already added the three tracing keys and M2 already added the PHI block. Running the block below verbatim duplicates three keys and pastes a weaker copy of M2's `TARA_PHI_REDACTION_NLP_MODEL` warning. Confirm each key appears exactly once and the PHI block is intact; leave the file unchanged.

Append to `.env.example`:

```bash
# ---- Execution tracing (spec: docs/epic0_foundation/README.md) ----
# Off by default. Spans carry the question and retrieved text, so PHI redaction
# runs before any value reaches a span.
TARA_TRACING_ENABLED=false
TARA_OTLP_ENDPOINT=http://localhost:6006/v1/traces
TARA_SERVICE_NAME=tara-backend

# ---- PHI redaction ----
TARA_PHI_REDACTION_ENABLED=true
# The spaCy model is pinned as a wheel dependency in pyproject.toml, not an
# env knob - see Epic 0 M2. Do not add TARA_PHI_REDACTION_NLP_MODEL here: an
# env var beats the config.py default, so a stale value would silently
# re-introduce a model-recall gap that was measured and fixed in M2.
```

- [x] **Step 3: Bring the stack up**

```bash
make up
sleep 15
curl -s -o /dev/null -w "phoenix:%{http_code}\n" http://127.0.0.1:6006/
curl -s -o /dev/null -w "backend:%{http_code}\n" http://127.0.0.1:8000/
```

Expected: `phoenix:200` and `backend:200`

- [x] **Step 4: Generate a trace by uploading a document**

```bash
cd backend && python -c "
import pymupdf
doc = pymupdf.open(); page = doc.new_page()
page.insert_text((72, 72), 'Member ID: XQZ8842190')
page.insert_text((72, 92), 'Michael Okonkwo specialist copay is \$40.')
open('/tmp/probe.pdf','wb').write(doc.tobytes()); doc.close()
"
curl -s -F "file=@/tmp/probe.pdf" http://127.0.0.1:8000/upload
```

Expected: a JSON body containing `doc_id`, `filename`, and `doc_type`.

- [x] **Step 5: Verify the trace arrived and is redacted** — **SUPERSEDED: do this programmatically, not in a browser.** Query Phoenix's REST API (`GET /v1/projects/default/spans`, plus `.../spans/otlpv1` for a raw-text scan) and assert all four items below in code. Item 4 is this module's acceptance criterion; eyeballing it verifies nothing and leaves no regression guard.

Open `http://localhost:6006` in a browser. Confirm all four:

1. A trace named `ingest_document` exists.
2. It has child spans `extract_text_spans`, `chunk_spans`, and `embed_chunks`.
3. `chunk_spans` carries a `chunk_count` attribute with a real number.
4. **No span attribute anywhere contains the strings `Michael Okonkwo` or `XQZ8842190`.**

Item 4 is the acceptance criterion for this module. If it fails, stop and fix redaction before proceeding.

- [x] **Step 6: Tear down and document the plane**

```bash
make down
```

In `CLAUDE.md`, add to the "Cross-cutting design constraints" list:

```markdown
- **Tracing is opt-in and redacted at set time.** `execution_tracing/` wraps OpenTelemetry; `traced_span()` is the only span-creation path, and it runs every string attribute through `phi_redaction` before the value reaches the span. Instrumentation is vendor-neutral OTLP, so the backend (Phoenix by default, Langfuse a documented swap) is an endpoint change, never a code change.
```

- [x] **Step 7: Commit**

```bash
git add deployment/docker/compose.yaml .env.example CLAUDE.md
git commit -m "feat: add self-hosted Phoenix and verify redacted tracing

Phoenix runs as a second Compose service on 6006. Self-hosting keeps
trace payloads on the device, which is what makes tracing compatible
with the local-first posture; set-time redaction protects the payload
itself.

Verified end to end via /upload, since /ask cannot run until M5."
```

---

## M3 acceptance

**Met 2026-08-25** on branch `feat/execution-tracing`.

- [x] `make test` reports **243 passed, 4 skipped, 16 xfailed** — the 214/4/16 baseline this module started from, plus 29 new tests, with no pre-existing test changed. (234/4/16 at the end of Task 6; the final fix round below added 8, and the scoped re-review that followed added 1 more.) (The plan said "the M2-completion count"; that predated M5, which merged to `main` first. 214/4/16 is the count M3 actually built on.)
- [x] `make lint` and `make typecheck` are clean.
- [x] With `TARA_TRACING_ENABLED=false` (the default), `get_tracer()` returns a non-recording span — asserted by `test_tracer_setup.py`, not just probed by hand.
- [x] `make up`, then an upload, produces an `ingest_document` trace in Phoenix with child spans `extract_text_spans`, `chunk_spans`, `embed_chunks`, and a real integer `chunk_count`.
- [x] No span attribute contains a person name or a member identifier — verified programmatically against Phoenix's REST API (see "As built" below), and guarded in the suite by `test_no_span_carries_phi` and `test_no_span_carries_an_exception_message`.

---

## As built — deviations from this plan

Sixteen deviations, each ruled during execution or in the whole-branch review, and recorded here so the next reader trusts the code over the plan. Deviations 1-9 were ruled per task; 10-16 came from the whole-branch review that ran after every task-level review had already passed.

| # | Plan said | As built | Why |
|---|---|---|---|
| 1 | Task 4 Step 3 creates the span with OTel's defaults | `record_exception=False, set_status_on_exception=False`; only the exception **type** is recorded | OTel's defaults wrote an escaping exception's message, stacktrace, and status description onto the span, bypassing redaction. Live via `ingest_document()`, which raises with the uploaded filename in the message. See the note in Task 4. |
| 2 | Task 3 sets `_is_tracing_configured = True` before the `tracing_enabled` check | Latch set **after** `trace.set_tracer_provider(...)` | The plan's ordering meant one call while disabled permanently prevented tracing from ever turning on, silently. Guarded by `test_disabled_call_does_not_latch_out_a_later_enable`. |
| 3 | `redact_span_attributes` redacts string values | Also recurses one level into `list`/`tuple` values | OTel's attribute contract permits `Sequence[str]`, so a string hiding in a list reached the span unredacted. Latent — no call site passes a list today. |
| 4 | Task 5 records `index_ready=False` on the not-ready retrieval path | Also records `abstained=True` there | Every other path records `abstained`, so a query for `abstained = true` meaning "returned nothing" silently undercounted. |
| 5 | Task 6 Step 2 appends a tracing block and a PHI block to `.env.example` | **Verify-only; nothing appended** | Task 1 Step 3 already added the three tracing keys, and M2 already added the PHI block with its `TARA_PHI_REDACTION_NLP_MODEL` warning. Running Step 2 verbatim duplicated three keys and pasted a weaker copy of M2's warning. |
| 6 | Task 6 Step 5 verifies the trace by opening Phoenix in a browser | A script queries Phoenix's REST API (`/v1/projects/default/spans` and `.../spans/otlpv1`) and asserts all four items in code | An acceptance criterion that is only eyeballed is not verified, and leaves no regression guard behind. |
| 7 | Tasks 5 adds no tests | Adds `test_pipeline_instrumentation.py` (5 tests) | Every span name and attribute was a string literal no assertion touched; after Task 6 there would have been no executable artifact anywhere asserting M3 met its own acceptance criterion. |
| 8 | — | Adds `test_span_discipline.py` | `traced_span()` yields the raw `Span`, so the "only span-creation path" guarantee was convention, not construction. The test fails, naming file and line, if any module outside `span_emitter.py` touches `.set_attribute(`, `.add_event(`, `.record_exception(`, or `.set_status(`. Widened by deviation 11 below. |
| 9 | Task 3 adds no tests | Adds `test_tracer_setup.py` | "Behaviour-neutral when tracing is off" was a Global Constraint backed only by a probe run once by hand. Shipped beyond plan at Task 3, then extended in the final fix round (deviations 13-14). |

**Deviations 10-16 come from the whole-branch review**, after every per-task review had passed. Each is a gap six task-level reviews looked straight past.

| # | Plan said | As built | Why |
|---|---|---|---|
| 10 | Deviation 3 redacts `str`, and `str` inside a `list`/`tuple` | Also redacts `bytes`, both top-level and inside a sequence | Deviation 3 reasoned from "OTel permits `Sequence[str]`" and stopped there. OTel's real `_VALID_ATTR_VALUE_TYPES` is `(bool, str, bytes, int, float)`, and OTel **decodes `bytes` to a plain string** on the span. Reproduced: `traced_span("t", raw=b"Member Michael Okonkwo id XQZ8842190")` landed verbatim. Latent — no call site passes bytes — but `ingest_document(filename, file_bytes)` holds the raw document bytes. |
| 11 | Deviation 8 scans four span-**mutation** calls | Also scans span **creation** — `.start_as_current_span(`, `.start_span(`, `get_tracer(` — with exemptions keyed per (pattern, file) | Deviation 8's threat model was the yielded raw `Span`, so every reviewer looked past the `attributes=` kwarg on the creation API. Reproduced: `start_as_current_span("ask", attributes={"question": "Is Michael Okonkwo covered?"})` puts PHI on a span unredacted and the mutation-only scan flagged nothing. `tracer_setup.py` is exempt for `get_tracer(` **only** — a blanket file exemption would reopen the creation hole inside the tracing plane itself. |
| 12 | Task 6 mounts `phoenix-data:/mnt/data` | Also sets `PHOENIX_WORKING_DIR: /mnt/data` on the `phoenix` service | Phoenix defaults its store to `$HOME/.phoenix`, so the declared volume received nothing: traces vanished on `make down`, and PHI-derived span data sat in an unmanaged container writable layer rather than the named volume anyone would purge. Six reviews read the Compose file; none looked inside the container. Verified in-container after the fix: `/mnt/data/phoenix.db` present, `~/.phoenix` absent. |
| 13 | Task 3 guards the latch with a plain check-then-act | `configure_tracing()`'s body runs under a module-level `threading.Lock`; `_build_tracer_provider()` is extracted and tested directly | Concurrent callers would each build a `BatchSpanProcessor`, leaving N-1 abandoned worker threads and HTTP sessions. Precautionary — only `main()` calls it today. The extraction exists so the enabled path is testable without a global `set_tracer_provider()` install, which would leak into the whole suite; coverage of `tracer_setup.py` went 76% -> 100%. |
| 14 | — | `configure_tracing()` emits both a `logging.error` and a `warnings.warn` when `tracing_enabled and not phi_redaction_enabled` | `redact_phi()` degrades to identity when redaction is off, announcing it with one easy-to-miss per-process warning; combined with tracing, raw strings reach spans. Deliberately a warning and **not** a refusal: `.env.example` sanctions disabling redaction "for local debugging on synthetic data", and tracing is exactly what you want on while doing that. |
| 15 | — | Docstring note: span **names** are never redacted and must be compile-time constants | `traced_span("ingest Michael_Okonkwo_member_XQZ8842190.pdf")` reaches the exporter with that name intact. Safe today — every name is a literal — but the module's promise reads as covering the whole span. No runtime redaction of the name was added: a name built from a runtime value is a design error to catch in review, not to paper over. |
| 16 | — | `.env.example` notes the unreachable-collector case | With `TARA_TRACING_ENABLED=true` and nothing listening at `TARA_OTLP_ENDPOINT`, process exit blocks a few seconds on export retries, with connection warnings on stderr. Ingestion and retrieval are unaffected and nothing raises — it degrades gracefully, but it surprises. No new setting was added. |

**Two limits worth knowing, demonstrated during execution rather than assumed:**

- **Redaction is not a backstop for filenames.** `redact_phi("Michael_Okonkwo_member_XQZ8842190.pdf")` returns the string completely unchanged — Presidio does not recognise underscore-joined names, and that is exactly how real uploads are named. Keeping such a value off the span is the only defence; running it through redaction is not.
- **`test_no_span_carries_phi` guards call-site discipline, not redaction.** After Task 5, not one span attribute is a string, so redaction is a no-op for these flows. That test proves no call site puts a PHI-bearing value on a span; `test_span_redaction.py` and the integration cases in `test_span_emitter.py` are what prove redaction works. Neither covers the other — a distinction that starts to matter when Epic 1 M4 adds the first string-valued attribute (the question, the answer).

**Recorded, deliberately not done here:**

- `doc_id` is absent from the `ingest_document` span, so a trace cannot be tied back to a stored document, and the idempotent dedup-hit path is attribute-identical to a fast failure. `doc_id` is a `uuid4().hex`, not PHI. Deferred to the Epic 1 M4 handoff.
- The `sqlite3.IntegrityError` dedup-race branch in `ingest_document()` has no test in the suite. Pre-existing; M3 re-indented it, and that re-indent is verified by AST comparison and by executing the other error paths, never by executing that branch.
- Ruff's isort (`I`) rules are not enabled, so import-group drift is caught only by review. Enabling them would reformat imports repo-wide — out of scope for a behaviour-neutral module.
