"""Calls a local text-generation model served by an OpenAI-compatible server.

Runs fully on-device — no data leaves the machine. One of the two local
backends (the other is Ollama; which one `get_llm_client` uses is chosen by
config.local_llm_backend). LM Studio is the reference server: it exposes an
OpenAI-style chat-completions endpoint at config.local_openai_base_url.
"""
from __future__ import annotations

from typing import Any

from openai import OpenAI

from tara.config import get_settings


class OpenAICompatibleClient:
    """LLMClient backed by an OpenAI-compatible server at config.local_openai_base_url."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        settings = get_settings()
        openai_api_client = OpenAI(
            base_url=settings.local_openai_base_url,
            api_key=settings.local_api_key,
            timeout=settings.llm_timeout_seconds,
        )
        response = openai_api_client.chat.completions.create(
            model=settings.local_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return str(response.choices[0].message.content)

    def generate_structured_json(
        self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]
    ) -> str:
        """Return raw JSON text constrained to `json_schema` by the server.

        `strict: True` is what turns the schema from a request into a
        constraint: a conforming server rejects non-conforming tokens during
        sampling, so a malformed shape cannot come back at all.
        """
        settings = get_settings()
        openai_api_client = OpenAI(
            base_url=settings.local_openai_base_url,
            api_key=settings.local_api_key,
            timeout=settings.llm_timeout_seconds,
        )
        response = openai_api_client.chat.completions.create(
            model=settings.local_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_answer",
                    "schema": json_schema,
                    "strict": True,
                },
            },
        )
        return str(response.choices[0].message.content)
