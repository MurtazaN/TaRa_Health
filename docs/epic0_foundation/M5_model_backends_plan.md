# Epic 0 · M5 — model_backends · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app two real model backends — hosted generation on Google Cloud Agent Platform, and embeddings running in-process — so it no longer depends on LM Studio and no longer sends documents anywhere to be indexed.

**Architecture:** One new plane module, `llm_clients/agent_platform_client.py`, implements the existing `LLMClient` protocol over LangChain. `semantic_search/text_embedder.py` is rewritten onto in-process `sentence-transformers`. LangChain touches generation only; embeddings never leave the process.

**Tech Stack:** `langchain-google-genai` · `langchain-google-vertexai` · `sentence-transformers` (already installed) · Application Default Credentials

**Spec:** [M5_model_backends.md](M5_model_backends.md) — read it alongside this plan. Where the two disagree, the spec wins.

## Global Constraints

- Python 3.11+; `from __future__ import annotations` at the top of every module.
- Import direction: kernel (`config`, `data_models`, `app_errors`) ← planes (`llm_clients`, `local_data_stores`) ← capabilities (`document_ingestion`, `semantic_search`, `question_answering`) ← `safety_checks` ← `web_app`. Capabilities never import each other.
- No SQL outside `local_data_stores/`. This module adds none.
- Fail closed: no bare `except`. A failure raises rather than silently degrading.
- **No PHI in exception messages, log records, or span attributes.** `web_app.py` renders `str(exc)` straight to the client.
- Naming: every name carries its object; modules are noun phrases; functions are verb+object; no single-letter variables.
- Docstrings state purpose first, rationale second.
- CI must never download the 1.19 GB embedding model.

---

## Task Order and Rationale

| Task | Deliverable | Why here |
|---|---|---|
| 1 | Config surface renamed, validators conditional | Everything else depends on the new setting names |
| 2 | In-process embedder | Fully independent of generation; the highest-value half |
| 3 | Chunking coupled to the model's sequence limit | Needs Task 2's `model_max_sequence_length()` |
| 4 | `AgentPlatformClient` + routing | Needs Task 1's settings; adds the two dependencies |
| 5 | Error taxonomy, HTTP mapping, startup validation | Needs Tasks 2 and 4 to have something to classify |
| 6 | Container, bootstrap, docs | Packaging for what Tasks 1–5 built |

---

### Task 1: Rename the generation mode and retire the hosted credential

**Files:**
- Modify: `backend/src/tara/config.py`
- Modify: `backend/src/tara/llm_clients/llm_client_interface.py:22-41`
- Modify: `backend/src/tara/question_answering/question_answerer.py:27,42`
- Modify: `backend/src/tara/web_app.py:43,72`
- Modify: `backend/tests/conftest.py:34,82`
- Modify: `deployment/docker/compose.yaml:16`
- Modify: `.env.example`
- Test: `backend/tests/test_config.py`, `backend/tests/llm_clients/test_llm_client_interface.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.generation_mode: Literal["local","agent_platform","hybrid"]`, `Settings.gcp_project: str`, `Settings.gcp_location: str`, `Settings.agent_platform_provider: Literal["gemini","llama","mistral"]`, `Settings.gemini_model: str`, `Settings.llama_model: str`, `Settings.mistral_model: str`, `Settings.embed_model_revision: str`, `Settings.phi_egress_acknowledged: bool`, `get_llm_client(prefer_agent_platform: bool = False) -> LLMClient`.

- [ ] **Step 1: Write the failing config tests**

Replace the whole of `backend/tests/test_config.py` lines 16-40 (the five hosted-key tests) with:

```python
@pytest.mark.unit
def test_local_mode_needs_no_gcp_project():
    # Nothing egresses in local mode, so demanding a project would be theatre.
    s = _settings(generation_mode="local", gcp_project="", phi_egress_acknowledged=False)
    assert s.generation_mode == "local"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_require_a_gcp_project(mode):
    with pytest.raises(ValidationError, match="TARA_GCP_PROJECT"):
        _settings(generation_mode=mode, gcp_project="", phi_egress_acknowledged=True)


@pytest.mark.unit
def test_blank_gcp_project_is_treated_as_missing():
    with pytest.raises(ValidationError, match="TARA_GCP_PROJECT"):
        _settings(generation_mode="agent_platform", gcp_project="   ",
                  phi_egress_acknowledged=True)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_require_acknowledgement(mode):
    with pytest.raises(ValidationError, match="TARA_PHI_EGRESS_ACKNOWLEDGED"):
        _settings(generation_mode=mode, gcp_project="my-project",
                  phi_egress_acknowledged=False)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_accept_project_and_acknowledgement(mode):
    s = _settings(generation_mode=mode, gcp_project="my-project",
                  phi_egress_acknowledged=True)
    assert s.generation_mode == mode
    assert s.gcp_location == "us-central1"


@pytest.mark.unit
def test_embed_model_is_pinned_by_revision():
    # An unpinned model silently changes the vector space between installs.
    s = _settings()
    assert s.embed_model == "Qwen/Qwen3-Embedding-0.6B"
    assert len(s.embed_model_revision) == 40  # a full git SHA
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_config.py -v
```
Expected: FAIL — `Settings` has no field `generation_mode`.

- [ ] **Step 3: Rewrite the config surface**

In `backend/src/tara/config.py`, replace the `LocalLLMBackend` type alias line with:

```python
LocalLLMBackend = Literal["ollama", "openai_compatible"]
GenerationMode = Literal["local", "agent_platform", "hybrid"]
AgentPlatformProvider = Literal["gemini", "llama", "mistral"]
```

Replace the `# ---- Model mode (§3.5) ----` block and the `# ---- Hosted model ----` block with:

```python
    # ---- Generation mode (§3.5) ----
    # Governs GENERATION ONLY. Embeddings always run in-process and never egress,
    # so a single setting can no longer describe both (M5 §4.2).
    generation_mode: GenerationMode = "local"

    # ---- Google Cloud Agent Platform (formerly Vertex AI) — GENERATION ONLY ----
    # Required only when generation may egress. An empty project is the exact
    # condition under which LangChain's backend auto-detection silently falls back
    # to the consumer Gemini Developer API (generativelanguage.googleapis.com),
    # which is NOT BAA-covered. Fail closed rather than egress to the wrong product.
    gcp_project: str = ""
    gcp_location: str = "us-central1"  # MaaS models are region-limited
    agent_platform_provider: AgentPlatformProvider = "gemini"
    # Model IDs are perishable: gemini-2.5-flash retires 2026-10-20, and the Llama
    # allowlist is frozen per langchain-google-vertexai release. Validated at startup.
    gemini_model: str = "gemini-3.5-flash"
    llama_model: str = "meta/llama-3.3-70b-instruct-maas"
    mistral_model: str = "mistral-medium-3"

    # Records that a human asserted a signed GCP BAA covers Agent Platform. It
    # cannot check that; it only refuses to egress until someone says so.
    phi_egress_acknowledged: bool = False
```

