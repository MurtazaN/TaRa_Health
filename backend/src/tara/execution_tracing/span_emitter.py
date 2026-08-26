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
