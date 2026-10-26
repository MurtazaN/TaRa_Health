"""Turns a backend's raw JSON into a validated object, retrying a bad shape.

The single validation point for every backend (handoff §3.1 row 1, satisfied
without Instructor per the M4 plan's decision 4). Each backend constrains its
own server to the schema; this module is what happens when a server honours the
schema loosely, or not at all.
"""
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from tara.app_errors import StructuredOutputError
from tara.llm_clients.llm_client_interface import get_llm_client

ModelT = TypeVar("ModelT", bound=BaseModel)

# Three attempts: one honest try, one correction, one margin. An unbounded loop
# would hang a request against a model that simply cannot satisfy the schema.
MAX_STRUCTURED_ATTEMPTS = 3

_CORRECTION_NOTE = (
    "\n\nYour previous reply was not valid JSON for the required schema. "
    "Reply again with ONLY a JSON object matching the schema exactly."
)


def generate_structured_object(
    system_prompt: str,
    user_prompt: str,
    response_model: type[ModelT],
    json_schema: dict[str, Any],
    prefer_agent_platform: bool = False,
) -> ModelT:
    """Return one validated `response_model` instance from the selected backend.

    The correction note appended on retry names the failure class only, never the
    rejected payload: a malformed payload may carry document text, and echoing it
    back doubles the egress for no benefit.
    """
    llm_client = get_llm_client(prefer_agent_platform=prefer_agent_platform)
    attempted_prompt = user_prompt
    for attempt in range(1, MAX_STRUCTURED_ATTEMPTS + 1):
        raw_json = llm_client.generate_structured_json(
            system_prompt, attempted_prompt, json_schema
        )
        try:
            return response_model.model_validate_json(raw_json)
        except ValidationError:
            if attempt == MAX_STRUCTURED_ATTEMPTS:
                break
            attempted_prompt = user_prompt + _CORRECTION_NOTE
    raise StructuredOutputError(
        f"The model did not return output matching the {response_model.__name__} "
        f"schema within {MAX_STRUCTURED_ATTEMPTS} attempts."
    )
