# TaRa Health — Epic 0: Foundation

- **Epic 0 scope:** the infrastructure and tooling layer every other epic stands on — monorepo separation, CI/CD, containers, execution tracing, PHI redaction, and the settled third-party stack.
- **Explicitly out of scope:** any change to an Epic 1 module *contract*. M1, M2, and M3 here are behaviour-neutral; the functional work stays governed by [epic1_grounded_qa/](../epic1_grounded_qa/README.md).
- **Why "Epic 0":** it precedes Epic 1 in build order but was designed after it, once the missing layer became visible. Modules M1 and M2 must land before Epic 1 M4, or M4's files get moved twice.
- **Status:** Approved 2026-08-14. **M1 implemented 2026-08-15** — restructure, dependency repair, Makefile, containers, and CI are live on `main`-bound branch `feat/foundation-and-stack`. M2, M3, and M4 are not yet built.
- **Last updated:** 2026-08-15.

---

## Modules

1. [M1 — repo_restructure](M1_repo_restructure.md) — move to a `backend/` + `frontend/` + `deployment/` monorepo and add the CI, container, and task-runner layer, with zero behaviour change.
2. [M2 — phi_redaction](M2_phi_redaction.md) — strip protected health information out of any text before it leaves the process, and prove the recall with a fixture.
3. [M3 — execution_tracing](M3_execution_tracing.md) — make a request's internal execution visible as a trace, with every string attribute redacted before it enters a span.
4. [M4 — epic1_handoff](M4_epic1_handoff.md) — the per-module deltas these decisions impose on Epic 1 M3–M8. A planning boundary, not a task list.
5. [M5 — model_backends](M5_model_backends.md) — two real model backends: hosted generation on Google Cloud Agent Platform, and embeddings running in-process. Removes the LM Studio dependency without sending documents anywhere to be indexed. Added 2026-08-25, after M4; independent of M3.

- **M2 and M3 were one module until 2026-08-15.** They were split because `phi_redaction.py` is a *kernel* module while `execution_tracing/` is a *plane* that depends on it — bundling a kernel module with its own consumer inverts the layering enforced everywhere else. Redaction also has a second consumer independent of tracing (the Epic 1 M4 hosted-egress path), and as the security-critical half it earns its own review gate.

---

## 1. Why this epic exists

- An audit on 2026-08-14 found the epic docs settle *architecture* (module boundaries, contracts, data flow) but never settle *tooling*.
- Zero mentions across `docs/`, `README.md`, and `CLAUDE.md` of:
  - agent frameworks (CrewAI, LangGraph, LangChain, AutoGen, Semantic Kernel);
  - telemetry (OpenTelemetry, OpenLLMetry, Traceloop);
  - observability platforms (Arize Phoenix, Langfuse, LangSmith);
  - evaluation frameworks (DeepEval, Ragas, promptfoo).
- Three decisions had therefore been made silently, by omission:
  1. the Epic 2 orchestrator is hand-rolled;
  2. there is no execution observability of any kind;
  3. the M8 eval harness is hand-rolled and unbuilt.
- The repository also had no `backend/`/`frontend/`/`deployment/` separation, no CI, and no containers.

## 2. Goals

1. Separate the deployable units so backend, frontend, and deployment concerns stop sharing one directory.
2. Make execution observable, so answer quality can be attributed to retrieval or to the model rather than guessed at.
3. Keep protected health information on the device *and* out of the payloads that infrastructure handles.
4. Settle the third-party stack once, with reasons recorded, so choices are not silently revisited.
5. Gate every push on lint, type-check, test, and image build.

- **Success bar:**
  - `make test` reports the same count before and after the restructure.
  - An `/upload` call produces a span tree in Phoenix in which no attribute contains a person name or a member identifier.

## 3. Constraints this design is bound by

1. **Local-first is the default path.** PHI stays on device unless the user explicitly opts into egress.
2. **The project serves two goals at once** — a genuinely usable personal tool *and* a demonstration of agentic-AI engineering. Neither may compromise the other.
3. **Vendor choices must stay swappable**, mirroring the `LLMClient` rule: local-vs-hosted is configuration, never a code change.
4. **The naming rules in `CLAUDE.md` are non-negotiable** — every package/file/function names its object.
5. **Import direction holds:** kernel ← planes ← capabilities ← safety/agent ← `web_app`.