Replace the `# ---- Embeddings ----` block with:

```python
    # ---- Embeddings (in-process; never egress, in any generation mode) ----
    # Pinned by revision, not just name, for the same reason en_core_web_lg is a
    # pinned wheel: an unpinned model silently changes the vector space between
    # installs and makes every retrieval test measure a moving target.
    embed_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embed_model_revision: str = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    embed_dim: int = 1024
```

Add to the chunking-adjacent settings (place directly after `max_pdf_pages`):

```python
    # ---- Chunking (coupled to the embedding model — see M5 §5.5) ----
    # sentence-transformers TRUNCATES SILENTLY past the model's sequence limit, so
    # startup validates these against it rather than trusting the default.
    chunk_target_tokens: int = 800
    chunk_overlap_tokens: int = 100
```

Replace `_require_hosted_key_when_egressing` entirely with:

```python
    @model_validator(mode="after")
    def _require_gcp_project_when_generation_egresses(self) -> "Settings":
        """Fail loudly if generation may egress without a project (M5 §5.4).

        Conditional because egress is conditional: in "local" mode nothing leaves
        the device. An empty project is what makes LangChain fall back to the
        consumer Gemini API, so this is the guard against silent mis-routing.
        """
        if self.generation_mode in ("agent_platform", "hybrid") and not self.gcp_project.strip():
            raise ValueError(
                "generation_mode is 'agent_platform'/'hybrid' but TARA_GCP_PROJECT is "
                "empty. An empty project silently routes generation to the consumer "
                "Gemini Developer API, which is not covered by a GCP BAA."
            )
        return self

    @model_validator(mode="after")
    def _require_phi_egress_acknowledgement(self) -> "Settings":
        """Refuse to egress until a human has asserted a BAA is in place."""
        if self.generation_mode in ("agent_platform", "hybrid") and not self.phi_egress_acknowledged:
            raise ValueError(
                "generation_mode is 'agent_platform'/'hybrid' but "
                "TARA_PHI_EGRESS_ACKNOWLEDGED is false. Answering a question sends the "
                "retrieved excerpts to Google Cloud. Set this only once a BAA covering "
                "Agent Platform is in place."
            )
        return self
```

- [ ] **Step 4: Run the config tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_config.py -v
```
Expected: PASS.

- [ ] **Step 5: Rename `prefer_hosted` through the call chain**

`backend/src/tara/llm_clients/llm_client_interface.py` — replace lines 22-41 with:

```python
def get_llm_client(prefer_agent_platform: bool = False) -> "LLMClient":
    """Select the text-generation backend for one request, from generation_mode.

    - "local"          -> the configured on-device client (nothing leaves the device)
    - "agent_platform" -> Google Cloud Agent Platform (excerpts egress)
    - "hybrid"         -> local unless `prefer_agent_platform` (the per-query opt-in)

    Local routing honours config.local_llm_backend: "openai_compatible" (LM Studio)
    or "ollama". Both run on-device; the choice is which server is running.
    """
    from tara.config import get_settings
    from tara.llm_clients.agent_platform_client import AgentPlatformClient
    from tara.llm_clients.ollama_client import OllamaClient

    settings = get_settings()
    if settings.generation_mode == "agent_platform":
        return AgentPlatformClient()
    if settings.generation_mode == "hybrid" and prefer_agent_platform:
        return AgentPlatformClient()
    return OllamaClient()
```

Also update the module docstring's `config.model_mode` reference to `config.generation_mode`.

> Note: `AgentPlatformClient` does not exist until Task 4. Task 1 leaves this import
> unresolved *only* for the `agent_platform` branch, which no Task 1 test exercises.
> Task 4's first step makes it real. Do not create a placeholder class.

`backend/src/tara/question_answering/question_answerer.py` line 27 and 42:

```python
def answer_question(question: str, prefer_agent_platform: bool = False) -> Answer:
```
```python
    llm_client = get_llm_client(prefer_agent_platform=prefer_agent_platform)
```

`backend/src/tara/web_app.py` line 43 and 72:

```python
    prefer_agent_platform: bool = False
```
```python
    answer = answer_question(payload.question, prefer_agent_platform=payload.prefer_agent_platform)
```

- [ ] **Step 6: Update the routing tests**

Replace `backend/tests/llm_clients/test_llm_client_interface.py` in full:

```python
"""get_llm_client routing: generation_mode x prefer_agent_platform -> backend.

Local mode must NEVER return the Agent Platform client — that is the only code
path by which a generated answer's context leaves the device. Embeddings are
in-process in every mode, so no routing decision can cause ingestion egress.
"""
from __future__ import annotations

import pytest

from tara import config
from tara.llm_clients.agent_platform_client import AgentPlatformClient
from tara.llm_clients.llm_client_interface import get_llm_client
from tara.llm_clients.ollama_client import OllamaClient


@pytest.fixture
def generation_mode(monkeypatch):
    """Set TARA_GENERATION_MODE hermetically (+ the egress prerequisites)."""
    def _set(mode: str) -> None:
        monkeypatch.setenv("TARA_GENERATION_MODE", mode)
        if mode in ("agent_platform", "hybrid"):
            monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
            monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
        config.get_settings.cache_clear()
    yield _set
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_local_mode_uses_local_client(generation_mode):
    generation_mode("local")
    assert isinstance(get_llm_client(), OllamaClient)


@pytest.mark.unit
def test_local_mode_ignores_the_opt_in(generation_mode):
    generation_mode("local")
    # The per-query opt-in must be inert in local mode: no silent egress path.
    assert isinstance(get_llm_client(prefer_agent_platform=True), OllamaClient)


@pytest.mark.unit
def test_agent_platform_mode_uses_agent_platform_client(generation_mode):
    generation_mode("agent_platform")
    assert isinstance(get_llm_client(), AgentPlatformClient)


@pytest.mark.unit
def test_hybrid_defaults_to_local(generation_mode):
    generation_mode("hybrid")
    assert isinstance(get_llm_client(), OllamaClient)


@pytest.mark.unit
def test_hybrid_opt_in_uses_agent_platform(generation_mode):
    generation_mode("hybrid")
    assert isinstance(get_llm_client(prefer_agent_platform=True), AgentPlatformClient)
```

> These five tests will fail until Task 4 creates `AgentPlatformClient`. That is
> expected and correct: mark the file with `pytest.importorskip` is NOT acceptable —
> instead, run Task 1's verification with `--ignore` as shown in Step 8, and Task 4
> removes the ignore.

- [ ] **Step 7: Update fixtures and environment files**

`backend/tests/conftest.py` lines 34 and 82 — change both occurrences:

```python
    monkeypatch.setenv("TARA_GENERATION_MODE", "local")
