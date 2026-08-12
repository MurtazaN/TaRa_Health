"""Adds safety framing to a finished answer — the post-check of design §3.3.

`apply_safety_framing()` ensures the answer reads as general information (not a
diagnosis), nudges toward professional care for anything serious or persistent,
and avoids guaranteed outcomes or timelines. Append-only and non-destructive:
it may add disclaimers but must not edit the grounded facts or the citation
markers already in the text.
"""
from __future__ import annotations


def apply_safety_framing(answer_text: str) -> str:
    """Return `answer_text` with the informational framing and care nudge appended.

    TODO (Slice 4): keep it light so it doesn't bury the actual answer; on
    framing failure, return the answer with a default static disclaimer rather
    than erroring (§3.3)."""
    raise NotImplementedError
