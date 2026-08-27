"""The typed shape the answering model must return (M4 contract, handoff §3.1 rows 1-2).

A typed object rather than free text with `[chunk_id]` markers: the identifiers
arrive as a list, so citation mapping is a lookup rather than a parse, and a
schema-constrained server cannot emit a shape the app must repair.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GroundedAnswer(BaseModel):
    """One answer plus the chunk identifiers it was drawn from.

    An abstention is an empty `cited_chunk_ids`, not a separate flag: "the model
    declined" and "the model cited nothing" must never be able to disagree.
    """

    answer_text: str = Field(description="The answer, or a refusal if the excerpts do not support one.")
    cited_chunk_ids: list[str] = Field(description="Excerpt ids the answer was drawn from; empty if none.")


# Hand-written rather than derived from GroundedAnswer.model_json_schema():
# `strict: true` requires additionalProperties=false, which Pydantic does not
# emit, and OpenAI's own converter for that is a private helper. Two fields are
# cheaper to keep correct by hand than to depend on a private API for.
GROUNDED_ANSWER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer_text": {"type": "string"},
        "cited_chunk_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer_text", "cited_chunk_ids"],
    "additionalProperties": False,
}