```

`deployment/docker/compose.yaml` line 16:

```yaml
      TARA_GENERATION_MODE: "local"
```

`.env.example` — replace the `# ---- Model mode ----` and `# ---- Hosted model ----` and `# ---- Embeddings ----` blocks with:

```bash
# ---- Generation mode (governs GENERATION ONLY) ----
# local          = always use the on-device model (private, fully offline)
# agent_platform = always use Google Cloud Agent Platform (opt-in; excerpts leave the device)
# hybrid         = local by default, escalate only when the user opts in per-query
# Embeddings are in-process in EVERY mode and never egress.
TARA_GENERATION_MODE=local

# ---- Google Cloud Agent Platform (generation only) ----
# The startup validator FAILS if generation_mode is agent_platform/hybrid and
# TARA_GCP_PROJECT is empty — an empty project silently routes to the consumer
# Gemini Developer API, which is NOT covered by a GCP BAA.
TARA_GCP_PROJECT=
TARA_GCP_LOCATION=us-central1
TARA_AGENT_PLATFORM_PROVIDER=gemini         # gemini | llama | mistral
TARA_GEMINI_MODEL=gemini-3.5-flash
TARA_LLAMA_MODEL=meta/llama-3.3-70b-instruct-maas
TARA_MISTRAL_MODEL=mistral-medium-3
# Set true ONLY once a signed GCP BAA covers Agent Platform. Nothing checks this
# for you; it records that a human asserted it.
TARA_PHI_EGRESS_ACKNOWLEDGED=false

# ---- Embeddings (in-process; never egress, in any mode) ----
# Pinned by revision so the vector space cannot change between installs.
TARA_EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B
TARA_EMBED_MODEL_REVISION=97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
TARA_EMBED_DIM=1024

# ---- Chunking (validated at startup against the embedding model's limit) ----
TARA_CHUNK_TARGET_TOKENS=800
TARA_CHUNK_OVERLAP_TOKENS=100
```

- [ ] **Step 8: Verify the suite**

```bash
cd backend && python -m pytest tests/ -q --ignore=tests/llm_clients
cd backend && python -m mypy src && python -m ruff check src tests
```
Expected: all pass. `tests/llm_clients` is ignored until Task 4.

- [ ] **Step 9: Commit**

```bash
git add backend/src/tara/config.py backend/src/tara/llm_clients/llm_client_interface.py \
        backend/src/tara/question_answering/question_answerer.py backend/src/tara/web_app.py \
        backend/tests/conftest.py backend/tests/test_config.py \
        backend/tests/llm_clients/test_llm_client_interface.py \
        deployment/docker/compose.yaml .env.example
git commit -m "refactor: rename model_mode to generation_mode and gate egress on a GCP project"
```

---

### Task 2: Move embeddings in-process

**Files:**
- Modify: `backend/src/tara/semantic_search/text_embedder.py` (full rewrite)
- Test: `backend/tests/semantic_search/test_text_embedder.py` (full rewrite)

**Interfaces:**
- Consumes: `Settings.embed_model`, `Settings.embed_model_revision`, `Settings.embed_dim`, `Settings.chunk_target_tokens` (Task 1).
- Produces: `embed_texts(texts: list[str]) -> list[list[float]]`, `embed_query(text: str) -> list[float]`, `probe_embedding_dimension() -> int`, `verify_embedding_dimension() -> None`, `model_max_sequence_length() -> int`, `verify_chunk_size_fits_model() -> None`, and the private accessor `_model()` which tests monkeypatch.

- [ ] **Step 1: Write the failing tests**

Replace `backend/tests/semantic_search/test_text_embedder.py` in full:

```python
"""Embedder unit tests: in-process call shape, the query/document prompt split,
unit-normalization, and the startup guards. The model is faked so these run
offline — the real model is 1.19 GB and must never be downloaded in CI."""
from __future__ import annotations

import math
import os

import pytest

from tara.semantic_search import text_embedder


class _FakeSentenceTransformer:
    """Records how it was called. Returns non-unit vectors on purpose."""

    max_seq_length = 512

    def __init__(self):
        self.calls: list[tuple[object, dict]] = []

    def encode(self, sentences, **kwargs):
        self.calls.append((sentences, kwargs))
        if isinstance(sentences, str):
            return [3.0, 4.0, 0.0]                       # norm 5 -> proves normalize
        return [[float(i + 1), 0.0, 0.0] for i, _ in enumerate(sentences)]


@pytest.fixture
def fake_model(monkeypatch):
    model = _FakeSentenceTransformer()
    # Patching the accessor also sidesteps its @lru_cache.
    monkeypatch.setattr(text_embedder, "_model", lambda: model)
    return model


@pytest.mark.unit
def test_embed_query_applies_the_query_prompt(fake_model):
    # THE critical assertion. Omitting prompt_name embeds a question as a document:
    # a valid unit vector in the wrong region, so retrieval favours passages that
    # RESEMBLE the question over passages that ANSWER it. Nothing raises.
    text_embedder.embed_query("what is my deductible?")
    _, kwargs = fake_model.calls[0]
    assert kwargs["prompt_name"] == "query"


@pytest.mark.unit
def test_embed_texts_applies_no_prompt(fake_model):
    # Documents use the model's empty "document" prompt, i.e. no prompt at all.
    text_embedder.embed_texts(["a", "b"])
    _, kwargs = fake_model.calls[0]
    assert "prompt_name" not in kwargs


@pytest.mark.unit
def test_embed_texts_preserves_order_and_normalizes(fake_model):
    out = text_embedder.embed_texts(["a", "b"])
    assert len(out) == 2
    for vector in out:
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-6)
    assert math.isclose(out[0][0], 1.0, rel_tol=1e-6)


@pytest.mark.unit
def test_embed_query_normalizes(fake_model):
    vector = text_embedder.embed_query("hello")
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-6)


@pytest.mark.unit
def test_embed_texts_empty_is_noop(fake_model):
    assert text_embedder.embed_texts([]) == []
    assert fake_model.calls == []


@pytest.mark.unit
def test_model_is_constructed_with_the_pinned_revision(monkeypatch):
    """Spec assertion 2. Every other test patches _model wholesale, so without
    this one nothing proves the revision pin is actually passed through."""
    captured: dict = {}

    class _RecordingSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            captured["model"] = model_name_or_path
            captured["kwargs"] = kwargs

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer",
                        _RecordingSentenceTransformer)
    text_embedder._model.cache_clear()
    text_embedder._model()
    text_embedder._model.cache_clear()

    assert captured["model"] == "Qwen/Qwen3-Embedding-0.6B"
    assert captured["kwargs"]["revision"] == "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("TARA_TEST_REAL_EMBED_MODEL"),
    reason="loads the real 1.19 GB model; opt in with TARA_TEST_REAL_EMBED_MODEL=1",
)
def test_real_model_loads_and_matches_configured_dimension():
    """Spec 9.5. The only test that touches the real weights. Never runs in CI.

    Print max_seq_length: Task 3's chunk sizing depends on it being comfortably
    above chunk_target_tokens, and this model ships no sentence_bert_config.json,
    so the effective value must be observed rather than assumed.
    """
    text_embedder._model.cache_clear()
    print(f"max_seq_length={text_embedder.model_max_sequence_length()}")
    assert len(text_embedder.embed_query("what is my deductible?")) == 1024
    text_embedder._model.cache_clear()


@pytest.mark.unit
def test_embed_texts_rejects_count_mismatch(monkeypatch):
    class _ShortModel:
        max_seq_length = 512

        def encode(self, sentences, **kwargs):
            return [[1.0, 0.0, 0.0]]        # fewer vectors than inputs

    monkeypatch.setattr(text_embedder, "_model", lambda: _ShortModel())
    with pytest.raises(RuntimeError, match="vectors"):
        text_embedder.embed_texts(["a", "b"])


@pytest.mark.unit
def test_verify_chunk_size_rejects_oversized_chunks(fake_model, monkeypatch):
    # sentence-transformers truncates SILENTLY past max_seq_length, so an
    # oversized chunk would lose text from its vector while the full text is
    # still stored and cited.
    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "5000")
    from tara import config
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="max_seq_length"):
        text_embedder.verify_chunk_size_fits_model()
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_verify_chunk_size_accepts_a_fitting_chunk(fake_model, monkeypatch):
    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "200")
    from tara import config
    config.get_settings.cache_clear()
    text_embedder.verify_chunk_size_fits_model()   # must not raise
    config.get_settings.cache_clear()


@pytest.mark.unit
def test_verify_embedding_dimension_rejects_a_mismatch(fake_model, monkeypatch):
    monkeypatch.setenv("TARA_EMBED_DIM", "1024")
    from tara import config
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="TARA_EMBED_DIM"):
        text_embedder.verify_embedding_dimension()   # fake returns dim 3
    config.get_settings.cache_clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/semantic_search/test_text_embedder.py -v
```
Expected: FAIL — `text_embedder` has no attribute `_model`.

