"""Answers a user's question from their documents — the full Epic 1 query flow.

`answer_question()` is the single entry point the API calls (§5.2):

    safety pre-check -> (emergency? stop) -> retrieve -> (nothing? abstain) ->
    grounded structured answer -> map citations -> verify figures ->
    safety framing -> audit row -> Answer

The post-processing ORDER is fixed by the M4 contract and is load-bearing:
citations are mapped before figures are verified, because a figure is only
grounded if it appears in a CITED excerpt; framing is appended last, so no
generated disclaimer is ever inspected as if it were grounded content.
"""
from __future__ import annotations

from dataclasses import dataclass

from opentelemetry.trace import Span

from tara.data_models import Citation
from tara.execution_tracing.span_emitter import record_span_attribute, traced_span
from tara.llm_clients.llm_client_interface import resolve_model_route
from tara.llm_clients.structured_completion import generate_structured_object
from tara.local_data_stores.query_records import insert_query_record
from tara.question_answering.answer_prompts import ANSWER_SYSTEM_PROMPT, build_user_prompt
from tara.question_answering.answer_response_model import (
    GROUNDED_ANSWER_JSON_SCHEMA,
    GroundedAnswer,
)
from tara.question_answering.numeric_grounding import verify_numbers_are_grounded
from tara.safety_checks.answer_framing import apply_safety_framing
from tara.safety_checks.emergency_triage import screen_for_emergency
from tara.semantic_search.chunk_retriever import RetrievedChunk, retrieve_chunks

# One wording for every decline, whatever caused it. A user cannot act on the
# difference between "retrieval found nothing" and "the figure was ungrounded",
# and varying the wording would leak how the machinery failed.
ABSTENTION_MESSAGE = "I don't see that in your documents."

# How much cited text the interface shows beside a citation.
_SNIPPET_CHARACTER_LIMIT = 240

# Written into the audit row's answer column when generation itself fails. Names
# the failure CLASS only: the row records THAT a request happened, and is not a
# place to keep an upstream error's text.
GENERATION_FAILURE_MARKER = "<generation failed: {failure_type}>"


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    safety_flag: str  # "none" | "emergency"


def _map_cited_chunks_to_citations(
    cited_chunk_ids: list[str], retrieved_chunks: list[RetrievedChunk]
) -> list[Citation]:
    """Map the identifiers the model returned onto the chunks actually retrieved.

    An identifier the model returned that was never retrieved is DROPPED, not
    resolved: a model inventing a chunk id is precisely the failure citations
    exist to catch, and rendering it would attach a source to a fact that has
    none. Order follows the model's own citation order.
    """
    retrieved_by_id = {
        retrieved.chunk.chunk_id: retrieved for retrieved in retrieved_chunks
    }
    citations: list[Citation] = []
    for cited_chunk_id in cited_chunk_ids:
        retrieved = retrieved_by_id.get(cited_chunk_id)
        if retrieved is None:
            continue
        citations.append(Citation(
            chunk_id=retrieved.chunk.chunk_id,
            filename=retrieved.filename,
            page=retrieved.chunk.page,
            char_start=retrieved.chunk.char_start,
            char_end=retrieved.chunk.char_end,
            snippet=retrieved.chunk.text[:_SNIPPET_CHARACTER_LIMIT],
        ))
    return citations


def _record_query(
    span: Span,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    answer: Answer,
    model_route: str,
) -> None:
    """Write the audit row, never letting a logging fault destroy an answer."""
    try:
        insert_query_record(
            question=question,
            retrieved_chunk_ids=[retrieved.chunk.chunk_id for retrieved in retrieved_chunks],
            answer=answer.text,
            citations=answer.citations,
            safety_flag=answer.safety_flag,
            model_route=model_route,
        )
    except Exception as audit_error:  # noqa: BLE001 - the answer outranks the log
        record_span_attribute(span, "audit_write_failed", type(audit_error).__qualname__)


def _abstain(
    span: Span,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    model_route: str,
    abstain_reason: str,
) -> Answer:
    """Return the one decline wording, recording WHY on the span only.

    The reason is diagnostic and stays in the trace; the user sees one message,
    because "retrieval was weak" and "the model invented a figure" call for the
    same action from them and different wording would only leak the mechanism.
    """
    answer = Answer(
        text=apply_safety_framing(ABSTENTION_MESSAGE), citations=[], safety_flag="none"
    )
    record_span_attribute(span, "abstained", True)
    record_span_attribute(span, "abstain_reason", abstain_reason)
    _record_query(span, question, retrieved_chunks, answer, model_route)
    return answer


