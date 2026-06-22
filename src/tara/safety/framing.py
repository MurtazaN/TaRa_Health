"""Framing POST-check. Ensures the final answer reads as general information
(not diagnosis), nudges toward professional care for anything serious/persistent,
and strips any guaranteed outcomes or timelines.
"""
from __future__ import annotations


def apply_framing(answer: str) -> str:
    """TODO: append/standardize the informational framing and care nudge.
    Keep it light so it doesn't bury the actual answer."""
    raise NotImplementedError