- [ ] **Step 3: Rewrite the embedder**

Replace `backend/src/tara/semantic_search/text_embedder.py` in full:

```python
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


@lru_cache
def _model() -> "SentenceTransformer":
    """Load the pinned embedding model once, in-process.

    Imported lazily so that merely importing this module does not pull torch,
    and so tests can replace this accessor without loading 1.19 GB of weights.
    """
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    # Pinned by revision, not just name: an unpinned model silently changes the
    # vector space between installs, which would make every retrieval test
    # measure a moving target (the same lesson as the pinned en_core_web_lg wheel).
    return SentenceTransformer(
        settings.embed_model,
        revision=settings.embed_model_revision,
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
    return int(_model().max_seq_length)


def verify_chunk_size_fits_model() -> None:
    """Fail loudly if the configured chunk size exceeds the model's limit (M5 §5.5)."""
    settings = get_settings()
    sequence_limit = model_max_sequence_length()
    if settings.chunk_target_tokens > sequence_limit:
        raise RuntimeError(
            f"TARA_CHUNK_TARGET_TOKENS={settings.chunk_target_tokens} exceeds the "
            f"embedding model's max_seq_length of {sequence_limit}. Chunks would be "
            f"silently truncated before embedding while their full text is still "
            f"stored and cited. Lower the chunk size or choose another model."
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/semantic_search/ -v
```
Expected: PASS — 9 tests.

- [ ] **Step 5: Verify no network and no regression**

```bash
cd backend && python -m pytest tests/ -q --ignore=tests/llm_clients
```
Expected: PASS. Confirm the run is not noticeably slower — if it is, the real model is being loaded and a `_model` monkeypatch is missing.

- [ ] **Step 6: Commit**

```bash
git add backend/src/tara/semantic_search/text_embedder.py \
        backend/tests/semantic_search/test_text_embedder.py
git commit -m "feat: embed in-process with a pinned model, splitting query and document prompts"
```

---

### Task 3: Source chunk sizing from config

**Files:**
- Modify: `backend/src/tara/document_ingestion/text_chunking.py:70-76`
- Modify: `backend/src/tara/document_ingestion/ingestion_pipeline.py:71`
- Test: `backend/tests/document_ingestion/test_text_chunking.py`

**Interfaces:**
- Consumes: `Settings.chunk_target_tokens`, `Settings.chunk_overlap_tokens` (Task 1).
- Produces: `chunk_spans(doc_id, spans, target_tokens: int | None = None, overlap_tokens: int | None = None) -> list[Chunk]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/document_ingestion/test_text_chunking.py`:

```python
@pytest.mark.unit
def test_chunk_spans_defaults_come_from_config(monkeypatch):
    """Chunk sizing is coupled to the embedding model's limit, so it must be
    configuration — not a hard-coded function default no operator can reach."""
    from tara import config
    from tara.document_ingestion.text_chunking import chunk_spans
    from tara.document_ingestion.text_extraction import ExtractedSpan

    monkeypatch.setenv("TARA_CHUNK_TARGET_TOKENS", "10")
    monkeypatch.setenv("TARA_CHUNK_OVERLAP_TOKENS", "0")
    config.get_settings.cache_clear()

    page_text = "\n".join(f"line number {i} with several words" for i in range(40))
    spans = [ExtractedSpan(page=1, char_start=0, char_end=len(page_text), text=page_text)]
    chunks = chunk_spans("doc-1", spans)

    config.get_settings.cache_clear()
    # A 10-token budget over ~40 lines must produce many small chunks, not one big one.
    assert len(chunks) > 5
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/document_ingestion/test_text_chunking.py::test_chunk_spans_defaults_come_from_config -v
```
Expected: FAIL — one chunk is produced, because `target_tokens` still defaults to 800.

- [ ] **Step 3: Wire the defaults to config**

Replace `backend/src/tara/document_ingestion/text_chunking.py` lines 70-76 with:

```python
def chunk_spans(doc_id: str, spans: list[ExtractedSpan],
                target_tokens: int | None = None,
                overlap_tokens: int | None = None) -> list[Chunk]:
    """Pack spans into ~target_tokens chunks, page-bounded, preserving provenance.

    Sizing defaults to configuration rather than a literal, because it is coupled
    to the embedding model's sequence limit — sentence-transformers truncates
    silently past it (M5 §5.5). Explicit arguments still win, for tests.
    """
    from tara.config import get_settings

    settings = get_settings()
    resolved_target = settings.chunk_target_tokens if target_tokens is None else target_tokens
    resolved_overlap = settings.chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
    chunks: list[Chunk] = []
    for span in spans:
        chunks.extend(_chunk_single_span(doc_id, span, resolved_target, resolved_overlap))
    return chunks
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/document_ingestion/ -v
```
Expected: PASS — including the pre-existing chunking tests, which pass explicit arguments.

