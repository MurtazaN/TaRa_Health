"""Local, on-device embeddings via an OpenAI-compatible endpoint (LM Studio).

Design §3.1e/§7: embeddings run on-device and never egress, in every model mode
— only the answering step may leave the device. Vectors are L2-normalized so the
vector store's L2 distance is monotonic with cosine similarity (see retrieval).
"""
from __future__ import annotations

import math
from functools import lru_cache

from openai import OpenAI

from tara.config import get_settings


@lru_cache
def _embedding_api_client() -> OpenAI:
    s = get_settings()
    # LM Studio serves an OpenAI-compatible API at {lmstudio_host}/v1 and ignores
    # the key; the client still requires a non-empty value (config.local_api_key).
    return OpenAI(
        base_url=s.local_openai_base_url,
        api_key=s.local_api_key,
        timeout=s.llm_timeout_seconds,
    )


def _normalize_to_unit_length(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-12:  # all-zero (or underflowed) vector: nothing to normalize
        return vec
    return [x / norm for x in vec]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, preserving input order. Returns unit vectors."""
    if not texts:
        return []
    s = get_settings()
    resp = _embedding_api_client().embeddings.create(model=s.embed_model, input=texts)
    # The API tags each vector with its input index; sort defensively.
    ordered = sorted(resp.data, key=lambda d: d.index)
    if len(ordered) != len(texts):
        # A partial batch would silently leave chunks un-vectorized (zip truncates
        # downstream); fail loudly so the pipeline's cleanup path catches it.
        raise RuntimeError(
            f"Embedding endpoint returned {len(ordered)} vectors for {len(texts)} inputs."
        )
    return [_normalize_to_unit_length(list(d.embedding)) for d in ordered]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def probe_embedding_dimension() -> int:
    """Ask the live endpoint for the actual embedding dimension (§3.2).

    Requires the embedding server to be reachable; used by startup validation,
    not on the request hot path.
    """
    return len(embed_query("dimension probe"))


def verify_embedding_dimension() -> None:
    """Fail loudly if the configured dimension disagrees with the live model."""
    s = get_settings()
    actual = probe_embedding_dimension()
    if actual != s.embed_dim:
        raise RuntimeError(
            f"TARA_EMBED_DIM={s.embed_dim} but embedding model '{s.embed_model}' "
            f"returns dimension {actual}. Fix the config or re-index."
        )
