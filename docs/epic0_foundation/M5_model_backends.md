# Epic 0 · M5 — model_backends

- **Parent:** [Epic 0 — Foundation](README.md) — overview · decisions · build order · global constraints.
- **Seams:** depends on [M1](M1_repo_restructure.md). Replaces the `hosted_client.py` stub that [M4 §3.1](M4_epic1_handoff.md) assumed. Consumes nothing from [M2](M2_phi_redaction.md); [M3 execution_tracing](M3_execution_tracing.md) is unaffected.
- **Status:** design approved 2026-08-25. Task plan lands beside this file as `M5_model_backends_plan.md`.
- **Supersedes:** an earlier draft named `M5_agent_platform_models.md`, which routed embeddings through Agent Platform. Reversed on 2026-08-25 — see §1.1.

---

> **For agentic workers:** this file is the **contract**, not the task list. Implementations follow the plan file. Where the two disagree, this file wins.

**Goal:** Give the app two real model backends — hosted generation on Google Cloud Agent Platform, and embeddings running in-process — so it no longer depends on LM Studio and no longer sends documents anywhere to be indexed.

**Architecture:** One new plane module, `llm_clients/agent_platform_client.py`, implementing the existing `LLMClient` protocol over LangChain; plus a rewrite of `semantic_search/text_embedder.py` onto `sentence-transformers`. LangChain is confined to one file and touches only generation.

**Design sections:** this document. Supersedes [README](README.md) §7 rows covering `hosted_model` / `hosted_api_key`.

**Tech Stack:** `langchain-google-genai` (Gemini) · `langchain-google-vertexai` (Llama / Mistral MaaS) · `sentence-transformers` (already a dependency) · Application Default Credentials

## Why this is its own module

- It removes the **last hard dependency on a local model server**, which is what blocks deploying anywhere.
- It is the first module where **generation and retrieval have genuinely different trust boundaries** — one may egress, the other never does. That distinction is the design.
- It has **no dependency on M3**, and M3 has none on it.

## 1. Decisions

| # | Decision | Consequence if reversed later |
|---|---|---|
| 1 | **Generation** runs on Agent Platform (opt-in); **embeddings** run in-process | Reversing embeddings is a full re-index |
| 2 | **Embeddings never egress, in any mode** — the original invariant, restored | Re-opening this re-opens ingestion-time PHI egress |
| 3 | A BAA gates **generation only**, because that is now the only egress path | Validators become unconditional again |
| 4 | `Qwen/Qwen3-Embedding-0.6B`, **1024 dims**, pinned by revision | `embed_dim` unchanged; vec0 schema unchanged |
| 5 | Queries and documents are embedded with **different prompts** | Silent retrieval degradation — see §6.3 |
| 6 | **Gemini + Llama** selectable by config (Mistral via the same factory) | Claude would re-add deprecating classes |
| 7 | LangChain sits **behind** the existing `LLMClient` protocol, never in front | LangChain stays replaceable in one file |
| 8 | `chunk_target_tokens` becomes configuration and is **validated against the embedding model's sequence limit** | A model swap can silently truncate every chunk |

### 1.1 Why the earlier draft was reversed

- The superseded draft made Agent Platform the single embedding backend. Three problems surfaced on review:
  - It **hard-wired one provider** into the only component the app could not swap by config — contradicting the project's own rule that provider choice is configuration, never code.
  - It made **every upload egress**, inverting the product premise, and it broke offline operation entirely.
  - It bought nothing that in-process embedding does not also buy. Removing the LM Studio dependency was the actual goal, and running the model in-process achieves it without egress.
- In-process embedding satisfies every original goal simultaneously: no LM Studio, works offline, deploys to GCP unchanged, one portable vector space, and zero ingestion egress.

## 2. Global constraints

- Python 3.11+, `from __future__ import annotations` at the top of every module.
- Import direction unchanged: kernel ← planes ← capabilities ← safety ← `web_app`.
- No SQL outside `local_data_stores/`. This module adds none.
- Fail closed: no bare `except`. A failure raises rather than silently degrading.
- No PHI in exception messages, log records, or span attributes.

## 3. File structure

