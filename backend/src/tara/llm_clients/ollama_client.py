"""Calls a local text-generation model served by Ollama.

Runs fully on-device — no data leaves the machine. One of the two local
backends (the other is an OpenAI-compatible server such as LM Studio; which one
`get_llm_client` uses is chosen by config.local_llm_backend).
"""
from __future__ import annotations

from typing import Any

import ollama

from tara.config import get_settings


class OllamaClient:
    """LLMClient backed by an Ollama server at config.ollama_host."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        settings = get_settings()
        ollama_api_client = ollama.Client(host=settings.ollama_host)
        response = ollama_api_client.chat(
            model=settings.local_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response["message"]["content"]

    def generate_structured_json(
        self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]
    ) -> str:
        """Return raw JSON text constrained to `json_schema` by Ollama.

        Ollama takes the schema as `format`, where an OpenAI-compatible server
        takes a `response_format` envelope — the reason this method is
        implemented per backend rather than once over a shared HTTP shape.
        """
        settings = get_settings()
        ollama_api_client = ollama.Client(host=settings.ollama_host)
        response = ollama_api_client.chat(
            model=settings.local_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format=json_schema,
        )
        return response["message"]["content"]
