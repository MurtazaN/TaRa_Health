"""LLM client interface. The rest of the app depends only on this protocol, so
local vs hosted is a config decision, not a code change.
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's text response."""
        ...


def get_client(prefer_hosted: bool = False) -> "LLMClient":
    """Pick a client based on config.model_mode.

    - local  -> always LocalOllamaClient
    - hosted -> always HostedClient
    - hybrid -> LocalOllamaClient unless prefer_hosted (the per-query opt-in)
    """
    from tara.config import get_settings
    from tara.llm.hosted import HostedClient
    from tara.llm.local_ollama import LocalOllamaClient

    mode = get_settings().model_mode
    if mode == "hosted":
        return HostedClient()
    if mode == "hybrid" and prefer_hosted:
        return HostedClient()
    return LocalOllamaClient()
