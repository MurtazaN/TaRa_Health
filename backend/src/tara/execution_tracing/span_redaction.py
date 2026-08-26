"""Strips PHI out of span attributes before they reach a span.

Runs at attribute-set time rather than at export time: a value that never
enters a span cannot leak through a misconfigured exporter or a backend
swapped in later.
"""
from __future__ import annotations

from typing import Any

from tara.phi_redaction import redact_phi


def _redact_attribute_value(attribute_value: Any) -> Any:
    """Redact one attribute value, recursing one level into list/tuple values.

    OTel's attribute contract permits `Sequence[str]` alongside scalars, so a
    string hiding inside a list must be redacted the same as a bare string.
    Non-string, non-sequence values pass through untouched.
    """
    if isinstance(attribute_value, str):
        return redact_phi(attribute_value)
    if isinstance(attribute_value, (list, tuple)):
        redacted_items = [
            redact_phi(item) if isinstance(item, str) else item
            for item in attribute_value
        ]
        return type(attribute_value)(redacted_items)
    return attribute_value


def redact_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Return a new mapping with every string value PHI-redacted.

    Non-string, non-sequence values pass through untouched — counts, scores,
    and durations carry no identity, and they are the numbers a trace exists
    to show. Strings nested inside a list or tuple attribute are redacted too.
    """
    return {
        attribute_name: _redact_attribute_value(attribute_value)
        for attribute_name, attribute_value in attributes.items()
    }
