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
