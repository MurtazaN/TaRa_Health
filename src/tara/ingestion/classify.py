"""Assigns a document-type label (DocType) to an extracted document's text.

`classify_doc_type()` tags each document (insurance_policy, lab_report, eob, …)
so retrieval can filter to the types a question implies — e.g. cost questions
prefer insurance documents (§3.4). Lands in Slice 6.
"""
from __future__ import annotations

from tara.storage.models import DocType


def classify_doc_type(full_text: str) -> DocType:
    """Return the DocType for a document given its full extracted text.

    TODO (Slice 6): keyword heuristics first, optional small local LLM call for
    ambiguous cases. Keep it cheap and local."""
    raise NotImplementedError
