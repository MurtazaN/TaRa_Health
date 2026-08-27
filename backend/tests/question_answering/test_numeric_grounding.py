"""Every checked figure in an answer must appear in a cited excerpt."""
from __future__ import annotations

import pytest

from tara.question_answering.numeric_grounding import verify_numbers_are_grounded

_EXCERPT = "Specialist visit copay: $40.00 after a 30-day wait. Coinsurance 20%. A1c 5.7%."


@pytest.mark.unit
@pytest.mark.parametrize(
    "answer_text",
    [
        "Your specialist copay is $40.",
        "Your specialist copay is $40.00.",
        "Coinsurance is 20% once the deductible is met.",
        "There is a 30-day wait.",
        "Your A1c was 5.7%.",
    ],
)
def test_a_figure_present_in_the_excerpt_is_grounded(answer_text):
    verdict = verify_numbers_are_grounded(answer_text, [_EXCERPT])
    assert verdict.is_grounded is True
    assert verdict.ungrounded_figures == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "answer_text, expected_figure",
    [
        ("Your specialist copay is $45.", "$45"),
        ("Coinsurance is 30%.", "30%"),
        ("Your A1c was 6.2%.", "6.2%"),
    ],
)
def test_a_figure_absent_from_the_excerpt_is_reported(answer_text, expected_figure):
    verdict = verify_numbers_are_grounded(answer_text, [_EXCERPT])
    assert verdict.is_grounded is False
    assert expected_figure in verdict.ungrounded_figures


@pytest.mark.unit
@pytest.mark.parametrize("answer_text", ["See step 2 below.", "There are 3 options."])
def test_a_standalone_single_digit_is_not_checked(answer_text):
    # Fail-closed means every false positive discards a correct answer, and
    # list markers are the commonest false positive of all.
    assert verify_numbers_are_grounded(answer_text, [_EXCERPT]).is_grounded is True


@pytest.mark.unit
def test_only_cited_excerpts_count_as_grounding():
    # A number that appears in a retrieved but UNCITED excerpt is not grounding:
    # the citation is the claim about where the fact came from.
    verdict = verify_numbers_are_grounded("Your copay is $75.", [_EXCERPT])
    assert verdict.is_grounded is False


@pytest.mark.unit
def test_an_answer_with_no_figures_is_grounded():
    assert verify_numbers_are_grounded("Physiotherapy is covered.", []).is_grounded is True
