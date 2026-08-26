"""Enforces `traced_span()` as the only path that touches the raw span API.

Two ways to put an unredacted value on a span, and this scan must cover both:

- **Mutation.** `traced_span()` yields the raw OTel `Span` so Task 5's call
  sites can attach late attributes via `record_span_attribute()`. Nothing
  stops a call site from bypassing redaction by calling `.set_attribute()`,
  `.add_event()`, `.record_exception()`, or `.set_status()` on that span.
- **Creation.** `start_as_current_span()` and `start_span()` take an
  `attributes=` mapping, so a span can be born carrying PHI before anything
  mutates it — `start_as_current_span("ask", attributes={"question": ...})`
  never touches a forbidden mutation call, and an earlier mutation-only
  version of this scan flagged nothing. Reaching a tracer at all is the first
  step of that bypass, so `get_tracer(` is scanned too.

Centralization is what guarantees redaction cannot be forgotten — but only as
long as no other module reaches for the raw API by either route. This test
fails loudly, naming the offending file and line, the moment one does.

Exemptions are per (pattern, file), not per file: `tracer_setup.py` legitimately
defines and calls `get_tracer`, but it has no business creating or mutating a
span, so blanket-exempting the whole file would reopen the creation hole inside
the very plane this scan protects.
"""
from __future__ import annotations

from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "tara"
_SPAN_EMITTER = _SOURCE_ROOT / "execution_tracing" / "span_emitter.py"
_TRACER_SETUP = _SOURCE_ROOT / "execution_tracing" / "tracer_setup.py"

# Each forbidden pattern maps to the files allowed to contain it. An empty set
# means no file may use it anywhere; adding a genuinely needed call means adding
# the file here, which is a reviewed decision rather than a silent one.
_FORBIDDEN_CALLS: dict[str, frozenset[Path]] = {
    # --- span mutation ---
    ".set_attribute(": frozenset({_SPAN_EMITTER}),
    ".add_event(": frozenset({_SPAN_EMITTER}),
    ".set_status(": frozenset({_SPAN_EMITTER}),
    # `traced_span()` passes `record_exception=False` deliberately; no module
    # should be recording an exception onto a span by hand.
    ".record_exception(": frozenset(),
    # --- span creation ---
    ".start_as_current_span(": frozenset({_SPAN_EMITTER}),
    ".start_span(": frozenset(),
    "get_tracer(": frozenset({_SPAN_EMITTER, _TRACER_SETUP}),
}


def _find_forbidden_calls() -> list[str]:
    """Return "path:line: snippet" for every raw-span call site not exempted."""
    violations: list[str] = []
    for source_file in sorted(_SOURCE_ROOT.rglob("*.py")):
        lines = source_file.read_text().splitlines()
        for line_number, line in enumerate(lines, start=1):
            for forbidden_call, exempt_files in _FORBIDDEN_CALLS.items():
                if forbidden_call in line and source_file not in exempt_files:
                    violations.append(f"{source_file}:{line_number}: {line.strip()}")
                    break
    return violations


def test_only_span_emitter_touches_the_raw_span_api():
    violations = _find_forbidden_calls()
    assert not violations, (
        "Raw span creation or mutation outside execution_tracing/span_emitter.py — "
        "route this through traced_span()/record_span_attribute() instead, "
        "or redaction can be bypassed at this call site:\n"
        + "\n".join(violations)
    )


def test_every_exemption_actually_matches_something():
    """Sanity check that the scan itself works.

    Every (pattern, file) exemption must correspond to a real call in that
    file. An exemption matching nothing would mean the pattern is misspelled,
    which would make `test_only_span_emitter_touches_the_raw_span_api` pass for
    the wrong reason — a scan that finds nothing anywhere.
    """
    unmatched_exemptions = [
        f"{exempt_file.name} is exempted from '{forbidden_call}' but never uses it"
        for forbidden_call, exempt_files in _FORBIDDEN_CALLS.items()
        for exempt_file in sorted(exempt_files)
        if forbidden_call not in exempt_file.read_text()
    ]
    assert not unmatched_exemptions, "\n".join(unmatched_exemptions)