| File | Action | Responsibility |
|---|---|---|
| `backend/src/tara/llm_clients/agent_platform_client.py` | **new** | `AgentPlatformClient.generate()`; provider selection; `verify_generation_model()` |
| `backend/src/tara/llm_clients/llm_client_interface.py` | modify | routing only |
| `backend/src/tara/llm_clients/hosted_client.py` | **delete** | superseded; `"hosted"` names no specific thing |
| `backend/src/tara/llm_clients/ollama_client.py` | unchanged | — |
| `backend/src/tara/semantic_search/text_embedder.py` | **rewrite** | in-process embeddings, query/document prompts |
| `backend/src/tara/document_ingestion/text_chunking.py` | modify | `target_tokens` sourced from config |
| `backend/src/tara/config.py` | modify | new settings, conditional fail-closed validators |
| `backend/src/tara/app_errors.py` | modify | two new error types |
| `backend/src/tara/web_app.py` | modify | two new handlers; startup validation |
| `backend/pyproject.toml` | modify | two new dependencies |
| `deployment/docker/Dockerfile.backend` | modify | pre-download pinned model weights |
| `deployment/docker/compose.yaml` | modify | read-only ADC mount (generation only) |
| `deployment/local/bootstrap.sh` | modify | pre-download weights; ADC guidance |

- **One new production module.** No shared credential factory: LangChain takes `project` / `location` / `vertexai` directly, and the safety a factory would carry lives in config validation instead.

## 4. Architecture

### 4.1 Data flow

```
INGESTION  (fully on-device, every mode)
  upload -> extract -> chunk
        -> text_embedder.embed_texts(texts)          [in-process, document prompt]
        -> 1024-d unit vectors -> vec0

QUERY
  question -> screen_for_emergency()                 [local, no network]
          -> text_embedder.embed_query(q)            [in-process, QUERY prompt - 6.3]
          -> vec0 nearest -> chunks -> question_answerer
          -> get_llm_client() -+- local:          OllamaClient / LM Studio
                               +- agent_platform: AgentPlatformClient   <- ONLY egress
```

### 4.2 The split that defines this module

- **Retrieval is always local. Generation is the only thing that may leave the device.**
- The payload that egresses is the assembled excerpts plus the question — never the corpus, never at ingestion time.
- This is what the original design intended; this module is the first to actually implement it.

### 4.3 Properties preserved

- **Works fully offline** in `generation_mode: "local"` — ingestion, retrieval, and answering.
- **`screen_for_emergency()` imports only `dataclasses`** — no network, no LLM, and it runs before retrieval, so emergencies triage correctly regardless of connectivity.
- **One vector space, everywhere.** The same weights run on a laptop, in the container, and on any host, so an index is portable and `IndexMismatchError` never fires on a deployment change.

## 5. Configuration surface

### 5.1 Renames

| Now | Becomes | Reason |
|---|---|---|
| `model_mode` | `generation_mode` | it governs generation only |
| `"hosted"` | `"agent_platform"` | `"hosted"` no longer identifies which host |
| `prefer_hosted` | `prefer_agent_platform` | same, in `AskRequest` and `get_llm_client()` |

### 5.2 Removed

- `hosted_model`, `hosted_api_key`.
- `_require_hosted_key_when_egressing` — ADC has no API key, so the credential it required does not exist.

### 5.3 Added and changed

