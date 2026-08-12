"""Defines how the app calls a text-generation model.

`LLMClient` is the protocol every backend implements — local (Ollama, or an
OpenAI-compatible server such as LM Studio) and hosted (remote API; document
text leaves the device). `get_llm_client()` selects which backend a caller gets,
driven by `config.model_mode`, so switching local vs hosted is a configuration
change, never a code change (design §3.5).
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """A text-generation backend: takes prompts, returns the model's text."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's text response for one system+user prompt pair."""
        ...


def get_llm_client(prefer_hosted: bool = False) -> "LLMClient":
    """Select the text-generation backend for one request, from config.model_mode.

    - "local"  -> the local client (data stays on device)
    - "hosted" -> the hosted client (data egresses)
    - "hybrid" -> local unless `prefer_hosted` (the per-query opt-in)

    TODO (Slice 2): route "local" by config.local_llm_backend — OllamaClient vs the
    OpenAI-compatible client (LM Studio). Until then local always means Ollama.
    """
    from tara.config import get_settings
    from tara.llm_clients.hosted_client import HostedLLMClient
    from tara.llm_clients.ollama_client import OllamaClient

    model_mode = get_settings().model_mode
    if model_mode == "hosted":
        return HostedLLMClient()
    if model_mode == "hybrid" and prefer_hosted:
        return HostedLLMClient()
    return OllamaClient()
