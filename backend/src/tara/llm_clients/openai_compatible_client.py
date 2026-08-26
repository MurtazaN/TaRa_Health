"""Calls a local text-generation model served by an OpenAI-compatible server.

Runs fully on-device — no data leaves the machine. One of the two local
backends (the other is Ollama; which one `get_llm_client` uses is chosen by
config.local_llm_backend). LM Studio is the reference server: it exposes an
OpenAI-style chat-completions endpoint at config.local_openai_base_url.
"""
from __future__ import annotations

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