```python
GenerationMode = Literal["local", "agent_platform", "hybrid"]
AgentPlatformProvider = Literal["gemini", "llama", "mistral"]

# ---- Google Cloud Agent Platform (formerly Vertex AI) — GENERATION ONLY ----
# Required only when generation may egress. An empty project is the exact
# condition under which LangChain's backend auto-detection silently falls back
# to the consumer Gemini Developer API (generativelanguage.googleapis.com),
# which is NOT BAA-covered. Fail closed rather than egress to the wrong product.
gcp_project: str = ""
gcp_location: str = "us-central1"   # MaaS models are region-limited

generation_mode: GenerationMode = "local"
agent_platform_provider: AgentPlatformProvider = "gemini"
# Model IDs are perishable: gemini-2.5-flash retires 2026-10-20, and the Llama
# allowlist is frozen per langchain-google-vertexai release. Validated at startup.
gemini_model: str = "gemini-3.5-flash"
llama_model: str = "meta/llama-3.3-70b-instruct-maas"
mistral_model: str = "mistral-medium-3"

# ---- Embeddings (in-process; never egress, in any mode) ----
# Pinned by revision, not just name, for the same reason en_core_web_lg is a
# pinned wheel: an unpinned model makes every retrieval test measure a moving
# target. 1024 dims keeps embed_dim and the vec0 schema unchanged.
embed_model: str = "Qwen/Qwen3-Embedding-0.6B"
embed_model_revision: str = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
embed_dim: int = 1024

# ---- Chunking (coupled to the embedding model — see 5.5) ----
chunk_target_tokens: int = 800
chunk_overlap_tokens: int = 100
```

- `embed_max_concurrency` is **not** added: `sentence-transformers` batches natively, so there is no fan-out to bound.

### 5.4 Validators — conditional, and fail closed

- `_require_gcp_project_when_generation_egresses` — when `generation_mode` is `"agent_platform"` or `"hybrid"`, `gcp_project` must be non-empty. This is the guard against the silent consumer-API fallback.
- `_require_phi_egress_acknowledgement` — under the same condition, `phi_egress_acknowledged` must be explicitly true.
- Both are conditional because **egress is now conditional again.** In `"local"` mode nothing leaves the device, so demanding a GCP project would be theatre.
- `_embed_dim_is_positive` is unchanged.

### 5.5 The chunking coupling

- `target_tokens=800` is currently a **hardcoded function default** in `text_chunking.py`, which violates the rule that code never hard-codes what settings own.
- It becomes `chunk_target_tokens`, and startup validates it against the loaded model's `max_seq_length`.
- **Why this guard exists:** `sentence-transformers` truncates silently past the sequence limit. Under `all-MiniLM-L6-v2` (256 tokens) an 800-token chunk would lose roughly two-thirds of its text from the vector while the full text still got stored and cited — retrieval missing content that the citation claims is there.
- Qwen3-Embedding-0.6B allows 32768 positions, so 800 fits with enormous headroom. The guard is for the next model, not this one.
- `_CHARS_PER_TOKEN = 4` is an estimate, so the validation leaves margin rather than sitting on the limit.

### 5.6 Deployment

- **Dockerfile:** pre-download the pinned model in a build layer so the image is self-contained and the container never reaches Hugging Face at runtime. Set `HF_HOME` / `SENTENCE_TRANSFORMERS_HOME` to a fixed path.
- **bootstrap.sh:** pre-download the same pinned revision into the local venv's cache; prompt for a GCP project only if the user opts into Agent Platform generation.
- **compose.yaml:** mount `~/.config/gcloud/application_default_credentials.json` **read-only**; needed only for Agent Platform generation. Never `COPY` a credential into an image layer.
- **Image cost:** ~1.19 GB of weights on top of the 427 MB spaCy model and torch already shipped. Irrelevant on a VM; a real cold-start cost on Cloud Run, recorded in §11.4.
- Project and location are passed **explicitly** to LangChain rather than read from `GOOGLE_CLOUD_PROJECT`, so there is one source of truth.

## 6. The embedder rewrite

### 6.1 Preserved

| Element | Why it survives |
|---|---|
| `embed_texts(list) -> list`, `embed_query(str) -> list` | `ingestion_pipeline.py` and `chunk_retriever.py` need no change |
| `_normalize_to_unit_length` | the L2→cosine identity in `chunk_retriever` requires unit vectors; keeping our own normalize makes that a single guaranteed point |
| count-mismatch guard | a partial result would silently leave chunks un-vectorized |
| `probe_embedding_dimension` / `verify_embedding_dimension` | contract unchanged; now probes the loaded model |
| The module's **original invariant** | *"embeddings run on-device and never egress, in every model mode"* — restored, not rewritten |

### 6.2 Changed

```python
@lru_cache
def _model() -> SentenceTransformer:
    settings = get_settings()
    return SentenceTransformer(
        settings.embed_model,
        revision=settings.embed_model_revision,   # pinned; tests must not chase a moving model
    )
```

