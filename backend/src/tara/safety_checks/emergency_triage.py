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
    # Copular phrasings of the stroke signs above. Matching is literal
    # substring, so "my face is drooping" does not contain "face drooping";
    # a missed stroke is exactly the failure this list exists to prevent.
    "face is drooping", "speech is slurred",
]


@dataclass
class TriageResult:
    is_emergency: bool
    message: str | None = None  # the escalation message to show, if any


# Shown verbatim on escalation. Names the action, not the diagnosis: this check
# is deliberately over-triggering, so the wording must be right even when the
# question turns out to be benign.
EMERGENCY_MESSAGE = (
    "This sounds like it could be a medical emergency. Please call your local "
    "emergency number (911 in the US) or go to the nearest emergency department "
    "now. I cannot help with emergencies, and I will not try to answer this from "
    "your documents."
)


def _normalise_question(question: str) -> str:
    """Lower-case and collapse whitespace so a pattern matches regardless of layout."""
    return " ".join(question.lower().split())


def screen_for_emergency(question: str) -> TriageResult:
    """Return whether `question` describes an emergency, and the escalation
    message to show if it does.

    M4 implements the keyword layer only. The hazard classifier that Epic 0's
    handoff §3.3 adds is M5 work, and is purely ADDITIVE: either layer may
    escalate, neither may downgrade the other, so this layer stays authoritative
    when it lands.

    Fail-closed by construction: any failure inside the check escalates. A check
    that errors into "not an emergency" would hand the question to the answering
    model, which is the exact outcome the pre-check exists to prevent.
    """
    try:
        normalised_question = _normalise_question(question)
    except Exception:  # noqa: BLE001 - fail-closed is the whole point
        return TriageResult(is_emergency=True, message=EMERGENCY_MESSAGE)
    for red_flag_pattern in RED_FLAG_PATTERNS:
        if red_flag_pattern in normalised_question:
            return TriageResult(is_emergency=True, message=EMERGENCY_MESSAGE)
    return TriageResult(is_emergency=False, message=None)
