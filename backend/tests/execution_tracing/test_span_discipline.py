"""Enforces `traced_span()` as the only path that touches the raw span API.

`traced_span()` yields the raw OTel `Span` so Task 5's call sites can attach
late attributes via `record_span_attribute()`. That means nothing stops a call
site from bypassing redaction entirely by calling `.set_attribute()`,
`.add_event()`, `.record_exception()`, or `.set_status()` directly on the
span it was handed. Centralization is what guarantees redaction cannot be
forgotten — but only as long as no other module reaches for the raw API. This
test is what keeps that guarantee true as new call sites are added: it fails
loudly, naming the offending file and line, the moment one does.
"""
from __future__ import annotations

from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "tara"
_ALLOWED_FILE = _SOURCE_ROOT / "execution_tracing" / "span_emitter.py"
_FORBIDDEN_CALLS = (".set_attribute(", ".add_event(", ".record_exception(", ".set_status(")


def _find_forbidden_calls() -> list[str]:
    """Return "path:line: snippet" for every forbidden raw-span call site."""
    violations: list[str] = []
    for source_file in sorted(_SOURCE_ROOT.rglob("*.py")):
        if source_file == _ALLOWED_FILE:
            continue
        lines = source_file.read_text().splitlines()
        for line_number, line in enumerate(lines, start=1):
            if any(forbidden_call in line for forbidden_call in _FORBIDDEN_CALLS):
                violations.append(f"{source_file}:{line_number}: {line.strip()}")
    return violations


def test_only_span_emitter_touches_the_raw_span_api():
    violations = _find_forbidden_calls()
    assert not violations, (
        "Raw span API called outside execution_tracing/span_emitter.py — "
        "route this through traced_span()/record_span_attribute() instead, "
        "or redaction can be bypassed at this call site:\n"
        + "\n".join(violations)
    )


def test_allowed_file_is_the_one_that_actually_uses_the_raw_api():
    """Sanity check that the scan itself works: span_emitter.py legitimately
    calls at least one forbidden pattern it is exempted from — an exemption
    that matched nothing would make `test_only_span_emitter_touches_the_raw_span_api`
    pass for the wrong reason (a scan that finds nothing anywhere).
    """
    allowed_file_contents = _ALLOWED_FILE.read_text()
    assert any(forbidden_call in allowed_file_contents for forbidden_call in _FORBIDDEN_CALLS)
