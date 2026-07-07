"""Answers a user's question from their documents — the full Phase 1 query flow.

`answer_question()` is the single entry point the API calls (§5.2):

    safety pre-check -> (emergency? stop) -> retrieve chunks -> grounded+cited
    LLM answer -> map citations -> safety framing -> Answer
"""
from __future__ import annotations

from dataclasses import dataclass

from tara.answering.prompts import ANSWER_SYSTEM, build_user_prompt
from tara.llm_clients.interface import get_llm_client
from tara.retrieval.chunk_retriever import retrieve_chunks
from tara.safety.framing import apply_safety_framing
from tara.safety.triage import screen_for_emergency
from tara.storage.models import Citation


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    safety_flag: str  # "none" | "emergency"


def answer_question(question: str, prefer_hosted: bool = False) -> Answer:
    # 1) Safety pre-check — short-circuit on emergencies.
    triage = screen_for_emergency(question)
    if triage.is_emergency:
        return Answer(text=triage.message or "", citations=[], safety_flag="emergency")

    # 2) Retrieve grounding context.
    retrieved = retrieve_chunks(question)
    excerpts = [
        {"chunk_id": r.chunk.chunk_id, "filename": r.filename,
         "page": r.chunk.page, "text": r.chunk.text}
        for r in retrieved
    ]

    # 3) Grounded, citable answer (local by default; hosted only if opted in).
    client = get_llm_client(prefer_hosted=prefer_hosted)
    raw_answer = client.generate(ANSWER_SYSTEM, build_user_prompt(question, excerpts))

    # 4) Map cited chunk_ids -> Citations, then append safety framing (§3.5 order).
    framed_text = apply_safety_framing(raw_answer)
    citations = _map_cited_chunks_to_citations(raw_answer, retrieved)
    return Answer(text=framed_text, citations=citations, safety_flag="none")


def _map_cited_chunks_to_citations(raw_answer: str, retrieved) -> list[Citation]:
    """Parse the [chunk_id] markers the model emitted and map each to a Citation.

    TODO (Slice 2/3): implement the parse + the numeric-grounding check that
    runs between citation mapping and framing (§3.5 post-processing order)."""
    return []
