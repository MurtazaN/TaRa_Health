"""Calls a local text-generation model served by Ollama.

Runs fully on-device — no data leaves the machine. One of the two local
backends (the other is an OpenAI-compatible server such as LM Studio; which one
`get_llm_client` uses is chosen by config.local_llm_backend).
"""
from __future__ import annotations

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
