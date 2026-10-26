"""Framing may add, and may never take away."""
from __future__ import annotations

import pytest

from tara.safety_checks.answer_framing import SAFETY_FRAMING, apply_safety_framing


@pytest.mark.unit
def test_the_original_answer_survives_verbatim():
    answer = "Your specialist copay is $40 after the deductible."
    framed = apply_safety_framing(answer)
    assert framed.startswith(answer)
    assert SAFETY_FRAMING in framed


@pytest.mark.unit
def test_framing_is_not_applied_twice():
    framed_once = apply_safety_framing("Your copay is $40.")
    framed_twice = apply_safety_framing(framed_once)
    assert framed_twice == framed_once


@pytest.mark.unit
def test_an_empty_answer_is_left_alone():
    # Nothing to frame, and appending a disclaimer to nothing produces an
    # "answer" made entirely of disclaimer.
    assert apply_safety_framing("") == ""
