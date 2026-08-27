"""Checks that every figure an answer states appears in a cited excerpt.

The M4 contract's post-processing step 2, and the reason it exists: a
confidently wrong copay carrying a citation is more dangerous than a refusal,
because the citation is what makes the user trust the number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

# Matches an optional currency symbol, a digit run with optional thousands
# separators, an optional decimal part, and an optional percent sign.
_FIGURE_PATTERN = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


@dataclass
class GroundingVerdict:
    """Whether every checked figure was found, and which were not."""

    is_grounded: bool
    ungrounded_figures: list[str] = field(default_factory=list)


def _is_checked_figure(figure: str) -> bool:
    """Whether `figure` is the kind of number a wrong answer would turn on.

    Money, percentages, decimals and any number of two or more digits are
    checked. A standalone single digit is not: "step 2" and "3 options" are the
    commonest figures in ordinary prose, and abstaining on them would discard
    correct answers for no safety gain.
    """
    if figure.startswith("$") or figure.endswith("%") or "." in figure:
        return True
    return len(figure.replace(",", "")) >= 2


def _normalise_figure(figure: str) -> str:
    """Reduce a figure to the form used for comparison on both sides.

    Strips the currency symbol and thousands separators, then drops a trailing
    zero decimal, so "$1,200" in an answer matches "1200.00" in a document:
    comparing raw text would fail on formatting alone. A percent sign is kept,
    because it changes what the number means -- a stated "30%" must not be
    grounded by the unrelated "30" in "30-day wait". The currency symbol is not
    kept, because documents routinely put the "$" in a table header rather than
    in the cell.
    """
    percent_suffix = "%" if figure.endswith("%") else ""
    stripped = figure.lstrip("$").rstrip("%").replace(",", "")
    if "." in stripped:
        stripped = stripped.rstrip("0").rstrip(".")
    return stripped + percent_suffix


def verify_numbers_are_grounded(
    answer_text: str, cited_chunk_texts: Sequence[str]
) -> GroundingVerdict:
    """Return which figures in `answer_text` appear in no cited excerpt.

    Only CITED excerpts count. A figure found in a retrieved-but-uncited excerpt
    is still ungrounded, because the citation is the answer's own claim about
    where the fact came from.
    """
    grounded_forms = {
        _normalise_figure(found_figure)
        for chunk_text in cited_chunk_texts
        for found_figure in _FIGURE_PATTERN.findall(chunk_text)
    }
    ungrounded_figures = [
        answer_figure
        for answer_figure in _FIGURE_PATTERN.findall(answer_text)
        if _is_checked_figure(answer_figure)
        and _normalise_figure(answer_figure) not in grounded_forms
    ]
    return GroundingVerdict(
        is_grounded=not ungrounded_figures, ungrounded_figures=ungrounded_figures
    )
