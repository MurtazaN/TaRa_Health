"""Hosted frontier model. Only used in hosted mode, or hybrid mode when the user
explicitly opts in for a given question. Send the MINIMUM: assembled context +
question — never the whole corpus.
"""
from __future__ import annotations


class HostedClient:
    def complete(self, system: str, user: str) -> str:
        # TODO: call the hosted provider with settings.hosted_model.
        #       Keep the payload to system + the single assembled prompt.
        raise NotImplementedError