- No HTTP client, no API key, no timeout, no retry, no fan-out, no concurrency ceiling. All of it disappears with the network.

### 6.3 The query/document prompt asymmetry

- Qwen3-Embedding ships asymmetric prompts and applies **neither** by default:

```json
"prompts": { "query": "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:",
             "document": "" },
"default_prompt_name": null
```

- `embed_texts()` — documents — is correct with no prompt, because the document prompt is empty.
- `embed_query()` — questions — **must** pass `prompt_name="query"`.
- **The failure is invisible.** Omit it and the question is embedded as though it were a document: a valid, correctly-shaped, unit-length vector sitting in the wrong region of the space. Nearest-neighbour search then favours passages that *resemble* the question over passages that *answer* it. Nothing raises; scores stay plausible.
- It bites this app specifically because `abstain_threshold: 0.25` turns a mispositioned query into one of two outcomes: abstaining when it should answer, or confidently answering from the wrong chunk — **with a citation**, which makes a wrong answer look better grounded.
- Every strong retrieval model has this asymmetry (E5 uses `"query: "` / `"passage: "`, BGE an instruction prefix, `gemini-embedding-001` a `task_type`). It is the mechanism that makes them good. Choosing a model without it means choosing a weaker model.

### 6.4 The docstring

- The current module docstring is **correct and stays** — this module makes it true rather than aspirational.
- It gains one addition: the query/document asymmetry and why omitting the prompt is silently wrong.

## 7. Error handling

### 7.1 Two new error types — generation path only

```python
class AgentPlatformConfigError(RuntimeError):
    """Agent Platform is misconfigured — missing or expired ADC, wrong project,
    insufficient permission, or an unknown/retired model. An operator must fix
    it; retrying will not help. Maps to HTTP 500."""

class AgentPlatformUnavailableError(RuntimeError):
    """Agent Platform was over quota or unavailable after bounded retry. The same
    request may succeed later. Maps to HTTP 503."""
```

| Failure | Classified as | Retried |
|---|---|---|
| `DefaultCredentialsError`, 403, 404, unknown model, region mismatch | `AgentPlatformConfigError` → 500 | **no** |
| 429, 503, connection error | `AgentPlatformUnavailableError` → 503 | **yes**, bounded |
| empty `gcp_project` while egressing | prevented at config load | n/a |

- **The embedding path needs none of this.** Its only failure modes are a missing model cache or insufficient memory, both of which surface at load time as ordinary exceptions.

### 7.2 The PHI rule for error messages

- `web_app.py` renders `content={"detail": str(exc)}` — the exception string reaches the client verbatim.
- Therefore: **never interpolate chunk text, question text, or filenames into these exceptions.** They carry the failure class, model ID, project, and location — nothing derived from user content.
- `raise ... from e` preserves the underlying error for local logs; the chained cause must never reach `str()` on our type.
- Enforced by test (§9.3, assertion 8), not by convention.

### 7.3 Startup validation

| Check | Needs network | On failure |
|---|---|---|
| `verify_generation_model()` | no — literal/allowlist check | **fail** |
| `chunk_target_tokens` ≤ model `max_seq_length` | no — model already loaded | **fail** |
| `verify_embedding_dimension()` | no — local model | **fail** |

- `verify_embedding_dimension()` is currently **dead code — nothing calls it.** This module wires it in.
- All three are now deterministic and offline, so all three fail hard. The earlier draft's warn-versus-fail split existed only because a network probe could fail transiently; that concern is gone.

## 8. Adjacent fixes taken deliberately

1. **`llm_client_interface.py` routing bug.** It carries `TODO (Slice 2): route "local" by config.local_llm_backend`; today `"local"` always returns `OllamaClient`, ignoring `local_llm_backend: "openai_compatible"` — which is the **default**. Local mode uses the wrong backend today. This module rewrites that function anyway.
2. **`text_chunking.py` hardcoded defaults.** Required by §5.5, not optional.

- Both recorded as **added scope**, not slipped in.

## 9. Testing

### 9.1 Prerequisite — existing fixtures break