- [ ] **Step 5: Commit**

```bash
git add backend/src/tara/document_ingestion/text_chunking.py \
        backend/tests/document_ingestion/test_text_chunking.py
git commit -m "refactor: source chunk sizing from config, coupled to the embedding model limit"
```

---

### Task 4: Add the Agent Platform generation client

**Files:**
- Create: `backend/src/tara/llm_clients/agent_platform_client.py`
- Delete: `backend/src/tara/llm_clients/hosted_client.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/tara/app_errors.py`
- Create: `backend/tests/llm_clients/test_agent_platform_client.py`

**Interfaces:**
- Consumes: `Settings.generation_mode`, `Settings.gcp_project`, `Settings.gcp_location`, `Settings.agent_platform_provider`, `Settings.gemini_model`, `Settings.llama_model`, `Settings.mistral_model`, `Settings.llm_timeout_seconds` (Task 1).
- Produces: `AgentPlatformClient` with `generate(system_prompt: str, user_prompt: str) -> str`; `verify_generation_model() -> None`; `AgentPlatformConfigError`; `AgentPlatformUnavailableError`; the private accessor `_chat_model()` which tests monkeypatch.

- [ ] **Step 1: Add the dependencies and the error types**

In `backend/pyproject.toml`, add to `dependencies` after the `openai` line:

```python
    # Hosted generation on Google Cloud Agent Platform (formerly Vertex AI).
    # Two packages because ChatGoogleGenerativeAI (Gemini) and VertexModelGardenLlama
    # (Llama/Mistral MaaS) live in different ones; ChatVertexAI is deprecated since
    # 3.2.0 with removal at 4.0.0, so it is deliberately not used.
    "langchain-google-genai>=4.3",
    "langchain-google-vertexai>=3.2,<4",
```

In `backend/src/tara/app_errors.py`, append:

```python
class AgentPlatformConfigError(RuntimeError):
    """Agent Platform is misconfigured — missing or expired credentials, wrong
    project, insufficient permission, or an unknown/retired model. An operator must
    fix it; retrying will not help. Maps to HTTP 500.

    Carries no user content: web_app renders str(exc) straight to the client."""


class AgentPlatformUnavailableError(RuntimeError):
    """Agent Platform was over quota or unavailable after bounded retry. The same
    request may succeed later. Maps to HTTP 503.

    Carries no user content: web_app renders str(exc) straight to the client."""
```

```bash
cd backend && uv pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/llm_clients/test_agent_platform_client.py`:

```python
"""AgentPlatformClient: explicit Vertex routing, failure classification, bounded
retry, and the guarantee that no user content reaches an exception message."""
from __future__ import annotations

import pytest

from tara import config
from tara.app_errors import AgentPlatformConfigError, AgentPlatformUnavailableError
from tara.llm_clients import agent_platform_client


@pytest.fixture
def egress_env(monkeypatch):
    monkeypatch.setenv("TARA_GENERATION_MODE", "agent_platform")
    monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
    monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


class _FakeResponse:
    def __init__(self, text): self.content = text


class _FakeChatModel:
    """Raises the queued exceptions in order, then returns text."""

    def __init__(self, failures=()):
        self.failures = list(failures)
        self.attempts = 0

    def invoke(self, messages):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        return _FakeResponse("the answer")


def _api_error(code: int) -> Exception:
    error = RuntimeError(f"upstream said {code}")
    error.code = code          # what _classify_failure reads
    return error


@pytest.mark.unit
def test_generate_returns_model_text(egress_env, monkeypatch):
    model = _FakeChatModel()
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    assert agent_platform_client.AgentPlatformClient().generate("sys", "user") == "the answer"


@pytest.mark.unit
def test_quota_error_is_retried_then_succeeds(egress_env, monkeypatch):
    model = _FakeChatModel(failures=[_api_error(429)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)
    assert agent_platform_client.AgentPlatformClient().generate("sys", "user") == "the answer"
    assert model.attempts == 2


@pytest.mark.unit
def test_persistent_quota_error_raises_unavailable_with_bounded_attempts(egress_env, monkeypatch):
    model = _FakeChatModel(failures=[_api_error(429) for _ in range(10)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    monkeypatch.setattr(agent_platform_client, "_backoff_seconds", lambda attempt: 0.0)
    with pytest.raises(AgentPlatformUnavailableError):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    # A runaway retry must not hide behind a green test.
    assert model.attempts == agent_platform_client._MAX_ATTEMPTS


@pytest.mark.unit
@pytest.mark.parametrize("status", [403, 404])
def test_operator_errors_are_never_retried(egress_env, monkeypatch, status):
    model = _FakeChatModel(failures=[_api_error(status) for _ in range(5)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError):
        agent_platform_client.AgentPlatformClient().generate("sys", "user")
    assert model.attempts == 1


@pytest.mark.unit
def test_exception_message_never_carries_user_content(egress_env, monkeypatch):
    # web_app renders str(exc) to the client, so PHI must never reach it.
    secret = "MEMBER-ID-XQZ8842190-PRIYA-RAGHUNATHAN"
    model = _FakeChatModel(failures=[_api_error(403)])
    monkeypatch.setattr(agent_platform_client, "_chat_model", lambda: model)
    with pytest.raises(AgentPlatformConfigError) as caught:
        agent_platform_client.AgentPlatformClient().generate("sys", secret)
    assert secret not in str(caught.value)


@pytest.mark.unit
def test_verify_generation_model_rejects_unknown_maas_model(egress_env, monkeypatch):
    monkeypatch.setenv("TARA_AGENT_PLATFORM_PROVIDER", "llama")
    monkeypatch.setenv("TARA_LLAMA_MODEL", "meta/llama-9.9-imaginary-maas")
    config.get_settings.cache_clear()
    with pytest.raises(AgentPlatformConfigError, match="not a known"):
        agent_platform_client.verify_generation_model()


@pytest.mark.unit
def test_verify_generation_model_accepts_a_known_maas_model(egress_env, monkeypatch):
    monkeypatch.setenv("TARA_AGENT_PLATFORM_PROVIDER", "llama")
    monkeypatch.setenv("TARA_LLAMA_MODEL", "meta/llama-3.3-70b-instruct-maas")
    config.get_settings.cache_clear()
    agent_platform_client.verify_generation_model()   # must not raise


@pytest.mark.unit
def test_maas_allowlist_import_still_resolves():
    """Guards a PRIVATE import. If langchain-google-vertexai moves these symbols,
    this fails loudly rather than silently disabling the startup model check."""
    assert len(agent_platform_client._MAAS_MODEL_NAMES) > 0
    assert "meta/llama-3.3-70b-instruct-maas" in agent_platform_client._MAAS_MODEL_NAMES
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/llm_clients/test_agent_platform_client.py -v
```
Expected: FAIL — no module named `agent_platform_client`.

