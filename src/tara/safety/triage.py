"""Emergency PRE-check. Runs BEFORE the answering model on any health query.
Kept separate from the answering prompt so it cannot be 'reasoned away' and can
be tested on its own. Bias toward over-triggering — a false alarm is far safer
than a missed emergency.
"""
from __future__ import annotations

from dataclasses import dataclass

# Non-exhaustive starting list. Expand and test against safety/eval cases.
RED_FLAG_PATTERNS = [
    "chest pain", "can't breathe", "cannot breathe", "trouble breathing",
    "face drooping", "slurred speech", "sudden weakness", "worst headache",
    "suicidal", "want to die", "overdose", "anaphylaxis", "severe bleeding",
]


@dataclass
class TriageResult:
    is_emergency: bool
    message: str | None = None  # the escalation message to show, if any


def screen(question: str) -> TriageResult:
    """TODO: fast keyword pass + optional lightweight LLM confirmation.
    On emergency, return a message directing the user to emergency services and
    DO NOT proceed to answering."""
    raise NotImplementedError
