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


@pytest.mark.unit
@pytest.mark.parametrize(
    "chunk_text, fabricated_answer, expected_figure",
    [
        # A calendar date is not a quantity. Without this, the year grounds a
        # fabricated dollar amount that happens to share its digits.
        ("Plan effective 01/01/2026. Specialist copay: $40 after the deductible.",
         "Your specialist copay is $2026.", "$2026"),
        ("Plan effective 2026-01-01. Specialist copay: $40.",
         "Your specialist copay is $2026.", "$2026"),
        # A dash-separated identifier is not a quantity either.
        ("Group Number: 4000-1234. Specialist copay: $40.",
         "Your specialist copay is $4000.", "$4000"),
        ("Questions? Call 555-123-4567. Specialist copay: $40.",
         "Your specialist copay is $555.", "$555"),
    ],
)
def test_a_date_or_identifier_in_the_chunk_does_not_ground_a_figure(
    chunk_text, fabricated_answer, expected_figure
):
    verdict = verify_numbers_are_grounded(fabricated_answer, [chunk_text])
    assert verdict.is_grounded is False
    assert expected_figure in verdict.ungrounded_figures


@pytest.mark.unit
@pytest.mark.parametrize(
    "chunk_text",
    [
        "Plan effective 01/01/2026. Specialist copay: $40 after the deductible.",
        "Group Number: 4000-1234. Specialist copay: $40.",
    ],
)
def test_the_real_figure_still_grounds_alongside_a_date_or_identifier(chunk_text):
    # Removing the non-quantity shapes must not remove the quantities beside them.
    assert verify_numbers_are_grounded("Your specialist copay is $40.", [chunk_text]).is_grounded


@pytest.mark.unit
def test_a_day_count_is_still_a_quantity():
    # "30-day" is a duration, not an identifier, and an answer may legitimately
    # state it. Only dash-separated DIGIT runs are treated as identifiers.
    verdict = verify_numbers_are_grounded("There is a 30-day wait.", [_EXCERPT])
    assert verdict.is_grounded is True
