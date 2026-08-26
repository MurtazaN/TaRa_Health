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
