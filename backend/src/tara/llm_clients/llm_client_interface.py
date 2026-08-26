"""Defines how the app calls a text-generation model.

`LLMClient` is the protocol every backend implements — local (Ollama, or an
OpenAI-compatible server such as LM Studio) and hosted (remote API; document
text leaves the device). `get_llm_client()` selects which backend a caller gets,
driven by `config.generation_mode`, so switching local vs hosted is a configuration
change, never a code change (design §3.5).
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """A text-generation backend: takes prompts, returns the model's text."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's text response for one system+user prompt pair."""
        ...


def get_llm_client(prefer_agent_platform: bool = False) -> "LLMClient":
    """Select the text-generation backend for one request, from generation_mode.

    - "local"          -> the configured on-device client (nothing leaves the device)
    - "agent_platform" -> Google Cloud Agent Platform (excerpts egress)
    - "hybrid"         -> local unless `prefer_agent_platform` (the per-query opt-in)

    Local routing honours config.local_llm_backend: "openai_compatible" (LM Studio)
    or "ollama". Both run on-device; the choice is which server is running.

    The Agent Platform client is imported INSIDE the two egress branches: the
    local path must not pull the egress library (and the whole Vertex stack it
    loads) merely to decide it does not need it.
    """
    from tara.config import get_settings
    from tara.llm_clients.ollama_client import OllamaClient
    from tara.llm_clients.openai_compatible_client import OpenAICompatibleClient

    settings = get_settings()
    if settings.generation_mode == "agent_platform":
        from tara.llm_clients.agent_platform_client import AgentPlatformClient

        return AgentPlatformClient()
    if settings.generation_mode == "hybrid" and prefer_agent_platform:
        from tara.llm_clients.agent_platform_client import AgentPlatformClient

        return AgentPlatformClient()
    if settings.local_llm_backend == "openai_compatible":
        return OpenAICompatibleClient()
    return OllamaClient()