def answer_question(question: str, prefer_agent_platform: bool = False) -> Answer:
    """Return a grounded, cited answer to `question`, or the one decline wording.

    Emergencies short-circuit before retrieval and generation, so the answering
    model can never reason one away; every terminal outcome writes one audit row.
    """
    model_route = resolve_model_route(prefer_agent_platform)
    with traced_span("ask_question", model_route=model_route) as ask_span:
        # 1) Safety pre-check — short-circuits before retrieval and generation.
        triage_result = screen_for_emergency(question)
        if triage_result.is_emergency:
            emergency_answer = Answer(
                text=triage_result.message or "", citations=[], safety_flag="emergency"
            )
            record_span_attribute(ask_span, "safety_flag", "emergency")
            _record_query(ask_span, question, [], emergency_answer, model_route)
            return emergency_answer
        record_span_attribute(ask_span, "safety_flag", "none")

        # 2) Retrieve grounding context.
        retrieved_chunks = retrieve_chunks(question)
        if not retrieved_chunks:
            # Abstain WITHOUT a model call: asking a model to answer from no
            # excerpts invites exactly the fabrication this module prevents.
            return _abstain(ask_span, question, retrieved_chunks, model_route, "no_context")

        # 3) Grounded, citable answer (local by default; egress only if opted in).
        excerpts = [
            {"chunk_id": retrieved.chunk.chunk_id, "filename": retrieved.filename,
             "page": retrieved.chunk.page, "text": retrieved.chunk.text}
            for retrieved in retrieved_chunks
        ]
        try:
            with traced_span("llm_generate", model_route=model_route):
                generated: GroundedAnswer = generate_structured_object(
                    ANSWER_SYSTEM_PROMPT,
                    build_user_prompt(question, excerpts),
                    GroundedAnswer,
                    GROUNDED_ANSWER_JSON_SCHEMA,
                    prefer_agent_platform=prefer_agent_platform,
                )
        except Exception as generation_error:
            # Record BEFORE re-raising. A failure is a terminal outcome like any
            # other, and on the egress path this row is the only local evidence
            # that an attempt to send excerpts off the device was ever made.
            # Re-raised rather than abstained: a broken model must not read as
            # "I don't see that in your documents", which would hide a fault
            # behind a plausible answer.
            _record_query(
                ask_span,
                question,
                retrieved_chunks,
                Answer(
                    text=GENERATION_FAILURE_MARKER.format(
                        failure_type=type(generation_error).__qualname__
                    ),
                    citations=[],
                    safety_flag="none",
                ),
                model_route,
            )
            raise

        # 4) Map cited ids -> Citations (contract post-processing step 1).
        with traced_span("map_citations") as citation_span:
            citations = _map_cited_chunks_to_citations(
                generated.cited_chunk_ids, retrieved_chunks
            )
            record_span_attribute(
                citation_span, "invented_id_count",
                len(generated.cited_chunk_ids) - len(citations),
            )
        if not citations:
            return _abstain(ask_span, question, retrieved_chunks, model_route, "no_citations")

        # 5) Numeric grounding (contract post-processing step 2). The FULL text
        # of each cited chunk is the grounding source, never citation.snippet:
        # the snippet is truncated for display, so a figure further into the
        # chunk would be judged ungrounded and abstain a correct answer.
        cited_chunk_ids = {citation.chunk_id for citation in citations}
        cited_chunk_texts = [
            retrieved.chunk.text
            for retrieved in retrieved_chunks
            if retrieved.chunk.chunk_id in cited_chunk_ids
        ]
        grounding_verdict = verify_numbers_are_grounded(
            generated.answer_text, cited_chunk_texts
        )
        if not grounding_verdict.is_grounded:
            record_span_attribute(
                ask_span, "ungrounded_figure_count", len(grounding_verdict.ungrounded_figures)
            )
            return _abstain(ask_span, question, retrieved_chunks, model_route, "ungrounded_figure")

        # 6) Framing last (contract post-processing step 3), then the audit row.
        answer = Answer(
            text=apply_safety_framing(generated.answer_text),
            citations=citations,
            safety_flag="none",
        )
        record_span_attribute(ask_span, "abstained", False)
        record_span_attribute(ask_span, "citation_count", len(citations))
        _record_query(ask_span, question, retrieved_chunks, answer, model_route)
        return answer
