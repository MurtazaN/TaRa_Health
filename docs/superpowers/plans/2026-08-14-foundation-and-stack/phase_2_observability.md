# Phase 2 — Observability

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make a request's internal execution visible as a trace, with protected health information stripped before it ever enters a span.

**Architecture:** A kernel-level `phi_redaction` module wraps Presidio. A new `execution_tracing` plane configures OpenTelemetry and exposes one `traced_span()` context manager that redacts every string attribute *at set time*. Arize Phoenix runs as a second Compose service and receives spans over OTLP. Tracing is off by default.

**Spec:** [../../specs/2026-08-14-foundation-and-stack-design.md](../../specs/2026-08-14-foundation-and-stack-design.md) §5, §6.2, §7, §8.1

**Tech Stack:** OpenTelemetry Python SDK · OpenInference semantic conventions · Presidio (analyzer + anonymizer) · spaCy `en_core_web_sm` · Arize Phoenix

## Global Constraints

- See [README.md](README.md#global-constraints). Every task's requirements implicitly include that section.
- **Phase 2 is behaviour-neutral.** With `TARA_TRACING_ENABLED=false` (the default) nothing changes; the test suite must stay at `67 passed, 3 skipped` plus the new tests this phase adds.
- **Redaction happens at attribute-set time, not at export time.** A value that never enters a span cannot leak through a misconfigured exporter.

## File Structure

| # | Path | Responsibility |
|---|---|---|
| 1 | `backend/src/tara/phi_redaction.py` | Kernel. Presidio wrapper: `redact_phi(text) -> str`. |
| 2 | `backend/src/tara/execution_tracing/__init__.py` | Empty, per the existing package convention. |
| 3 | `backend/src/tara/execution_tracing/tracer_setup.py` | Plane. Installs the tracer provider once; `get_tracer()`. |
| 4 | `backend/src/tara/execution_tracing/span_redaction.py` | Plane. `redact_span_attributes(dict) -> dict`. |
| 5 | `backend/src/tara/execution_tracing/span_emitter.py` | Plane. `traced_span()` context manager — the only way this app makes spans. |
| 6 | `backend/tests/test_phi_redaction.py` | Kernel tests. |
| 7 | `backend/tests/execution_tracing/test_span_redaction.py` | Redaction-of-attributes tests. |
| 8 | `backend/tests/execution_tracing/test_span_emitter.py` | Span emission tests, using an in-memory exporter. |

---

### Task 1: Add the observability dependencies and settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/tara/config.py`
- Modify: `deployment/local/bootstrap.sh`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: phase 1 Task 2's repaired manifest.
- Produces: `Settings.tracing_enabled: bool`, `Settings.otlp_endpoint: str`, `Settings.service_name: str`, `Settings.phi_redaction_enabled: bool`, `Settings.phi_redaction_nlp_model: str`. Every later task in this phase reads these.

**Context an engineer needs:**
- **Presidio needs a spaCy language model at runtime.** Its default is `en_core_web_lg` (~600 MB). This plan pins `en_core_web_sm` (~12 MB) instead, configured explicitly, so a laptop install and a CI runner both stay light and deterministic. Accuracy improves with `en_core_web_lg`; swapping is a one-setting change, which is why the model name is configuration.
- Every new setting defaults to off or safe, so this task alone changes nothing.

- [ ] **Step 1: Add the dependencies**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    # Execution tracing (vendor-neutral; the backend is a config swap)
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",

    # PHI redaction before any span export or hosted egress
    "presidio-analyzer>=2.2",
    "presidio-anonymizer>=2.2",
```

**Deliberately not added yet:** `openinference-semantic-conventions`. It supplies the standard attribute names for *model-call* spans (prompt, completion, token counts). Phase 2 instruments ingestion and retrieval, which have no model-call spans, so importing it here would add a dependency with no call site. It arrives with M4 — see phase 3 §3.1.

- [ ] **Step 2: Add the settings**

In `backend/src/tara/config.py`, add inside `class Settings`, after the Timeouts block:

```python
    # ---- Execution tracing (spec §5) ----
    # Off by default: a span carries the question and retrieved document text.
    # `span_redaction` strips PHI before any value reaches a span, so a trace
    # shows retrieval behaviour without carrying identity.
    tracing_enabled: bool = False
    otlp_endpoint: str = "http://localhost:6006/v1/traces"
    service_name: str = "tara-backend"

    # ---- PHI redaction (spec §6.2) ----
    phi_redaction_enabled: bool = True
    # Presidio defaults to en_core_web_lg (~600MB). en_core_web_sm (~12MB) keeps
    # a laptop install and a CI runner light; swap to _lg for better recall.
    phi_redaction_nlp_model: str = "en_core_web_sm"
```

- [ ] **Step 3: Add the spaCy model download to the bootstrap script**

In `deployment/local/bootstrap.sh`, after the install step, insert:

```bash
echo "==> Downloading the spaCy model Presidio needs"
python -m spacy download en_core_web_sm
```

- [ ] **Step 4: Add the same download to the CI test job**

In `.github/workflows/ci.yml`, in the `test` job only, insert before `- run: make test`:

```yaml
      - run: python -m spacy download en_core_web_sm
```

- [ ] **Step 5: Install and verify nothing changed**

```bash
uv pip install -e "./backend[dev]" && python -m spacy download en_core_web_sm
cd backend && python -m pytest -q 2>&1 | tail -1
```

Expected: `67 passed, 3 skipped, ...`

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/src/tara/config.py deployment/local/bootstrap.sh .github/workflows/ci.yml
git commit -m "build: add tracing and PHI-redaction dependencies and settings

OpenTelemetry SDK, OTLP HTTP exporter, OpenInference conventions,
and Presidio. All five new settings default to off or safe, so this
commit changes nothing observable.

Pins spaCy en_core_web_sm (12MB) over Presidio's en_core_web_lg
default (600MB) so laptop and CI installs stay light; the model name
is a setting, so upgrading recall is a config change."
```

---

### Task 2: Build the PHI redaction module

**Files:**
- Create: `backend/src/tara/phi_redaction.py`
- Test: `backend/tests/test_phi_redaction.py`

**Interfaces:**
- Consumes: `Settings.phi_redaction_enabled`, `Settings.phi_redaction_nlp_model` from Task 1.
- Produces: `redact_phi(text: str) -> str`. Consumed by Task 3 (`span_redaction`) and, at phase 3, by the hosted-egress path.

**Context an engineer needs:**
- This is a **kernel root module**, not a package — it is one concept, and the naming rules forbid one-concept packages.
- Presidio's stock entity set does not cover insurance identifiers. Two custom `PatternRecognizer` instances add member and group numbers, which appear throughout benefits documents.
- The engines are expensive to construct, so both are cached with `lru_cache`.
- Presidio's default anonymizer operator replaces a match with `<ENTITY_TYPE>`, which is exactly what a trace wants: the shape of the value without the value.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_phi_redaction.py`:

```python
"""PHI redaction is what makes tracing safe on a health corpus - test it hard."""
from __future__ import annotations

import pytest

from tara import config
from tara.phi_redaction import redact_phi


@pytest.fixture
def redaction_on(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.integration
def test_person_name_is_removed(redaction_on):
    redacted = redact_phi("Patient Michael Okonkwo was seen on Tuesday.")
    assert "Michael Okonkwo" not in redacted
    assert "<PERSON>" in redacted


@pytest.mark.integration
def test_phone_number_is_removed(redaction_on):
    redacted = redact_phi("Call the office at 617-555-0142 to confirm.")
    assert "617-555-0142" not in redacted


@pytest.mark.integration
def test_insurance_member_id_is_removed(redaction_on):
    redacted = redact_phi("Member ID: XQZ8842190 is active through December.")
    assert "XQZ8842190" not in redacted
    assert "<INSURANCE_MEMBER_ID>" in redacted


@pytest.mark.integration
def test_insurance_group_id_is_removed(redaction_on):
    redacted = redact_phi("Group # 55210 covers the specialist visit.")
    assert "<INSURANCE_GROUP_ID>" in redacted


@pytest.mark.integration
def test_clinical_content_survives_redaction(redaction_on):
    """The point of redaction is to keep the medicine and drop the identity."""
    redacted = redact_phi("Michael Okonkwo has a specialist copay of $40.")
    assert "specialist copay" in redacted
    assert "$40" in redacted


def test_disabled_redaction_passes_text_through(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "false")
    config.get_settings.cache_clear()
    original = "Patient Michael Okonkwo, member ID XQZ8842190."
    assert redact_phi(original) == original
    config.get_settings.cache_clear()


def test_empty_text_is_returned_unchanged(redaction_on):
    assert redact_phi("") == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_phi_redaction.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tara.phi_redaction'`

- [ ] **Step 3: Write the implementation**

Create `backend/src/tara/phi_redaction.py`:

```python
"""Removes protected health information from text before it leaves the process.

Self-hosting the trace backend protects the destination; this module protects
the payload. A redacted span keeps the clinical and cost content a trace exists
to show, while dropping the identity that makes it protected health information.
"""
from __future__ import annotations

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from tara.config import get_settings

# Insurance identifiers Presidio's stock entity set does not cover. They appear
# throughout benefits summaries and explanation-of-benefits documents.
INSURANCE_MEMBER_ID_ENTITY = "INSURANCE_MEMBER_ID"
INSURANCE_GROUP_ID_ENTITY = "INSURANCE_GROUP_ID"

REDACTED_ENTITIES = [
    "PERSON",
    "DATE_TIME",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "US_SSN",
    "LOCATION",
    "MEDICAL_LICENSE",
    INSURANCE_MEMBER_ID_ENTITY,
    INSURANCE_GROUP_ID_ENTITY,
]


def _insurance_member_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_MEMBER_ID_ENTITY,
        patterns=[Pattern(
            name="member_id",
            regex=r"(?:Member|Subscriber)\s*(?:ID|Number|No\.?|#)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{4,}",
            score=0.85,
        )],
    )


def _insurance_group_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_GROUP_ID_ENTITY,
        patterns=[Pattern(
            name="group_id",
            regex=r"(?:Group)\s*(?:ID|Number|No\.?|#)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{3,}",
            score=0.85,
        )],
    )


@lru_cache(maxsize=1)
def _analyzer_engine() -> AnalyzerEngine:
    """Build the analyzer once. Constructing it loads a language model."""
    nlp_engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{
            "lang_code": "en",
            "model_name": get_settings().phi_redaction_nlp_model,
        }],
    }).create_engine()
    analyzer_engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    analyzer_engine.registry.add_recognizer(_insurance_member_id_recognizer())
    analyzer_engine.registry.add_recognizer(_insurance_group_id_recognizer())
    return analyzer_engine


@lru_cache(maxsize=1)
def _anonymizer_engine() -> AnonymizerEngine:
    return AnonymizerEngine()


def redact_phi(text: str) -> str:
    """Return `text` with PHI entities replaced by `<ENTITY_TYPE>` placeholders.

    A no-op when `phi_redaction_enabled` is false or the text is empty, so the
    caller never has to branch.
    """
    if not text or not get_settings().phi_redaction_enabled:
        return text
    analyzer_results = _analyzer_engine().analyze(
        text=text, language="en", entities=REDACTED_ENTITIES,
    )
    if not analyzer_results:
        return text
    return _anonymizer_engine().anonymize(
        text=text, analyzer_results=analyzer_results,
    ).text
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_phi_redaction.py -q`
Expected: `8 passed`

If `test_insurance_group_id_is_removed` fails, check that the group-number regex tolerates the space in `Group # 55210`. Adjust the regex, not the test.

- [ ] **Step 5: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `75 passed, 3 skipped, ...`

- [ ] **Step 6: Commit**

```bash
git add backend/src/tara/phi_redaction.py backend/tests/test_phi_redaction.py
git commit -m "feat: add PHI redaction over Presidio

Kernel root module (one concept, so not a package). Wraps Presidio's
analyzer and anonymizer, adding two custom recognizers for insurance
member and group identifiers that the stock entity set misses.

Keeps clinical and cost content intact while dropping identity - that
separation is what makes tracing a health corpus safe."
```

---

### Task 3: Build the span redaction helper

**Files:**
- Create: `backend/src/tara/execution_tracing/__init__.py` (empty)
- Create: `backend/src/tara/execution_tracing/span_redaction.py`
- Test: `backend/tests/execution_tracing/__init__.py` (empty)
- Test: `backend/tests/execution_tracing/test_span_redaction.py`

**Interfaces:**
- Consumes: `redact_phi(text) -> str` from Task 2.
- Produces: `redact_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]`. Task 5's `traced_span()` calls it.

**Context an engineer needs:**
- Non-string values pass through untouched. Counts, scores, and token totals carry no identity, and they are precisely the numbers a trace exists to show.
- This runs before the value reaches the span, which is stronger than redacting on export.

- [ ] **Step 1: Write the failing tests**

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

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_redaction.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tara.execution_tracing'`

- [ ] **Step 3: Write the implementation**

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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_redaction.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

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

### Task 4: Configure the tracer provider

**Files:**
- Create: `backend/src/tara/execution_tracing/tracer_setup.py`
- Modify: `backend/src/tara/web_app.py` (call `configure_tracing()` in `main()`)

**Interfaces:**
- Consumes: `Settings.tracing_enabled`, `Settings.otlp_endpoint`, `Settings.service_name` from Task 1.
- Produces: `configure_tracing() -> None` and `get_tracer() -> Tracer`. Task 5's `traced_span()` calls `get_tracer()`.

**Context an engineer needs:**
- `configure_tracing()` must be idempotent and safe to call when tracing is disabled — that is what keeps this phase behaviour-neutral.
- `get_tracer()` is safe to call before configuration; OpenTelemetry returns a no-op tracer, so instrumented code never has to check whether tracing is on.
- The provider is installed in `main()`, the composition root — not at import time, which would fire during tests.

- [ ] **Step 1: Write the implementation**

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

- [ ] **Step 2: Wire it into the composition root**

In `backend/src/tara/web_app.py`, inside `main()`, add the import and the call as the **first** statement in the function body, before `ensure_data_dirs()`:

```python
    from tara.execution_tracing.tracer_setup import configure_tracing

    configure_tracing()  # before anything else, so startup work is traced too
```

- [ ] **Step 3: Verify tracing stays off by default**

```bash
cd backend && python -c "
from tara.execution_tracing.tracer_setup import configure_tracing, get_tracer
configure_tracing()
with get_tracer().start_as_current_span('probe') as span:
    print('recording:', span.is_recording())
"
```

Expected: `recording: False` — the no-op tracer, because `tracing_enabled` defaults to false.

- [ ] **Step 4: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `79 passed, 3 skipped, ...`

- [ ] **Step 5: Commit**

```bash
git add backend/src/tara/execution_tracing/tracer_setup.py backend/src/tara/web_app.py
git commit -m "feat: configure the OpenTelemetry tracer provider

Idempotent, opt-in, and installed from the composition root rather
than at import time so importing the package never opens an exporter.

get_tracer() is safe before configuration - OTel returns a no-op
tracer - so instrumented code never branches on whether tracing is on."
```

---

### Task 5: Build the span emitter

**Files:**
- Create: `backend/src/tara/execution_tracing/span_emitter.py`
- Test: `backend/tests/execution_tracing/test_span_emitter.py`

**Interfaces:**
- Consumes: `get_tracer()` from Task 4, `redact_span_attributes()` from Task 3.
- Produces: `traced_span(span_name: str, **attributes) -> Iterator[Span]` and `record_span_attribute(span, attribute_name, attribute_value) -> None`. Task 6 calls both.

**Context an engineer needs:**
- `traced_span()` is the **only** way this application creates spans. Centralizing it is what guarantees redaction cannot be forgotten at a call site.
- The test uses OpenTelemetry's `InMemorySpanExporter` with a `SimpleSpanProcessor`, so it asserts on real spans without a network call or a running Phoenix.
- Attribute names follow OpenInference conventions where one exists; project-specific names are used otherwise.

- [ ] **Step 1: Write the failing tests**

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

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_emitter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tara.execution_tracing.span_emitter'`

- [ ] **Step 3: Write the implementation**

Create `backend/src/tara/execution_tracing/span_emitter.py`:

```python
"""Emits one named, timed span per unit of work, with PHI-redacted attributes.

`traced_span()` is the single way this application creates spans. Centralizing
creation is what guarantees redaction cannot be forgotten at a call site — a
per-call-site `set_attribute` would eventually leak.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry.trace import Span

from tara.execution_tracing.span_redaction import redact_span_attributes
from tara.execution_tracing.tracer_setup import get_tracer


@contextmanager
def traced_span(span_name: str, **attributes: Any) -> Iterator[Span]:
    """Open a span named `span_name`, carrying `attributes` with PHI removed.

    A no-op tracer is returned when tracing is disabled, so callers never branch.
    """
    with get_tracer().start_as_current_span(span_name) as span:
        for attribute_name, attribute_value in redact_span_attributes(attributes).items():
            span.set_attribute(attribute_name, attribute_value)
        yield span


def record_span_attribute(span: Span, attribute_name: str, attribute_value: Any) -> None:
    """Set one attribute on an already-open span, redacting it first.

    Needed for values only known at the end of a step — a result count, an
    answer — which cannot be passed to `traced_span()` up front.
    """
    redacted_attributes = redact_span_attributes({attribute_name: attribute_value})
    span.set_attribute(attribute_name, redacted_attributes[attribute_name])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/execution_tracing/test_span_emitter.py -q`
Expected: `5 passed`

- [ ] **Step 5: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `84 passed, 3 skipped, ...`

- [ ] **Step 6: Commit**

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

### Task 6: Instrument ingestion and retrieval

**Files:**
- Modify: `backend/src/tara/document_ingestion/ingestion_pipeline.py`
- Modify: `backend/src/tara/semantic_search/chunk_retriever.py`

**Interfaces:**
- Consumes: `traced_span()`, `record_span_attribute()` from Task 5.
- Produces: spans named `ingest_document`, `extract_text_spans`, `chunk_spans`, `embed_chunks`, `retrieve_chunks`, `embed_query`, `find_nearest_chunks`. Phase 3 adds the answering spans.

**Context an engineer needs:**
- **Only ingestion and retrieval are instrumented in this phase**, because they are the two flows that actually work today. `answer_question()` cannot run end to end — `screen_for_emergency()` raises `NotImplementedError` — so its spans land with M4 and M5 in phase 3.
- Import direction holds: capability → plane is permitted.
- Attributes must be primitives. Never put a chunk's text or a filename on a span; put counts, scores, and identifiers.

- [ ] **Step 1: Instrument the retrieval path**

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

- [ ] **Step 2: Instrument the ingestion path**

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

- [ ] **Step 3: Verify behaviour is unchanged**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `84 passed, 3 skipped, ...` — instrumentation must not change any test outcome.

- [ ] **Step 4: Lint and typecheck**

```bash
make lint && make typecheck
```

Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add backend/src/tara/semantic_search/chunk_retriever.py backend/src/tara/document_ingestion/ingestion_pipeline.py
git commit -m "feat: instrument the ingestion and retrieval paths

Spans for ingest_document, extract_text_spans, chunk_spans,
embed_chunks, retrieve_chunks, embed_query, and find_nearest_chunks,
carrying counts and scores only - never chunk text or filenames.

Answering spans are deliberately absent: answer_question cannot run
end to end until M5 implements screen_for_emergency, so they land in
phase 3 alongside it."
```

---

### Task 7: Add Phoenix to the stack and verify a trace end to end

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

- [ ] **Step 1: Add the Phoenix service**

In `deployment/docker/compose.yaml`, add to `services`:

```yaml
  phoenix:
    image: arizephoenix/phoenix:latest
    ports:
      - "6006:6006"   # UI + OTLP over HTTP
      - "4317:4317"   # OTLP over gRPC
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

- [ ] **Step 2: Document the new settings in .env.example**

Append to `.env.example`:

```bash
# ---- Execution tracing (spec: docs/superpowers/specs/2026-08-14-foundation-and-stack-design.md) ----
# Off by default. Spans carry the question and retrieved text, so PHI redaction
# runs before any value reaches a span.
TARA_TRACING_ENABLED=false
TARA_OTLP_ENDPOINT=http://localhost:6006/v1/traces
TARA_SERVICE_NAME=tara-backend

# ---- PHI redaction ----
TARA_PHI_REDACTION_ENABLED=true
# en_core_web_sm (12MB) keeps installs light; en_core_web_lg (600MB) has better recall.
TARA_PHI_REDACTION_NLP_MODEL=en_core_web_sm
```

- [ ] **Step 3: Bring the stack up**

```bash
make up
sleep 15
curl -s -o /dev/null -w "phoenix:%{http_code}\n" http://127.0.0.1:6006/
curl -s -o /dev/null -w "backend:%{http_code}\n" http://127.0.0.1:8000/
```

Expected: `phoenix:200` and `backend:200`

- [ ] **Step 4: Generate a trace by uploading a document**

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

- [ ] **Step 5: Verify the trace arrived and is redacted**

Open `http://localhost:6006` in a browser. Confirm all four:

1. A trace named `ingest_document` exists.
2. It has child spans `extract_text_spans`, `chunk_spans`, and `embed_chunks`.
3. `chunk_spans` carries a `chunk_count` attribute with a real number.
4. **No span attribute anywhere contains the strings `Michael Okonkwo` or `XQZ8842190`.**

Item 4 is the acceptance criterion for this phase. If it fails, stop and fix redaction before proceeding.

- [ ] **Step 6: Tear down and document the plane**

```bash
make down
```

In `CLAUDE.md`, add to the "Cross-cutting design constraints" list:

```markdown
- **Tracing is opt-in and redacted at set time.** `execution_tracing/` wraps OpenTelemetry; `traced_span()` is the only span-creation path, and it runs every string attribute through `phi_redaction` before the value reaches the span. Instrumentation is vendor-neutral OTLP, so the backend (Phoenix by default, Langfuse a documented swap) is an endpoint change, never a code change.
```

- [ ] **Step 7: Commit**

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

## Phase 2 acceptance

- [ ] `make test` reports `84 passed, 3 skipped`.
- [ ] `make lint` and `make typecheck` are clean.
- [ ] With `TARA_TRACING_ENABLED=false` (the default), `get_tracer()` returns a non-recording span — nothing changed for a developer who has not opted in.
- [ ] `make up`, then an upload, produces an `ingest_document` trace in Phoenix with child spans and numeric attributes.
- [ ] No span attribute contains a person name or a member identifier.
