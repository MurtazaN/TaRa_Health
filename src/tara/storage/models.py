"""Core data models. A Chunk always carries enough provenance (doc + page +
char span) to render a citation back to the exact location in the source file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

DocType = Literal[
    "insurance_policy", "benefits_summary", "eob", "bill",
    "lab_report", "prescription", "after_visit_summary", "other",
]


@dataclass
class Document:
    doc_id: str
    filename: str
    doc_type: DocType = "other"
    page_count: int = 0
    uploaded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page: int
    char_start: int
    char_end: int
    text: str
    # embedding lives in the vector table, keyed by chunk_id


@dataclass
class Citation:
    """What the UI shows: maps a used chunk back to its source location."""
    chunk_id: str
    filename: str
    page: int
