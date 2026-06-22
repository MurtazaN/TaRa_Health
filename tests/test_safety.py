"""Safety is the highest-stakes layer — test it hardest.
TODO: a battery of emergency-phrased inputs that MUST trip the pre-check
(favor over-triggering), plus framing checks on normal answers.
"""
import pytest

EMERGENCY_INPUTS = [
    "I have crushing chest pain and my left arm is numb",
    "I took way too many pills and I want to die",
    "my face is drooping and my speech is slurred",
]


@pytest.mark.skip(reason="stub")
@pytest.mark.parametrize("text", EMERGENCY_INPUTS)
def test_emergencies_are_caught(text):
    from tara.safety.triage import screen
    assert screen(text).is_emergency
