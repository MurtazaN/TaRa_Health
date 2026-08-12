"""Screens a question for medical emergencies BEFORE any answering happens.

`screen_for_emergency()` is the pre-check of design §3.3: a fast red-flag
keyword pass plus a lightweight LLM confirmation, combined fail-closed (either
layer can escalate; the LLM can never downgrade a keyword hit). It is kept
separate from the answering prompt so the answering model cannot "reason away"
an emergency, and it is biased toward over-triggering — a false alarm is far
safer than a missed emergency.
"""
from __future__ import annotations

from dataclasses import dataclass

# Non-exhaustive starting list. The required minimum taxonomy is design §3.3;
# the §8 safety-recall fixture gates this list at 100% recall (Slice 4).
RED_FLAG_PATTERNS = [
    "chest pain", "can't breathe", "cannot breathe", "trouble breathing",
    "face drooping", "slurred speech", "sudden weakness", "worst headache",
    "suicidal", "want to die", "overdose", "anaphylaxis", "severe bleeding",
]


@dataclass
class TriageResult:
    is_emergency: bool
    message: str | None = None  # the escalation message to show, if any


def screen_for_emergency(question: str) -> TriageResult:
    """Return whether `question` describes an emergency, and the escalation
    message to show if it does.

    TODO (Slice 4): keyword pass over RED_FLAG_PATTERNS + lightweight LLM
    confirmation; fail toward escalation if the check itself errors. On
    emergency, the message directs the user to emergency services and the
    caller must NOT proceed to answering."""
    raise NotImplementedError
