"""Strips PHI out of span attributes before they reach a span.

Runs at attribute-set time rather than at export time: a value that never
enters a span cannot leak through a misconfigured exporter or a backend
swapped in later.
"""
from __future__ import annotations

from typing import Any

from tara.phi_redaction import redact_phi


def _redact_text_bearing_value(attribute_value: Any) -> Any:
    """Redact one scalar attribute value; pass anything identity-free through.

    - `str` is redacted directly.
    - `bytes` is decoded, redacted, and re-encoded. OTel treats `bytes` as a
      valid attribute type and decodes it to a plain string on the span, so
      raw bytes leak exactly like a raw string would.
    - Everything else (`bool`, `int`, `float`, `None`, ...) passes through:
      counts and scores carry no identity.
    """
    if isinstance(attribute_value, str):
        return redact_phi(attribute_value)
    if isinstance(attribute_value, bytes):
        return redact_phi(attribute_value.decode("utf-8", "replace")).encode("utf-8")
    return attribute_value


def _redact_attribute_value(attribute_value: Any) -> Any:
    """Redact one attribute value, recursing one level into list/tuple values.

    OTel's valid attribute types are `(bool, str, bytes, int, float)` plus a
    homogeneous sequence of those, so both `str` and `bytes` carry text onto a
    span and both must be redacted — at the top level and inside a sequence.
    A `bytes` value is decoded, redacted, and re-encoded rather than skipped,
    because OTel decodes it to a plain string when it lands on the span.
    """
    if isinstance(attribute_value, (list, tuple)):
        redacted_items = [_redact_text_bearing_value(item) for item in attribute_value]
        return type(attribute_value)(redacted_items)
    return _redact_text_bearing_value(attribute_value)


def redact_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Return a new mapping with every text-bearing value PHI-redacted.

    - `str` and `bytes` values are redacted; `bytes` is decoded, redacted, and
      re-encoded, because OTel accepts `bytes` and decodes it to a plain
      string on the span.
    - `str` and `bytes` nested one level inside a `list` or `tuple` are
      redacted the same way — OTel accepts sequences of those types too.
    - Numbers and booleans pass through untouched: counts, scores, and
      durations carry no identity, and they are what a trace exists to show.
    """
    return {
        attribute_name: _redact_attribute_value(attribute_value)
        for attribute_name, attribute_value in attributes.items()
    }