- [ ] **Step 4: Write the client**

Create `backend/src/tara/llm_clients/agent_platform_client.py`:

```python
"""Calls a hosted text-generation model on Google Cloud Agent Platform.

The ONLY code path where document text may leave the device (§7). Used in
generation_mode 'agent_platform', or 'hybrid' with an explicit per-query opt-in.
Sends the MINIMUM payload: the system prompt plus one assembled user prompt —
never the corpus, and never at ingestion time.

LangChain is confined to this module so it stays as replaceable as the provider it
wraps. `vertexai=True` is passed EXPLICITLY on every construction: LangChain's
backend auto-detection falls back to the consumer Gemini Developer API when no
project is set, and that product is not covered by a GCP BAA.
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from tara.app_errors import AgentPlatformConfigError, AgentPlatformUnavailableError
from tara.config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

# Bounded retry. Transient failures are worth one or two more tries; an operator
# error is not worth any, and an unbounded loop would hang a request.
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_OPERATOR_STATUS_CODES = frozenset({400, 401, 403, 404, 409})

# PRIVATE import: the MaaS allowlist is not part of langchain-google-vertexai's
# public API. test_maas_allowlist_import_still_resolves() guards it, so a package
# upgrade that moves these symbols fails CI instead of silently disabling the
# startup model check.
from langchain_google_vertexai.model_garden_maas._base import (  # noqa: E402
    _LLAMA_MODELS,
    _MISTRAL_MODELS,
)

_MAAS_MODEL_NAMES: frozenset[str] = frozenset(_LLAMA_MODELS) | frozenset(_MISTRAL_MODELS)


def _configured_model_name() -> str:
    """The model id for the selected provider."""
    settings = get_settings()
    return {
        "gemini": settings.gemini_model,
        "llama": settings.llama_model,
        "mistral": settings.mistral_model,
    }[settings.agent_platform_provider]


@lru_cache
def _chat_model() -> "BaseChatModel":
    """Build the provider's chat model once, always in Agent Platform mode."""
    settings = get_settings()
    if settings.agent_platform_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            # EXPLICIT, never inferred: with this unset and no project, LangChain
            # routes to generativelanguage.googleapis.com — the consumer API.
            vertexai=True,
            project=settings.gcp_project,
            location=settings.gcp_location,
            timeout=settings.llm_timeout_seconds,
        )

    from langchain_google_vertexai.model_garden_maas import get_vertex_maas_model

    return get_vertex_maas_model(
        _configured_model_name(),
        project=settings.gcp_project,
        location=settings.gcp_location,
    )


def _status_code_of(error: Exception) -> int | None:
    """Best-effort HTTP status from a Google or LangChain-wrapped error."""
    for attribute in ("code", "status_code", "grpc_status_code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


def _classify_failure(error: Exception) -> Exception:
    """Map an upstream failure onto our taxonomy, carrying NO user content.

    The message names the failure, the model, the project and the location —
    nothing derived from the prompt, because web_app renders str(exc) to the
    client. The original error is chained for local logs only.
    """
    settings = get_settings()
    context = (
        f"provider={settings.agent_platform_provider} model={_configured_model_name()} "
        f"project={settings.gcp_project} location={settings.gcp_location}"
    )
    status_code = _status_code_of(error)

    if type(error).__name__ == "DefaultCredentialsError":
        return AgentPlatformConfigError(
            f"No Application Default Credentials found ({context}). "
            f"Run 'gcloud auth application-default login', or attach a service account."
        )
    if status_code in _RETRYABLE_STATUS_CODES:
        return AgentPlatformUnavailableError(
            f"Agent Platform returned {status_code} after {_MAX_ATTEMPTS} attempts "
            f"({context}). This is transient; the same request may succeed later."
        )
    return AgentPlatformConfigError(
        f"Agent Platform rejected the request"
        f"{f' with {status_code}' if status_code else ''} ({context}). "
        f"Check credentials, IAM permissions, the model id, and the region."
    )


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 0.5s, 1.0s. Patched to 0 in tests."""
    return 0.5 * (2 ** (attempt - 1))


def verify_generation_model() -> None:
    """Reject an unknown or retired model at startup, with no network call (M5 §7.3).

    Only MaaS providers are checkable offline: their names come from a frozen
    allowlist in the package. Gemini ids are not enumerable locally, so a bad one
    surfaces on first use instead.
    """
    settings = get_settings()
    if settings.agent_platform_provider == "gemini":
        return
    model_name = _configured_model_name()
    if model_name not in _MAAS_MODEL_NAMES:
        raise AgentPlatformConfigError(
            f"'{model_name}' is not a known Agent Platform MaaS model. "
            f"Known models: {', '.join(sorted(_MAAS_MODEL_NAMES))}."
        )


class AgentPlatformClient:
    """LLMClient backed by Google Cloud Agent Platform (Gemini or MaaS)."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        messages = [("system", system_prompt), ("human", user_prompt)]
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return _chat_model().invoke(messages).content
            except Exception as error:  # noqa: BLE001 - re-raised as our taxonomy
                last_error = error
                if _status_code_of(error) not in _RETRYABLE_STATUS_CODES:
                    raise _classify_failure(error) from error
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_backoff_seconds(attempt))
        raise _classify_failure(last_error) from last_error
```

- [ ] **Step 5: Delete the superseded stub**

```bash
git rm backend/src/tara/llm_clients/hosted_client.py
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/llm_clients/ -v
```
Expected: PASS — 8 client tests plus the 5 routing tests from Task 1, which now resolve.

- [ ] **Step 7: Verify the whole suite and types**

```bash
cd backend && python -m pytest tests/ -q && python -m mypy src && python -m ruff check src tests
```
Expected: all pass, with no `--ignore` needed.

- [ ] **Step 8: Commit**

```bash
git add backend/src/tara/llm_clients/agent_platform_client.py backend/src/tara/app_errors.py \
        backend/pyproject.toml backend/tests/llm_clients/test_agent_platform_client.py
git commit -m "feat: add Agent Platform generation over LangChain, replacing the hosted stub"
```

---

### Task 5: Map failures to HTTP and validate at startup

**Files:**
- Modify: `backend/src/tara/web_app.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_web_app.py`

