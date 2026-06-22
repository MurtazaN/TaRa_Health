"""Tag each document with a DocType. Drives document-type-filtered retrieval
(e.g., cost questions should prefer insurance documents).
"""
from __future__ import annotations

from tara.storage.models import DocType


def classify(full_text: str) -> DocType:
    """TODO: lightweight classifier — keyword heuristics first, optional small
    LLM call for ambiguous cases. Keep it cheap and local."""
    raise NotImplementedError