## 4. Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Repository shape | Monorepo: `backend/`, `frontend/`, `deployment/` |
| 2 | Instrumentation | OpenTelemetry Python SDK; OpenInference semantic conventions arrive with Epic 1 M4 |
| 3 | Trace backend | Arize Phoenix, self-hosted single container; Langfuse a documented one-variable swap |
| 4 | PHI redaction | Presidio, applied to span attributes before export and to the hosted-egress path |
| 5 | Evaluation gate | DeepEval under `pytest`, local judge model, telemetry opted out |
| 6 | Emergency triage | Keyword pass authoritative; Llama Guard with a **custom** emergency taxonomy as an additive second layer |
| 7 | Rails framework | NeMo Guardrails **rejected** (§11) |
| 8 | Agent framework | LangGraph, adopted at Epic 2, decided now |
| 9 | Structured output | Instructor (not Outlines — see §11) |
| 10 | Retrieval reranking | `BAAI/bge-reranker-v2-m3` cross-encoder, run via `sentence-transformers` |
| 11 | CI | GitHub Actions: `ruff`, `mypy`, `pytest`, `docker build`. Eval gate runs locally only. |
| 12 | Dependency manifest | Repaired — three unused dependencies removed (M1) |

## 5. Architecture — new modules

| # | Module | Layer | Purpose |
|---|---|---|---|
| 1 | `phi_redaction.py` | Kernel (root module) | Presidio wrapper. One concept → a root module, per the no-one-concept-packages rule. |
| 2 | `execution_tracing/` | Plane, beside `llm_clients/` | `tracer_setup.py`, `span_emitter.py`, `span_redaction.py`. Imports kernel only. |
| 3 | `llm_clients/structured_completion.py` | Plane | Instructor wrapper: `generate_structured_object()`. Lands with Epic 1 M4. |
| 4 | `semantic_search/chunk_reranker.py` | Capability | `rerank_chunks()`. Lands with Epic 1 M3 rework. |
| 5 | `safety_checks/hazard_classification.py` | Safety | `classify_hazards()`. Named for the job, not the model. Lands with Epic 1 M5. |
| 6 | `tests/behavior_evals/` | Tests | DeepEval fixture set. Name already reserved in the Epic 1 layout. Lands with Epic 1 M8. |

- Row 1 is built in M2; row 2 in M3. Rows 3–6 are built in Epic 1, against the deltas in [M4_epic1_handoff.md](M4_epic1_handoff.md).

## 6. Data-flow changes

### 6.1 Query flow

- `retrieve_chunks()` fetches `top_k × rerank_candidate_multiplier` candidates.
- `rerank_chunks()` scores them with the cross-encoder; `top_k` survive.
- Spans wrap: `screen_for_emergency`, `embed_query`, `find_nearest_chunks`, `rerank_chunks`, `llm_generate`, `apply_safety_framing`.

### 6.2 Egress flow

- Every span attribute passes through `phi_redaction` before it reaches a span.
- When `generation_mode` is `agent_platform`/`hybrid`, the assembled context passes through `phi_redaction` before leaving the device (Epic 0 M5).

### 6.3 Abstention rule

- There is **one** abstention decision, reading whichever score is final.
- `rerank_enabled=false` → the decision reads bi-encoder cosine similarity, range −1..1, against `abstain_threshold`.
- `rerank_enabled=true` → the decision reads the cross-encoder score, a different scale, against `rerank_abstain_threshold`.
- When reranking is on, the cosine gate does **not** also apply — pre-filtering weak candidates defeats the purpose of a cross-encoder.
- Two settings exist because both paths must keep working; one setting whose meaning changes with a flag cannot hold both calibrations.

### 6.4 Reranker specifics

- Model: `BAAI/bge-reranker-v2-m3` (~278M params, Apache 2.0, CPU-viable at these batch sizes).
- Runner: the `CrossEncoder` class from `sentence-transformers` — already a declared dependency, previously unused.
- `rerank_abstain_threshold` is calibrated against the Epic 1 M8 fixture set, not guessed.

## 7. Configuration additions

- All default to the safe or off position, so infrastructure work changes nothing observable.