- `conftest.isolated_env` sets `TARA_MODEL_MODE`; `test_llm_client_interface.py` sets `TARA_HOSTED_API_KEY`. Both settings disappear.
- Fixture updates are a prerequisite task, not cleanup.

### 9.2 Hermetic and fast

- The real model is **1.19 GB**. CI must never download it.
- Keep the existing pattern: `monkeypatch.setattr` on `text_embedder._model`, which also sidesteps its `@lru_cache`. `conftest.fake_embed_one` already produces deterministic unit vectors.
- Add an autouse fixture stubbing `google.auth.default`, so a missed monkeypatch fails loudly instead of attempting a real credential lookup.

### 9.3 Assertions that carry weight

| # | Pinned behavior | Why |
|---|---|---|
| 1 | `embed_query` passes `prompt_name="query"`; `embed_texts` does not | §6.3 — the invisible failure |
| 2 | `SentenceTransformer` is constructed with the pinned `revision` | tests must not chase a moving model |
| 3 | Vectors are unit length | the L2→cosine identity depends on it |
| 4 | Count mismatch raises | preserved from the current suite |
| 5 | `vertexai=True` on every LangChain construction; empty `gcp_project` raises before any client exists **when generation egresses** | stops PHI reaching the consumer API |
| 6 | 429 → retried then succeeds; 429 forever → `AgentPlatformUnavailableError`, **attempt count asserted** | a runaway retry cannot hide behind a green test |
| 7 | 403 / 404 → `AgentPlatformConfigError` with **exactly one call** | never retry an operator error |
| 8 | A distinctive synthetic identifier **never appears in `str(exc)`** | §7.2, given teeth |
| 9 | Emergency question returns `safety_flag: "emergency"` and HTTP 200 while every Agent Platform call raises | §4.3 |
| 10 | `verify_generation_model()` rejects an unknown model with no network | catches retired IDs at boot |
| 11 | `chunk_target_tokens` above the model's limit fails at startup | §5.5 |
| 12 | `generation_mode: "local"` performs **no** network call across a full ingest-and-ask cycle | the offline guarantee, asserted rather than claimed |

### 9.4 One existing docstring, now true

- `test_llm_client_interface.py` opens with *"Local mode must NEVER return the hosted client (no silent PHI egress)."*
- Under the superseded draft that parenthetical would have become false. Under this design it is **exactly right**, and assertion 12 upgrades it from a comment into a test.

### 9.5 Out of scope for CI

- **Loading the real 1.19 GB model** — one opt-in integration test beside `make eval`, matching the DeepEval precedent.
- **Whether the query prompt measurably improves retrieval** — asserted as *applied*, not as *effective*. Measuring that is Epic 1 M8's job.

## 10. Acceptance

- [ ] `make lint`, `make typecheck`, `make test` all pass.
- [ ] All 12 assertions in §9.3 present and passing.
- [ ] CI wall time does not regress — no model download in the test path.
- [ ] `Settings()` fails closed on an empty project or unacknowledged egress **when, and only when, generation egresses**.
- [ ] Startup fails on an unknown generation model, and on `chunk_target_tokens` above the model's limit.
- [ ] `grep -r "hosted_api_key\|model_mode\|prefer_hosted" backend/ docs/` returns nothing outside historical notes.
- [ ] With the image **already built**, a full upload-and-ask cycle succeeds with the container's networking disabled (`docker run --network none`) in `generation_mode: "local"`.
- [ ] README §7 and the M4 handoff updated for the removed `hosted_*` settings.

## 11. What this module does NOT give you

### 11.1 It does not make generation-time egress safe
- The control is a **signed GCP BAA covering Agent Platform**, verified against Google's covered-products list. Code cannot supply that.
- `phi_egress_acknowledged` records that a human asserted it. It does not check it.
- What this module *does* do is shrink the exposed surface from *every document at ingestion* to *the excerpts for one question, only when asked*.

### 11.2 A green suite proves plumbing, not quality
- It proves correct prompts, routing, pinning, failure classification, and no PHI in messages.
- It does **not** prove retrieval got better. The query-prompt fix and the model change are both unmeasured on this corpus. Epic 1 M8 settles that.

