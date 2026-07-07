"""Prompt templates for grounded, citable answering."""
from __future__ import annotations

ANSWER_SYSTEM_PROMPT = """You are Tara, a personal health & insurance assistant.
Answer using ONLY the document excerpts provided. Each excerpt has an ID.
When you state a fact, cite the excerpt ID(s) it came from, like [chunk_id].
If the excerpts do not contain the answer, say you don't see it in their
documents — do NOT guess or invent coverage amounts, results, or policy terms.
Frame any health information as general information, not a diagnosis, and suggest
professional care for anything serious or persistent."""


def build_user_prompt(question: str, excerpts: list[dict]) -> str:
    """Assemble the user-role prompt: tagged document excerpts, then the question.

    excerpts: [{chunk_id, filename, page, text}, ...]
    """
    excerpt_blocks = [
        f"[{excerpt['chunk_id']}] (source: {excerpt['filename']}, p.{excerpt['page']})\n"
        f"{excerpt['text']}"
        for excerpt in excerpts
    ]
    excerpts_text = "\n\n".join(excerpt_blocks)
    return f"Excerpts:\n{excerpts_text}\n\nQuestion: {question}"
