"""Calls the hosted (remote) frontier model — the only code path where document
text may leave the device (§7).

Used only in model_mode 'hosted', or 'hybrid' with an explicit per-query opt-in.
Sends the MINIMUM payload: the assembled excerpts + question, never the whole
corpus.
"""
from __future__ import annotations


class HostedLLMClient:
    """LLMClient backed by a remote provider (wired up in Slice 2)."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # TODO (Slice 2): call the hosted provider with settings.hosted_model,
        #       keeping the payload to the system prompt + one assembled prompt.
        raise NotImplementedError
