"""Phase 1 evaluation harness (see PHASE_1_TECHNICAL_DESIGN.md §8):

  - retrieval accuracy   (top-k hit rate on curated Q->chunk pairs)
  - citation correctness (does the cited page actually contain the fact?)
  - honesty              (unanswerable questions must be declined, not invented)
  - safety recall        (emergency inputs must trip the pre-check)
  - OCR fidelity         (spot-check numbers on scanned fixtures)

Run:  python tests/eval_harness.py
"""
from __future__ import annotations


def main() -> None:
    # TODO: load labeled cases from tests/fixtures, run each metric, print a report.
    raise NotImplementedError


if __name__ == "__main__":
    main()
