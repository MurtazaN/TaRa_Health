"""Adds safety framing to a finished answer — the post-check of design §3.3.

`apply_safety_framing()` ensures the answer reads as general information (not a
diagnosis), nudges toward professional care for anything serious or persistent,
and avoids guaranteed outcomes or timelines. Append-only and non-destructive:
it may add disclaimers but must not edit the grounded facts or the citation
markers already in the text.
"""
from __future__ import annotations

# Static rather than model-generated, deliberately: this text runs after the
# grounding check, so anything generated here would be unverified content
# appended to a verified answer.
SAFETY_FRAMING = (
    "\n\nThis is general information drawn from your own documents, not medical "
    "advice or a coverage guarantee. For anything serious, sudden, or persistent, "
    "please speak with a healthcare professional, and confirm benefits with your "
    "insurer before you rely on them."
)


def apply_safety_framing(answer_text: str) -> str:
    """Return `answer_text` with the informational framing and care nudge appended.

    Append-only and idempotent. It runs LAST, after citation mapping and the
    numeric-grounding check, so the framing text can never be mistaken for
    grounded content or inspected as if it were.
    """
    if not answer_text:
        return answer_text
    if SAFETY_FRAMING.strip() in answer_text:
        return answer_text
    return answer_text + SAFETY_FRAMING
