"""Local, on-device embeddings via sentence-transformers. No data leaves the device."""
from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from tara.config import get_settings


@lru_cache
def _model() -> SentenceTransformer:
    return SentenceTransformer(get_settings().embed_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