### 11.3 Retrieval quality versus the hosted alternative
- `gemini-embedding-001` may well retrieve better than a 0.6B open model. Unmeasured either way, and deliberately not the deciding factor: keeping documents on-device was.

### 11.4 Cold starts
- ~1.19 GB of weights plus torch and spaCy make this a heavy image. Irrelevant on a VM or a laptop; a real cost on Cloud Run. It is a hosting consideration, deferred with hosting.

## 12. Verified facts underpinning these decisions

- Verified 2026-08-24 / 2026-08-25 against live documentation and package sources.

| Fact | Source | Consequence |
|---|---|---|
| `Qwen/Qwen3-Embedding-0.6B` is 1024-dim, 32768 max positions, `sentence-transformers`-native | HF `config.json`, `modules.json`, model tags | `embed_dim` and vec0 schema unchanged; 800-token chunks fit whole |
| Weights are `model.safetensors`, **1191.6 MB**; revision `97b0c614…` | HF model API, 2026-08-25 | pinnable; image cost known |
| Its prompts are asymmetric and `default_prompt_name` is `null` | HF `config_sentence_transformers.json` | §6.3 exists because of this |
| `all-MiniLM-L6-v2` caps at **256** tokens; `bge-small`/`e5-small` at 512 | HF `sentence_bert_config.json` | §5.5 guard; MiniLM rejected |
| Agent Platform requires ADC + project; an API key alone **silently falls back** to `generativelanguage.googleapis.com` | `python-genai` `_api_client.py` | §5.4 validator |
| LangChain repeats the same fallback: *"API key is required (default when no `project` is set)"* | `langchain_google_genai/_common.py` | `vertexai=True` always explicit |
| Raw SDK `genai.Client` takes `enterprise=True`; `vertexai=` is its legacy alias | `python-genai` client.py | **not called directly by this module** — LangChain's own parameter is `vertexai` |
| `ChatVertexAI` / `VertexAIEmbeddings` deprecated since 3.2.0, removal 4.0.0 | `langchain-google-vertexai` source | use `langchain-google-genai` equivalents |
| `VertexModelGardenLlama` is **not** deprecated | `model_garden_maas/llama.py` | Llama is the lower-risk second provider |
| Llama allowlist: `llama-3.3-70b-instruct-maas`, `llama-4-maverick-17b-128e-instruct-maas`, `llama-4-scout-17b-16e-instruct-maas` | `model_garden_maas/_base.py` | validated at startup |
| `gemini-2.5-flash` retires **2026-10-20**; `gemini-3.5-flash` is current | Agent Platform model docs | chosen default |
| Self-deploying an open embedding model to a Vertex Endpoint is supported but requires dedicated always-on infrastructure | Model Garden self-deployed-models docs | rejected on cost for a single user |
| ADC resolves from an attached service account on **all** GCP compute; WIF covers non-GCP | Agent Platform auth docs | hosting choice does not constrain this module |

## 13. Open items

1. **BAA coverage for Llama/Mistral MaaS specifically** is unconfirmed. Verify before real PHI on those providers.
2. **`gemini-3.5-flash` retirement date** was not found in the docs consulted. Confirm before treating it as a long-lived default.
3. **`SentenceTransformer.encode()` signature for `prompt_name`** and the `revision` argument — confirm against `sentence-transformers>=3.0` at implementation time. The prompts themselves are verified.
4. **`tenacity` availability** as a `langchain-core` transitive dependency — confirm, or write ~15 lines of explicit backoff for the generation retry rather than add a direct dependency.
5. **Qwen3-Embedding ships no `sentence_bert_config.json`**, so the effective `max_seq_length` comes from the model/tokenizer config. Confirm the loaded value at implementation rather than assume 32768; §5.5's guard depends on reading it correctly.
6. **CPU embedding latency** on a realistic document is unmeasured. Record it during implementation so the ingestion UX is a known quantity.
7. **Per-provider `gcp_location`** deferred. MaaS models are region-limited; a single `gcp_location` holds until a real conflict appears.
8. **Hosting remains out of scope**, deferred 2026-08-24. §12's last row is why that costs this module nothing.
