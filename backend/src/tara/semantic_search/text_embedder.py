"""Local, on-device embeddings from an in-process sentence-transformers model.

Design §3.1e/§7: embeddings run on-device and never egress, in every generation
mode — only the answering step may leave the device. Vectors are L2-normalized so
the vector store's L2 distance is monotonic with cosine similarity (see retrieval).

Queries and documents are embedded with DIFFERENT prompts, and the model applies
NEITHER unless one is named (its `default_prompt_name` is null). Omitting the
query prompt fails silently: the question still yields a valid unit vector, but
one placed where documents live, so retrieval favours passages that RESEMBLE the
question over passages that ANSWER it. Nothing raises and scores stay plausible.
See M5 §6.3.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING

from tara.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# The model's own prompt name for the query side. Documents pass no prompt,
# because this model's "document" prompt is the empty string.
_QUERY_PROMPT_NAME = "query"

# Headroom kept below the model's sequence limit, as a fraction of it (M5 §5.5).
# The chunker measures tokens as characters // 4 — an ESTIMATE — and its inner
# loop may overshoot `target_tokens` by up to one whole line before it stops. A
# guard sitting exactly on the limit would therefore pass at configuration time
# and still truncate a real chunk, which is the silent failure the guard exists
# to prevent.
_SEQUENCE_LIMIT_SAFETY_MARGIN_FRACTION = 0.10


@lru_cache
def _model() -> "SentenceTransformer":
    """Load the pinned embedding model once, in-process.

    Imported lazily so that merely importing this module does not pull torch,
    and so tests can replace this accessor without loading 1.19 GB of weights.
    """
    import torch
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    # Pinned by revision, not just name: an unpinned model silently changes the
    # vector space between installs, which would make every retrieval test
    # measure a moving target (the same lesson as the pinned en_core_web_lg wheel).
    return SentenceTransformer(
        settings.embed_model,
        revision=settings.embed_model_revision,
        # When true, load only what is already cached instead of silently pulling
        # ~1.19 GB from Hugging Face on a cold cache — which would break the
        # "works fully offline" guarantee on a bare host (M5 §4.3). The container
        # gets the same effect from HF_HUB_OFFLINE.
        local_files_only=settings.embed_model_offline_only,
        # Load dtype is a performance cliff, not a detail: the weights ship as
        # bfloat16, which torch's aarch64 CPU build cannot matmul efficiently -
        # measured 456s versus 1.2s for one 446-token chunk. See config.
        model_kwargs={"torch_dtype": getattr(torch, settings.embed_model_dtype)},
    )


def _normalize_to_unit_length(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm < 1e-12:  # all-zero (or underflowed) vector: nothing to normalize
        return vector
    return [component / norm for component in vector]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts as DOCUMENTS, preserving input order. Unit vectors."""
    if not texts:
        return []
    encoded_vectors = _model().encode(texts)
    if len(encoded_vectors) != len(texts):
        # A partial batch would silently leave chunks un-vectorized (zip truncates
        # downstream); fail loudly so the pipeline's cleanup path catches it.
        raise RuntimeError(
            f"Embedding model returned {len(encoded_vectors)} vectors "
            f"for {len(texts)} inputs."
        )
    return [_normalize_to_unit_length(list(vector)) for vector in encoded_vectors]


def embed_query(text: str) -> list[float]:
    """Embed one QUERY. `prompt_name` is mandatory — see the module docstring."""
    encoded_vector = _model().encode(text, prompt_name=_QUERY_PROMPT_NAME)
    return _normalize_to_unit_length(list(encoded_vector))


def model_max_sequence_length() -> int:
    """The loaded model's input ceiling, in tokens.

    Chunking must stay under this: sentence-transformers TRUNCATES SILENTLY past
    it, which would drop text from a chunk's vector while the full text is still
    stored and cited.
    """
    sequence_length = _model().max_seq_length
    if sequence_length is None:
        # sentence-transformers types this Optional (some model configs omit it);
        # fail loudly rather than let a silent truncation risk go unvalidated.
        raise RuntimeError(
            "Embedding model does not report a max_seq_length; cannot verify "
            "that configured chunk sizes fit without silent truncation."
        )
    return sequence_length


def usable_chunk_token_ceiling() -> int:
    """The largest chunk size accepted, i.e. the model's limit minus the margin.

    Kept separate from the check so the ceiling can be reported in the failure
    message and asserted directly in tests.
    """
    sequence_limit = model_max_sequence_length()
    return int(sequence_limit * (1.0 - _SEQUENCE_LIMIT_SAFETY_MARGIN_FRACTION))


def verify_chunk_size_fits_model() -> None:
    """Fail loudly if the configured chunk size exceeds the model's safe ceiling (M5 §5.5).

    The ceiling is the model's max_seq_length less a 10% margin, not the limit
    itself: chunk sizing is measured with a characters-per-token ESTIMATE that can
    overshoot, so a chunk configured exactly at the limit can still be truncated.
    """
    settings = get_settings()
    sequence_limit = model_max_sequence_length()
    token_ceiling = usable_chunk_token_ceiling()
    if settings.chunk_target_tokens > token_ceiling:
        margin_percent = int(_SEQUENCE_LIMIT_SAFETY_MARGIN_FRACTION * 100)
        raise RuntimeError(
            f"TARA_CHUNK_TARGET_TOKENS={settings.chunk_target_tokens} exceeds {token_ceiling}, "
            f"the embedding model's max_seq_length of {sequence_limit} less a "
            f"{margin_percent}% safety margin. The margin is there because chunk "
            f"sizes are estimated as characters // 4 and can overshoot, so a chunk "
            f"sitting on the limit still risks silent truncation before embedding "
            f"while its full text is stored and cited. Lower the chunk size or "
            f"choose another model."
        )


def probe_embedding_dimension() -> int:
    """Ask the loaded model for the actual embedding dimension (§3.2)."""
    return len(embed_query("dimension probe"))


def verify_embedding_dimension() -> None:
    """Fail loudly if the configured dimension disagrees with the loaded model."""
    settings = get_settings()
    actual_dimension = probe_embedding_dimension()
    if actual_dimension != settings.embed_dim:
        raise RuntimeError(
            f"TARA_EMBED_DIM={settings.embed_dim} but embedding model "
            f"'{settings.embed_model}' returns dimension {actual_dimension}. "
            f"Fix the config or re-index."
        )
