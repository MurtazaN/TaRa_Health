"""Safety is the highest-stakes layer — test it hardest.
TODO: a battery of emergency-phrased inputs that MUST trip the pre-check
(favor over-triggering), plus framing checks on normal answers.
"""
from __future__ import annotations

import pytest

from tara.safety_checks.emergency_triage import screen_for_emergency

EMERGENCY_INPUTS = [
    "I have crushing chest pain and my left arm is numb",
    "I took way too many pills and I want to die",
    "my face is drooping and my speech is slurred",
]


@pytest.mark.parametrize("text", EMERGENCY_INPUTS)
def test_emergencies_are_caught(text):
    from tara.safety_checks.emergency_triage import screen_for_emergency
    assert screen_for_emergency(text).is_emergency


@pytest.mark.unit
@pytest.mark.parametrize(
    "question",
    [
        "I have crushing CHEST PAIN right now",
        "my dad's face drooping and slurred speech started an hour ago",
        "I think I took an overdose",
        "  worst headache of my life  ",
    ],
)
def test_a_red_flag_escalates_whatever_the_casing_or_spacing(question):
    result = screen_for_emergency(question)
    assert result.is_emergency is True
    assert result.message


@pytest.mark.unit
@pytest.mark.parametrize(
    "question",
    ["what is my specialist copay?", "does my plan cover physiotherapy?"],
)
def test_an_ordinary_question_does_not_escalate(question):
    result = screen_for_emergency(question)
    assert result.is_emergency is False
    assert result.message is None


@pytest.mark.unit
def test_a_failure_inside_the_check_escalates_rather_than_passing_through(monkeypatch):
    # Fail-closed: a triage that errors must not silently become "not an
    # emergency", because the caller would then answer the question normally.
    from tara.safety_checks import emergency_triage

    def explode(text):
        raise RuntimeError("nlp exploded")

    monkeypatch.setattr(emergency_triage, "_normalise_question", explode)
    result = screen_for_emergency("anything at all")
    assert result.is_emergency is True