**Interfaces:**
- Consumes: `AgentPlatformConfigError`, `AgentPlatformUnavailableError`, `verify_generation_model()` (Task 4); `verify_embedding_dimension()`, `verify_chunk_size_fits_model()` (Task 2).
- Produces: HTTP 500 / 503 handlers; a startup sequence that fails on misconfiguration.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_web_app.py`:

```python
@pytest.mark.unit
def test_agent_platform_config_error_maps_to_500(client, monkeypatch):
    from tara import web_app
    from tara.app_errors import AgentPlatformConfigError

    def raise_config_error(question: str, prefer_agent_platform: bool = False):
        raise AgentPlatformConfigError("provider=gemini project=test-project")

    monkeypatch.setattr(web_app, "answer_question", raise_config_error)
    response = client.post("/ask", json={"question": "what is my deductible?"})
    assert response.status_code == 500
    assert "test-project" in response.json()["detail"]


@pytest.mark.unit
def test_agent_platform_unavailable_maps_to_503(client, monkeypatch):
    from tara import web_app
    from tara.app_errors import AgentPlatformUnavailableError

    def raise_unavailable(question: str, prefer_agent_platform: bool = False):
        raise AgentPlatformUnavailableError("transient")

    monkeypatch.setattr(web_app, "answer_question", raise_unavailable)
    response = client.post("/ask", json={"question": "what is my deductible?"})
    assert response.status_code == 503


@pytest.mark.unit
def test_emergency_answers_while_agent_platform_is_down(client, monkeypatch):
    """The emergency pre-check imports nothing and runs BEFORE retrieval, so a
    Google outage must never stop a triage response (M5 §4.3)."""
    from tara.data_models import Citation  # noqa: F401 - documents the Answer shape
    from tara.question_answering.question_answerer import Answer
    from tara import web_app
    from tara.llm_clients import agent_platform_client

    def always_fails():
        raise AssertionError("Agent Platform must not be reached for an emergency")

    monkeypatch.setattr(agent_platform_client, "_chat_model", always_fails)

    def emergency(question: str, prefer_agent_platform: bool = False) -> Answer:
        return Answer(text="Call 911.", citations=[], safety_flag="emergency")

    monkeypatch.setattr(web_app, "answer_question", emergency)
    response = client.post("/ask", json={"question": "crushing chest pain"})
    assert response.status_code == 200
    assert response.json()["safety_flag"] == "emergency"


@pytest.mark.integration
def test_local_mode_resolves_no_hostname(offline_ingest_env, monkeypatch, make_pdf):
    """Spec assertion 12. In local mode a full ingest-and-ask cycle must resolve
    no hostname — any outbound call needs DNS first.

    What this proves: the PIPELINE holds no hidden HTTP client. What it does NOT
    prove: that the real embedding model is local, because offline_ingest_env
    fakes the embedder. Task 6 Step 5 covers that in the container.

    Guards getaddrinfo rather than socket.socket, so pytest's own machinery and
    SQLite (file-based, socket-free) are unaffected.
    """
    import socket

    from tara.document_ingestion.ingestion_pipeline import ingest_document
    from tara.question_answering.question_answerer import answer_question

    def _refuse(*args, **kwargs):
        raise AssertionError(f"local mode attempted to resolve {args[:1]}")

    monkeypatch.setattr(socket, "getaddrinfo", _refuse)

    pdf_bytes = make_pdf([["Annual Deductible: $2,500 individual / $5,000 family"]])
    ingest_document("benefits.pdf", pdf_bytes)

    # The answering model is stubbed: this asserts the RETRIEVAL half is offline.
    # Generation in local mode reaches LM Studio over the network by design.
    from tara.llm_clients import llm_client_interface

    class _OfflineClient:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            return "Your deductible is $2,500. [chunk-1]"

    monkeypatch.setattr(llm_client_interface, "get_llm_client",
                        lambda prefer_agent_platform=False: _OfflineClient())
    answer_question("what is my deductible?")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_web_app.py -v -k "agent_platform or emergency"
```
Expected: FAIL — the errors surface as unhandled 500s with the wrong body, and the import of `AgentPlatformConfigError` into `web_app` does not exist yet.

- [ ] **Step 3: Add the handlers and startup validation**

In `backend/src/tara/web_app.py`, extend the error import:

```python
from tara.app_errors import (
    AgentPlatformConfigError,
    AgentPlatformUnavailableError,
    IndexMismatchError,
    IngestionError,
    UploadError,
)
```

Add after `_handle_index_mismatch`:

```python
@app.exception_handler(AgentPlatformConfigError)
def _handle_agent_platform_config_error(request: Request, exc: AgentPlatformConfigError) -> JSONResponse:
    # 500: the operator must fix credentials, permissions, the model id, or the
    # region. Retrying will not help. The message carries no user content.
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(AgentPlatformUnavailableError)
def _handle_agent_platform_unavailable(request: Request, exc: AgentPlatformUnavailableError) -> JSONResponse:
    # 503: transient — quota or availability. The same request may succeed later.
    return JSONResponse(status_code=503, content={"detail": str(exc)})
```

In `main()`, insert after `reconcile_orphan_blobs()`:

```python
    # Startup validation (M5 §7.3). All three are deterministic and offline, so
    # all three fail hard: a typo'd model or an oversized chunk should never be
    # discovered by a user mid-question.
    from tara.llm_clients.agent_platform_client import verify_generation_model
    from tara.semantic_search.text_embedder import (
        verify_chunk_size_fits_model,
        verify_embedding_dimension,
    )

    if get_settings().generation_mode in ("agent_platform", "hybrid"):
        verify_generation_model()
    verify_chunk_size_fits_model()
    verify_embedding_dimension()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_web_app.py -v
```
Expected: PASS.

- [ ] **Step 5: Add the autouse credential guard**

Append to `backend/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def never_resolve_real_credentials(monkeypatch):
    """Fail loudly if any test reaches for real Google credentials.

    A missed monkeypatch would otherwise attempt a live ADC lookup — slow in CI,
    and on a developer's machine it would silently succeed and hit the network.
    """
    def _refuse(*args, **kwargs):
        raise AssertionError(
            "A test attempted to resolve Application Default Credentials. "
            "Patch the client accessor instead (agent_platform_client._chat_model)."
        )

    try:
        import google.auth
    except ImportError:
        return
    monkeypatch.setattr(google.auth, "default", _refuse)
