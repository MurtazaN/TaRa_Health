"""On-device model via Ollama. Default path — data never leaves the machine."""
from __future__ import annotations

import ollama

from tara.config import get_settings


class LocalOllamaClient:
    def complete(self, system: str, user: str) -> str:
        settings = get_settings()
        client = ollama.Client(host=settings.ollama_host)
        resp = client.chat(
            model=settings.local_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp["message"]["content"]
