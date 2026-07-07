"""Core data models. A Chunk always carries enough provenance (doc + page +
char span) to render a citation back to the exact location in the source file
(design §4). Citations carry the char span so the UI can highlight the exact
cited text (§3.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

DocType = Literal[
    "insurance_policy", "benefits_summary", "eob", "bill",
    "lab_report", "prescription", "after_visit_summary", "other",
]

# Ingestion lifecycle (§3.1g). A document is invisible to retrieval unless "indexed".
DocStatus = Literal["indexing", "indexed", "indexing_failed"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Document:
    doc_id: str
    filename: str
    doc_type: DocType = "other"
    content_hash: str = ""            # sha256 of the file bytes; drives re-ingest dedup (§3.1f)
    status: DocStatus = "indexing"    # set to "indexed" only after vectors are written (§3.1g)
    page_count: int = 0
    uploaded_at: datetime = field(default_factory=_utcnow)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page: int
    char_start: int
    char_end: int
    text: str
    # embedding lives in the vector table, keyed by chunk_id

    @staticmethod
    def make_chunk_id(doc_id: str, page: int, char_start: int) -> str:
        """Deterministic chunk id (§3.1d): stable across re-ingest so historical
        citations stay valid and re-ingest is idempotent."""
        return f"{doc_id}:{page}:{char_start}"


@dataclass
class Citation:
    """What the UI shows: maps a used chunk back to its source location (§3.5).

    The char span lets the UI open the source page and highlight the cited text.
    On OCR'd scans char spans aren't pixel-mappable, so the citation resolves to
    page level (char_start == char_end == 0 by convention; §3.1b)."""
    chunk_id: str
    filename: str
    page: int
    char_start: int = 0
    char_end: int = 0
    snippet: str = ""