```

- [ ] **Step 6: Verify the whole suite**

```bash
cd backend && python -m pytest tests/ -q && python -m mypy src && python -m ruff check src tests
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/tara/web_app.py backend/tests/test_web_app.py backend/tests/conftest.py
git commit -m "feat: map Agent Platform failures to 500/503 and validate config at startup"
```

---

### Task 6: Package the model and update the documentation

**Files:**
- Modify: `deployment/docker/Dockerfile.backend`
- Modify: `deployment/docker/compose.yaml`
- Modify: `deployment/local/bootstrap.sh`
- Modify: `.dockerignore`
- Modify: `docs/epic0_foundation/README.md`
- Modify: `docs/epic0_foundation/M4_epic1_handoff.md`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: a self-contained image; a bootstrap that pre-fetches weights.

- [ ] **Step 1: Bake the pinned model into the image**

In `deployment/docker/Dockerfile.backend`, add after the `uv pip install` line:

```dockerfile
# Bake the pinned embedding model into the image so the container never reaches
# Hugging Face at runtime and works with networking disabled. Pinned by revision
# for the same reason the spaCy model is a pinned wheel: an unpinned model would
# silently change the vector space between builds.
ENV HF_HOME=/opt/hf \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf \
    HF_HUB_OFFLINE=0
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('Qwen/Qwen3-Embedding-0.6B', \
                    revision='97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3')"
```

Add near the other `ENV` pins:

```dockerfile
# Offline at runtime: the weights are already in the image, so a hub lookup would
# only be a silent network dependency.
ENV HF_HUB_OFFLINE=1
```

- [ ] **Step 2: Mount ADC read-only for generation**

In `deployment/docker/compose.yaml`, add to `environment`:

```yaml
      # Agent Platform generation only. Unused in TARA_GENERATION_MODE=local.
      GOOGLE_APPLICATION_CREDENTIALS: /gcp/adc.json
```

and to `volumes`:

```yaml
      # Read-only, and never COPYd into an image layer: a credential baked into a
      # layer is permanent and shippable.
      - ~/.config/gcloud/application_default_credentials.json:/gcp/adc.json:ro
```

- [ ] **Step 3: Pre-fetch weights during bootstrap**

In `deployment/local/bootstrap.sh`, add before the closing instructions:

```bash
echo "Pre-fetching the pinned embedding model (~1.2 GB, one time)..."
python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('Qwen/Qwen3-Embedding-0.6B', \
                    revision='97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3')"
```

Replace the LM Studio instruction line with:

```bash
echo "  1. Embeddings run in-process — no model server needed for ingestion or search."
echo "  2. For local ANSWERING, start LM Studio and load the model named in TARA_LOCAL_MODEL."
echo "  3. For Agent Platform answering, set TARA_GCP_PROJECT and run:"
echo "       gcloud auth application-default login"
echo "       gcloud auth application-default set-quota-project <PROJECT_ID>"
```

- [ ] **Step 4: Confirm gcloud config cannot reach the image**

```bash
grep -nE "gcloud|\.config" .dockerignore || echo "MISSING — add the entries below"
```

If missing, append to `.dockerignore`:

```
**/.config/gcloud/
**/application_default_credentials.json
```

- [ ] **Step 5: Verify the offline guarantee end to end**

```bash
make up   # build once, with network
# Then prove the built image embeds with networking fully disabled.
docker compose -f deployment/docker/compose.yaml run --rm --network none tara-backend \
  python -c "\
from tara.semantic_search.text_embedder import embed_query, model_max_sequence_length; \
print('max_seq_length', model_max_sequence_length()); \
print('dim', len(embed_query('what is my deductible?')))"
```
Expected: prints the sequence limit and `dim 1024`, with **no network**. If it fails, the weights are not baked into the image. Record `max_seq_length` — Task 3's chunk sizing depends on it exceeding `chunk_target_tokens`.

- [ ] **Step 6: Update the docs**

- `docs/epic0_foundation/README.md` §7: remove the `hosted_model` / `hosted_api_key` rows; add `generation_mode`, `gcp_project`, `gcp_location`, `agent_platform_provider`, `phi_egress_acknowledged`, `embed_model_revision`, `chunk_target_tokens`, `chunk_overlap_tokens`.
- `docs/epic0_foundation/M4_epic1_handoff.md` §3.1: the Epic 1 M4 delta no longer describes a `hosted_client.py` stub to fill in. Replace with a pointer to `AgentPlatformClient`, and note that the egress payload is unchanged — system prompt plus one assembled user prompt.
- Mark M5 **DONE** in the README build-order table with the measured result.

- [ ] **Step 7: Final verification**

```bash
cd backend && python -m pytest tests/ -q && python -m mypy src && python -m ruff check src tests
grep -rn "hosted_api_key\|model_mode\|prefer_hosted\|HostedLLMClient" backend deployment .env.example
```
Expected: suite green; the grep returns nothing.

- [ ] **Step 8: Commit**

```bash
git add deployment/ .dockerignore docs/epic0_foundation/README.md \
        docs/epic0_foundation/M4_epic1_handoff.md
git commit -m "build: bake the pinned embedding model into the image and update Epic 0 docs"
```

---

## Acceptance (from the spec §10)

- [ ] `make lint`, `make typecheck`, `make test` all pass.
- [ ] All 12 spec assertions are present — Task 2 covers 1-4, Task 4 covers 5-8 and 10, Task 5 covers 9 and 12, Task 3 covers 11. Task 6 Step 5 confirms 12 again in the container, where the model is real rather than faked.
- [ ] CI wall time does not regress — no model download in the test path.
- [ ] `Settings()` fails closed on an empty project or unacknowledged egress **when, and only when, generation egresses**.
- [ ] Startup fails on an unknown MaaS model, and on `chunk_target_tokens` above the model's limit.
- [ ] `grep -r "hosted_api_key\|model_mode\|prefer_hosted" backend/ docs/` returns nothing outside historical notes.
- [ ] With the image already built, a full upload-and-ask cycle succeeds with the container's networking disabled in `generation_mode: "local"`.
- [ ] README §7 and the M4 handoff updated for the removed `hosted_*` settings.

## Known Risks Carried Into Execution

1. **`SentenceTransformer.encode()` signature.** Task 2 assumes `prompt_name=` and `revision=`. Confirm against the installed `sentence-transformers>=3.0` at Step 3; the prompt *names* are verified from the model's `config_sentence_transformers.json`.
2. **`max_seq_length` for this model.** Qwen3-Embedding ships no `sentence_bert_config.json`, so the effective value comes from the model/tokenizer config. Task 2's guard reads whatever is loaded rather than assuming 32768 — but print it during Step 4 and record it, because Task 3's chunk sizing depends on it being comfortably above 800.
3. **The private MaaS allowlist import.** Task 4 imports `_LLAMA_MODELS` / `_MISTRAL_MODELS` from a private module. `test_maas_allowlist_import_still_resolves` makes a package upgrade fail loudly. The pin `<4` is deliberate.
4. **Status-code extraction.** `_status_code_of` reads `code` / `status_code` / `grpc_status_code`. If LangChain wraps Google errors differently, retry classification degrades to "treat as operator error" — fail-closed, and visible as a 500 rather than a hang.
5. **BAA coverage for Llama/Mistral MaaS** is unconfirmed (spec §13 item 1). Do not put real PHI through those providers until verified.
