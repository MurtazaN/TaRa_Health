"""Top-level query flow — the heart of Phase 1:

    SAFETY pre-check -> (emergency? stop) -> retrieve -> answer (grounded+cited)
    -> SAFETY framing post-check -> return answer + citations
"""
from __future__ import annotations

from dataclasses import dataclass

from tara.answering.prompts import ANSWER_SYSTEM, build_user_prompt
from tara.llm.base import get_client
from tara.retrieval.retriever import retrieve
from tara.safety.framing import apply_framing
from tara.safety.triage import screen
from tara.storage.models import Citation


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    safety_flag: str  # "none" | "emergency"


def ask(question: str, prefer_hosted: bool = False) -> Answer:
    # 1) Safety pre-check — short-circuit on emergencies.
    triage = screen(question)
    if triage.is_emergency:
        return Answer(text=triage.message or "", citations=[], safety_flag="emergency")

    # 2) Retrieve grounding context.
    retrieved = retrieve(question)
    excerpts = [
        {"chunk_id": r.chunk.chunk_id, "filename": r.filename,
         "page": r.chunk.page, "text": r.chunk.text}
        for r in retrieved
    ]

    # 3) Grounded, citable answer (local by default; hosted only if opted in).
    client = get_client(prefer_hosted=prefer_hosted)
    raw = client.complete(ANSWER_SYSTEM, build_user_prompt(question, excerpts))

    # 4) Framing post-check + map cited chunk_ids -> Citations for the UI.
    text = apply_framing(raw)
    citations = _extract_citations(raw, retrieved)  # TODO: parse [chunk_id] refs
    return Answer(text=text, citations=citations, safety_flag="none")


def _extract_citations(raw: str, retrieved) -> list[Citation]:
    """TODO: parse [chunk_id] markers from the model output and map each to a
    Citation(chunk_id, filename, page)."""
    return []