| # | Setting | Default | Lands in |
|---|---|---|---|
| 1 | `TARA_FRONTEND_DIR` | `<repo>/frontend` | Epic 0 M1 |
| 2 | `TARA_SERVER_HOST` | `127.0.0.1` | Epic 0 M1 |
| 3 | `TARA_TRACING_ENABLED` | `false` | Epic 0 M3 |
| 4 | `TARA_OTLP_ENDPOINT` | `http://localhost:6006/v1/traces` | Epic 0 M3 |
| 5 | `TARA_SERVICE_NAME` | `tara-backend` | Epic 0 M3 |
| 6 | `TARA_PHI_REDACTION_ENABLED` | `true` | Epic 0 M2 |
| 7 | `TARA_PHI_REDACTION_NLP_MODEL` | `en_core_web_lg` | Epic 0 M2 |
| 8 | `TARA_RERANK_ENABLED` | `false` until calibrated | Epic 1 M3 |
| 9 | `TARA_RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Epic 1 M3 |
| 10 | `TARA_RERANK_CANDIDATE_MULTIPLIER` | `4` | Epic 1 M3 |
| 11 | `TARA_RERANK_ABSTAIN_THRESHOLD` | Unset until calibrated | Epic 1 M3 |
| 12 | `TARA_HAZARD_CLASSIFIER_MODEL` | Empty; keyword-only | Epic 1 M5 |
| 13 | `TARA_GENERATION_MODE` | `local` | Epic 0 M5 |
| 14 | `TARA_GCP_PROJECT` | `""` (empty) | Epic 0 M5 |
| 15 | `TARA_GCP_LOCATION` | `us-central1` | Epic 0 M5 |
| 16 | `TARA_AGENT_PLATFORM_PROVIDER` | `gemini` | Epic 0 M5 |
| 17 | `TARA_PHI_EGRESS_ACKNOWLEDGED` | `false` | Epic 0 M5 |
| 18 | `TARA_EMBED_MODEL_REVISION` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Epic 0 M5 |
| 19 | `TARA_CHUNK_TARGET_TOKENS` | `800` | Epic 0 M5 |
| 20 | `TARA_CHUNK_OVERLAP_TOKENS` | `100` | Epic 0 M5 |
| 21 | `TARA_GEMINI_MODEL` | `gemini-3.5-flash` | Epic 0 M5 |
| 22 | `TARA_LLAMA_MODEL` | `meta/llama-3.3-70b-instruct-maas` | Epic 0 M5 |
| 23 | `TARA_MISTRAL_MODEL` | `mistral-medium-3` | Epic 0 M5 |
| 24 | `TARA_EMBED_MODEL` | `Qwen/Qwen3-Embedding-0.6B` | Epic 0 M5 |
| 25 | `TARA_EMBED_MODEL_OFFLINE_ONLY` | `false` | Epic 0 M5 |

- `TARA_HOSTED_MODEL` and `TARA_HOSTED_API_KEY`, planned in an earlier draft of this table, were never implemented and do not exist — M5 replaced that draft with the Agent Platform + in-process-embedding split above (see [M5 §5.1–5.3](M5_model_backends.md#5-configuration-surface)).

## 8. Containers and CI

### 8.1 Compose services

- Two services, not three. **LM Studio stays on the host** — it needs direct graphics-hardware access.
- The backend container reaches the host model via `host.docker.internal`.

| # | Service | Image | Ports |
|---|---|---|---|
| 1 | `tara-backend` | Built from `deployment/docker/Dockerfile.backend` | 8000 |
| 2 | `phoenix` | `arizephoenix/phoenix:latest` | 6006 (UI + OTLP HTTP), 4317 (OTLP gRPC) |

### 8.2 Pipeline jobs

| # | Job | Command |
|---|---|---|
| 1 | `lint` | `ruff check` |
| 2 | `typecheck` | `mypy` |
| 3 | `test` | `pytest`, excluding `behavior_evals/` |
| 4 | `build` | `docker build` on the backend image |
| 5 | `eval` | `make eval` — **local only**, not a pipeline job |

### 8.3 Why the eval gate is local

- The DeepEval judge is the local LM Studio model; a GitHub Actions runner has neither LM Studio nor a local model.
- Rejected alternatives:
  - Recording HTTP fixtures — they go stale on every prompt change, and prompts change constantly through Epic 1 M4/M5.
  - A small hosted judge on synthetic fixtures — viable later; adds an API key and cost now.
- Revisit when the fixture set is large enough that running it locally becomes a chore.

## 9. Build order (module sequence)

| # | Module | Changes behaviour? | Gate |
|---|---|---|---|
| 1 | [M1 — repo_restructure](M1_repo_restructure.md) | No | **DONE 2026-08-15** — suite held at 67 passed / 3 skipped; `make up` then `curl http://127.0.0.1:8000/` returns `200` |
| 2 | [M2 — phi_redaction](M2_phi_redaction.md) | No | **DONE 2026-08-24** — gated recall 31/31; **true recall 33/64 = 51.6%** with 15 documented `xfail` gaps. The gated figure is a regression guard, not a measure of protection |
| 3 | [M3 — execution_tracing](M3_execution_tracing.md) | No | An `/upload` call produces a span tree at `localhost:6006` with no name or member identifier in any attribute |
| 4 | [M4 — epic1_handoff](M4_epic1_handoff.md) | n/a — a planning boundary | Epic 1 resumes at its own M4 |
| 5 | [M5 — model_backends](M5_model_backends.md) | **Yes** — replaces the model layer | **DONE 2026-08-25** — suite holds at 213 passed / 4 skipped / 16 xfailed; `make lint`/`make typecheck` clean. **Two gaps remain open, listed in §9.1 below.** Read that before treating spec §10 as met |

- **Ordering is load-bearing.** M1 must land before any Epic 1 M4 code, or M4's files get moved twice.
- **M1 and M2 are behaviour-neutral by design.** Every functional change lives in Epic 1.
- **M5 is the exception to that rule**, and deliberately so: it replaces the model layer. Ingestion and retrieval stay fully on-device; only Agent Platform *generation* egresses, and only when opted into — which requires a signed GCP BAA that no code can enforce.

### 9.1 M5 acceptance — what is actually pinned

- Spec [§10](M5_model_backends.md#10-acceptance) asks for "all 12 assertions in §9.3 present and passing". Eleven are; one is not, and the container check has never been run. Recorded here rather than implied by a green suite.

| §9.3 | Pinned behaviour | State |
|---|---|---|
| 1 | `embed_query` passes `prompt_name="query"`; `embed_texts` does not | **Passing** — `test_embed_query_applies_the_query_prompt`, `test_embed_texts_applies_no_prompt` |
| 2 | `SentenceTransformer` constructed with the pinned `revision` | **Passing** — `test_model_is_constructed_with_the_pinned_revision`, which builds the real constructor against a recorder |
| 3 | Vectors are unit length | **Passing** |
| 4 | Count mismatch raises | **Passing** |
| 5 | `vertexai=True` on every LangChain construction; empty `gcp_project` raises when generation egresses | **Passing as of the final fix wave.** It was previously HALF-PRESENT: every client test patched `_chat_model` wholesale, so the constructor never ran and deleting the `vertexai=True` line would have shipped green. `test_gemini_model_is_constructed_with_vertexai_pinned` now exercises the real constructor. MaaS is exempt by construction — those classes expose no `vertexai` field, asserted by `test_maas_classes_expose_no_vertexai_field` |
| 6 | 429 retried then succeeds; 429 forever → `AgentPlatformUnavailableError` with the attempt count asserted | **Passing** — attempt count now hard-coded to 3 rather than compared against the constant it is meant to pin |
| 7 | 403 / 404 → `AgentPlatformConfigError` with exactly one call | **Passing** |
| 8 | A distinctive synthetic identifier never appears in `str(exc)` | **Passing as of the final fix wave.** It was previously VACUOUS: the identifier was never in the upstream error's message, so the assertion could not fail. It now lives inside the chained cause — the real §7.2 risk, since Google errors echo request bodies — and `repr()` is checked too |
| 9 | Emergency question returns `safety_flag: "emergency"` and HTTP 200 while every Agent Platform call raises | **`xfail(strict=True)`, pending Epic 1 M4.** `screen_for_emergency()` is still an Epic 1 stub raising `NotImplementedError`, so the real path cannot pass yet. `test_real_answer_path_triages_emergency_while_agent_platform_is_down` runs that real path and is recorded as a strict xfail; it flips to a genuine pass when M4 lands. The sibling test covers response shaping only and no longer claims §4.3 |
| 10 | `verify_generation_model()` rejects an unknown model with no network | **Passing** |
| 11 | `chunk_target_tokens` above the model's limit fails at startup | **Passing**, now with a 10% safety margin below the limit rather than a bare `>` (§5.5 asks for margin) |
| 12 | `generation_mode: "local"` performs no network call across a full ingest-and-ask cycle | **Partially pinned.** `test_local_ingest_and_retrieval_resolve_no_hostname` covers ingest+retrieve with a faked embedder. The container half is unverified — see below |

- **The container offline-embedding check has NEVER been run.** Docker was unavailable in the implementing environment, so `make up` followed by `docker compose -f deployment/docker/compose.yaml run --rm --network none tara-backend python -c "..."` (plan Task 6 Step 5) has not happened. A human must run it, record `max_seq_length` and `dim`, and only then treat the container path as proven.
- **Two residual risks are recorded rather than fixed**, both deliberately deferred to their own cycle:
  1. `lmstudio_host` / `ollama_host` are unvalidated URLs, so a non-loopback value egresses assembled excerpts under `generation_mode: "local"` with no gate. `web_app.main()` now WARNS when the active backend's host is not loopback; it does not refuse, because LM Studio on another machine on a LAN is legitimate.
  2. BAA coverage for Llama / Mistral MaaS specifically is still unconfirmed (spec §13 item 1).

## Global constraints

- **Python:** 3.11+ source compatibility; the dev interpreter is 3.12. `from __future__ import annotations` at the top of every module.
- **Naming (non-negotiable, from `CLAUDE.md`):** every package/file/function names its object — `local_data_stores`, never `storage`; `retrieve_chunks()`, never `retrieve()`. Modules are noun phrases; functions are verb+object. No single-letter variables. No one-concept packages — a shared concern is a well-named root module.
- **Docstrings:** purpose first, rationale second.
- **Import direction:** kernel (`config`, `data_models`, `app_errors`, `upload_validation`, `phi_redaction`) ← planes (`llm_clients`, `local_data_stores`, `execution_tracing`) ← capabilities (`document_ingestion`, `semantic_search`, `question_answering`) ← `safety_checks` ← `web_app`. Capabilities never import each other, except `question_answering → semantic_search` and `→ safety_checks`.
- **All SQL lives in `local_data_stores/`.** No SQL anywhere else.
- **Configuration is centralized** in `config.py`, env-prefixed `TARA_`. Code never hard-codes a provider, model, host, or directory.
- **Output format for every file created:** bulleted or numbered lists, never prose paragraphs. At most a one-line lead-in before a list.
- **New settings default to off or safe.**
- **Commit after every task.** Branch is `feat/foundation-and-stack`.

## 10. Cross-cutting: privacy and security

- **Self-hosting protects the destination; redaction protects the payload.** Both are required — either alone is insufficient.
- **Redaction happens at attribute-set time, not at export time.** A value that never enters a span cannot leak through a misconfigured exporter or a backend swapped in later.
- **Tracing is opt-in.** `TARA_TRACING_ENABLED` defaults to `false`, because a span carries the user's question and retrieved document text.
- **Span attributes carry counts, scores, and identifiers — never chunk text or filenames.**
- **Embeddings never egress**, unchanged from Epic 1.

## 11. Rejected, with reasons

- Recorded so these are not silently revisited.

| # | Tool | Reason for rejection |
|---|---|---|
| 1 | **NeMo Guardrails** | Duplicates the Epic 1 M5 input/output-rail architecture; each rail costs a local inference pass on a 4B model; introduces Colang, a DSL, against the explicit-named-modules convention; puts a framework between the safety layer and the model, weakening the "cannot be reasoned away" guarantee. |
| 2 | **Guardrails AI** | Lighter than NeMo and DSL-optional, but its one relevant validator (`DetectPII`) is itself built on Presidio, which decision 4 adopts directly. Reconsider past ~4 validators. |
| 3 | **Outlines** | `from_lmstudio()` exists, but its own docs state server-based models give it "limited control … restricted support for certain output types". Constrained decoding needs logits access, unavailable over HTTP. The guarantee does not survive the LM Studio backend. **Revisit if the backend moves to vLLM.** |
| 4 | **Zep** | Positioned as a managed cloud platform ("enterprise scale", "governed Context Lake", sub-200ms SLA). Self-hosting is not its centre of gravity; routing health memory through it contradicts local-first. |
| 5 | **Mem0** | Closest call. Genuinely self-hostable (SQLite at `~/.mem0/vector_store.db`, Ollama-backable). But memory extraction costs an extra local inference per turn, and Epic 2 M4 `profile_memory` is a single-profile structured store — a small SQLite table. **Revisit if profile memory needs semantic recall over conversation history.** |
| 6 | **CrewAI** | Core abstraction is role-playing agent *teams*; TaRa is single-agent, single-profile, one action at a time. |
| 7 | **Microsoft Agent Framework** | Real (the AutoGen + Semantic Kernel consolidation) but its centre of gravity is .NET/Azure, against a Python local-first app. |
| 8 | **Langfuse** (as default) | Requires PostgreSQL + ClickHouse + MinIO; too heavy beside a local model on a laptop. Kept as a one-variable swap since both speak OTLP. |
| 9 | **OpenLLMetry** (Traceloop) | Evaluated properly 2026-08-15, after being passed over without a real comparison in the original design. Three reasons, below. **Revisit at Epic 2.** |

### 11.1 OpenLLMetry — the comparison that was owed

- **Correction:** the original design named OpenLLMetry once, as "the alternative to OpenInference — either works," and chose OpenInference because Phoenix is built around those conventions. That is a convenience argument, not a merit comparison, and it left this decision effectively unmade. Evaluated properly on 2026-08-15.

- **What the two things actually are:**
  - **OpenInference** is a set of *semantic conventions* — agreed attribute names — plus Phoenix-native pairing. You write the spans.
  - **OpenLLMetry** is *auto-instrumentation*: import an instrumentor and calls to a supported library emit spans with no code of yours involved. Its whole value is not writing spans yourself.

- **What it would actually cover in TaRa:**

| # | TaRa span | Covered by OpenLLMetry? |
|---|---|---|
| 1 | LM Studio generation + embeddings (via the `openai` SDK) | **Yes** — `opentelemetry-instrumentation-openai` |
| 2 | Ollama generation, if that backend is selected | **Yes** — `opentelemetry-instrumentation-ollama` |
| 3 | Hosted Anthropic path, once built | **Yes** |
| 4 | `find_nearest_chunks` — sqlite-vec retrieval | **No.** Supported vector stores are Chroma, LanceDB, Marqo, Milvus, Pinecone, Qdrant, Weaviate. sqlite-vec is a SQLite extension and will never appear on that list. |
| 5 | `extract_text_spans`, `chunk_spans`, `ingest_document` | **No** — application orchestration, no library boundary |
| 6 | `screen_for_emergency`, `apply_safety_framing` | **No** |
| 7 | The abstention decision and its score | **No** |

- **Reason 1 — it covers the wrong half.** Rows 4 through 7 are the spans that answer TaRa's actual debugging question: *why did this answer cite the wrong page?* All of them are application-level and must be hand-written regardless. OpenLLMetry covers the model-call layer, which is roughly two of the eight spans that matter here.
- **Reason 2 — its privacy control is binary, and this project needs a middle setting.** `TRACELOOP_TRACE_CONTENT=false` disables prompt, completion, and embedding capture entirely; the default is capture-on, which would put raw PHI in spans. TaRa's requirement is neither: keep the clinical and cost content, drop the identity. That is what set-time redaction delivers, and OpenLLMetry has no equivalent setting.
- **Reason 3 — adopting it now means two span-production paths.** The hand-written path must exist either way (reason 1), so adding auto-instrumentation on top buys partial coverage at the cost of a second mechanism to reason about.
- **What is *not* a reason to reject it:** cloud lock-in. Verified — it exports to any OTLP endpoint, and the API-key check fires only when the default Traceloop SaaS endpoint is used with no custom exporter. Self-hosting is fully supported.
- **Revisit trigger — Epic 2.** LangGraph's agent loop *is* a library boundary, which is exactly what auto-instrumentation is good at. Because both emit OpenTelemetry, adding it later is purely additive: no rework, no migration. At that point evaluate whether `TRACELOOP_TRACE_CONTENT=false` paired with hand-written redacted spans is a coherent combination, or whether the two mechanisms fight.

## 12. Verified facts underpinning these decisions

- Checked against live documentation on 2026-08-14, not recalled.

1. Langfuse exposes native OTLP ingestion at `/api/public/otel`, self-hosted from v3.22.0 — so the trace backend is swappable by endpoint.
2. Phoenix self-hosts as a single container, `arizephoenix/phoenix:latest`, ports 6006 and 4317.
3. LangGraph is at 1.0.x; `interrupt()` + `Command(resume=...)` + a checkpointer give durable pause/resume, and `interrupt_before=["tools"]` halts before tool execution.
4. DeepEval's `GEval` accepts a `DeepEvalBaseLLM` instance directly — no remote call — and `DEEPEVAL_TELEMETRY_OPT_OUT=true` disables telemetry. `assert_test()` raises `AssertionError`, so it can gate a build.
5. Llama Guard's stock taxonomy is 14 MLCommons-aligned categories: S1 Violent Crimes, S2 Non-Violent Crimes, S3 Sex Crimes, S4 Child Exploitation, S5 Defamation, S6 Specialized Advice, S7 Privacy, S8 Intellectual Property, S9 Indiscriminate Weapons, S10 Hate, S11 Self-Harm, S12 Sexual Content, S13 Elections, S14 Code Interpreter Abuse.
6. **No stock category covers medical urgency** (chest pain, stroke, anaphylaxis) — but the taxonomy is supplied in the prompt and is fully replaceable, so a custom `Medical Emergency` category is possible. Recall is unproven zero-shot; the Epic 1 M8 fixture must prove it before any weight is placed on it.
7. Presidio supports custom recognizers from regex patterns — needed for insurer-specific identifiers (member/group numbers) its stock entity set misses.

## 13. Forward decisions for Epic 2

- Recorded now so [Epic2_first_actions.md](../Epic2_first_actions.md) is rewritten against them before Epic 2 planning starts.

1. **LangGraph replaces the hand-rolled orchestrator.** Its `interrupt()` primitive maps near-literally onto the confirmation-gate contract:
   - `HumanInterrupt.description` → the action `preview`;
   - `Command(resume=...)` → the explicit affirmative;
   - the checkpointer → `proposed` → `confirmed`/`cancelled` surviving a restart;
   - `interrupt_before=["tools"]` → the executor refusing unconfirmed consequential tools.
2. **LM Studio can back a LangChain `BaseChatModel`** via `langchain_openai.ChatOpenAI(base_url=...)`, so LangGraph needs no hosted provider and no new runtime. Add a `langchain_openai`-backed `LLMClient` implementation when LangGraph lands — not before.
3. **Instructor overlap to re-examine at that point:** LangChain's `.with_structured_output()` covers the same ground. Keep one, not both.

## 14. Open items

1. `rerank_abstain_threshold` has no value until Epic 1 M8 calibration.
2. The custom Llama Guard emergency taxonomy text is undrafted; it lands with Epic 1 M5.
3. ~~Whether `hosted_client.py` targets Anthropic or another provider is still unsettled (`hosted_api_key` is deliberately provider-agnostic).~~ Settled by Epic 0 M5: generation runs on Google Cloud Agent Platform via `AgentPlatformClient`, selectable between Gemini/Llama/Mistral by `agent_platform_provider`; there is no `hosted_client.py` and no API key — Agent Platform authenticates via Application Default Credentials.
4. **Out-of-band, not a code task:** rotate the `HUGGINGFACEHUB_API_KEY` and `NVIDIA_API_KEY` values in the local `.env`. The file is gitignored and has never been committed, so nothing leaked to version control, but both values appeared in a session transcript.

## 15. Verification commands

- Run from the repository root after M1:

```bash
make lint        # ruff check backend/src backend/tests
make typecheck   # mypy (from backend/)
make test        # pytest (from backend/)
make up          # docker compose -f deployment/docker/compose.yaml up -d
make eval        # DeepEval gate — local only, never in CI
```
