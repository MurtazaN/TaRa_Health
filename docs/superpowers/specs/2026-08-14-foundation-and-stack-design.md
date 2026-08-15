# TaRa Health — Foundation & Tech-Stack Design

- **Status:** Approved 2026-08-14.
- **Supersedes:** nothing. Adds the tooling and infrastructure layer the Epic 1–4 docs never specified.
- **Does not change:** any Epic 1 module contract. All functional behaviour stays governed by `docs/epic1_grounded_qa/`.

---

## 1. Why this document exists

- The epic docs settle *architecture* (module boundaries, contracts, data flow) but never settle *tooling*.
- An audit on 2026-08-14 found zero mentions across `docs/`, `README.md`, and `CLAUDE.md` of:
  - agent frameworks (CrewAI, LangGraph, LangChain, AutoGen, Semantic Kernel);
  - telemetry (OpenTelemetry, OpenLLMetry, Traceloop);
  - observability platforms (Arize Phoenix, Langfuse, LangSmith);
  - evaluation frameworks (DeepEval, Ragas, promptfoo).
- Three decisions had therefore been made silently, by omission:
  1. the Epic 2 orchestrator is hand-rolled;
  2. there is no execution observability of any kind;
  3. the M8 eval harness is hand-rolled and unbuilt.
- The repository also had no `backend/`/`frontend/`/`deployment/` separation, no CI, and no containers.

## 2. Constraints this design is bound by

1. **Local-first is the default path.** Protected health information (PHI) stays on device unless the user explicitly opts into egress.
2. **The project serves two goals at once** — a genuinely usable personal tool *and* a demonstration of agentic-AI engineering. Neither may compromise the other.
3. **Vendor choices must stay swappable**, mirroring the existing `LLMClient` protocol rule: local-vs-hosted is configuration, never a code change.
4. **The naming rules in `CLAUDE.md` are non-negotiable** — every package/file/function names its object.
5. **Import direction holds:** kernel ← planes ← capabilities ← safety/agent ← `web_app`.

## 3. Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Repository shape | Monorepo: `backend/`, `frontend/`, `deployment/` |
| 2 | Instrumentation | OpenTelemetry Python SDK + OpenInference semantic conventions |
| 3 | Trace backend | Arize Phoenix, self-hosted single container; Langfuse a documented one-variable swap |
| 4 | PHI redaction | Presidio, applied to span attributes before export and to the hosted-egress path |
| 5 | Evaluation gate | DeepEval under `pytest`, local judge model, telemetry opted out |
| 6 | Emergency triage | Keyword pass authoritative; Llama Guard with a **custom** emergency taxonomy as an additive second layer |
| 7 | Rails framework | NeMo Guardrails **rejected** (§10) |
| 8 | Agent framework | LangGraph, adopted at Epic 2, decided now |
| 9 | Structured output | Instructor (not Outlines — see §10) |
| 10 | Retrieval reranking | `BAAI/bge-reranker-v2-m3` cross-encoder, run via `sentence-transformers` |
| 11 | CI | GitHub Actions: `ruff`, `mypy`, `pytest`, `docker build`. Eval gate runs locally only. |
| 12 | Dependency manifest | Repaired — four unused dependencies removed (§4.3) |

## 4. Repository layout

### 4.1 Target tree

```
tara-health/
├── backend/
│   ├── src/tara/           # moved verbatim from src/tara/
│   ├── tests/              # moved verbatim; adds behavior_evals/
│   └── pyproject.toml
├── frontend/               # index.html + app.js, moved out of the Python package
├── deployment/
│   ├── docker/             # Dockerfile.backend, compose.yaml
│   └── local/              # bootstrap script
├── .github/workflows/ci.yml
├── Makefile
└── docs/
```

### 4.2 Consequences to handle during the move

- `web_app.py` stops serving the UI from inside the package; it mounts `../../frontend/` in dev, and the image copies `frontend/` to a served path.
- The "Repository layout" section of all five design docs plus `CLAUDE.md` must be updated.
- No behaviour changes in this step — the test suite is the proof (§8).

### 4.3 Dependency repair

- **Retain** `sentence-transformers` — currently unused (embeddings moved to the LM Studio endpoint), but it becomes the reranker runner (§6.4), so it stops being dead weight.
- Remove `pymupdf4llm` — unused; `text_extraction.py` imports plain `pymupdf`.
- Remove `docling` — unused until M6 OCR; re-add there as an extra.
- Remove `anthropic` — unused; `hosted_client.py` is an unimplemented stub.
- Add: `opentelemetry-sdk`, `openinference-instrumentation`, `presidio-analyzer`, `presidio-anonymizer`, `instructor`.
- Add to `[dev]`: `deepeval`.

## 5. New modules

| # | Module | Layer | Purpose |
|---|---|---|---|
| 1 | `phi_redaction.py` | Kernel (root module) | Presidio wrapper. One concept → a root module, per the no-one-concept-packages rule. |
| 2 | `execution_tracing/` | Plane, beside `llm_clients/` | `tracer_setup.py`, `span_emitter.py`, `span_redaction.py`. Imports kernel only. |
| 3 | `llm_clients/structured_completion.py` | Plane | Instructor wrapper: `generate_structured_object()`. |
| 4 | `semantic_search/chunk_reranker.py` | Capability | `rerank_chunks()`, mirroring `chunk_retriever.py` / `text_embedder.py`. |
| 5 | `safety_checks/hazard_classification.py` | Safety | `classify_hazards()`. Named for the job, not the model, so Llama Guard stays a config choice. |
| 6 | `tests/behavior_evals/` | Tests | DeepEval fixture set. Name already reserved in the Epic 1 layout. |

- All six respect the import direction; no capability imports another capability.
- Tracing decorators are applied *in* capability modules and imported *from* the plane — plane ← capability, which is allowed.

## 6. Data-flow changes

### 6.1 Query flow

- `retrieve_chunks()` fetches `top_k × rerank_candidate_multiplier` candidates.
- `rerank_chunks()` scores them with the cross-encoder; `top_k` survive.
- Spans wrap: `screen_for_emergency`, `embed_query`, `find_nearest_chunks`, `rerank_chunks`, `llm_generate`, `apply_safety_framing`.

### 6.2 Egress flow

- Every span attribute passes through `phi_redaction` before export.
- When `model_mode` is `hosted`/`hybrid`, the assembled context passes through `phi_redaction` before leaving the device.

### 6.3 Abstention rule (corrected)

- There is **one** abstention decision, reading whichever score is final.
- `rerank_enabled=false` → decision reads bi-encoder cosine similarity, range −1..1, against `abstain_threshold`.
- `rerank_enabled=true` → decision reads the cross-encoder score, a different scale, against `rerank_abstain_threshold`.
- When reranking is on, the cosine gate does **not** also apply — pre-filtering weak candidates defeats the purpose of a cross-encoder.
- Two settings exist because both paths must stay working; one setting whose meaning changes with a flag cannot hold both calibrations.

### 6.4 Reranker specifics

- Model: `BAAI/bge-reranker-v2-m3` (~278M params, Apache 2.0, CPU-viable at these batch sizes).
- Runner: `sentence-transformers` `CrossEncoder` — already a declared dependency, previously unused.
- `rerank_abstain_threshold` is calibrated against the M8 fixture set, not guessed.

## 7. Configuration additions

- All default to the safe or off position, so the restructure alone changes nothing observable.

| # | Setting | Default |
|---|---|---|
| 1 | `TARA_TRACING_ENABLED` | `false` |
| 2 | `TARA_OTLP_ENDPOINT` | `http://localhost:6006/v1/traces` |
| 3 | `TARA_PHI_REDACTION_ENABLED` | `true` |
| 4 | `TARA_RERANK_ENABLED` | `false` until M8 calibrates it |
| 5 | `TARA_RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` |
| 6 | `TARA_RERANK_CANDIDATE_MULTIPLIER` | `4` |
| 7 | `TARA_RERANK_ABSTAIN_THRESHOLD` | Unset until calibrated |
| 8 | `TARA_HAZARD_CLASSIFIER_MODEL` | Empty; keyword-only until M5 |

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
  - Recording HTTP fixtures — they go stale on every prompt change, and prompts change constantly through M4/M5.
  - A small hosted judge on synthetic fixtures — viable later; adds an API key and cost now.
- Revisit when the fixture set is large enough that running it locally becomes a chore.

## 9. Phasing and verification

| # | Phase | Contents | Verification |
|---|---|---|---|
| 1 | Foundation | Restructure, dependency repair, CI, Docker, Makefile | `pytest` still reports 67 passed / 3 skipped after the move; `docker compose up` serves `/` |
| 2 | Observability | `phi_redaction`, `execution_tracing`, Phoenix wiring | An `/ask` call produces a span tree at `localhost:6006` with names and dates redacted |
| 3 | Epic 1 resumes | M4 (Instructor + reranker) → M5 (Llama Guard) → M6 → M7 → M8 (DeepEval) | The existing Epic 1 build order and acceptance criteria, unchanged |

- Phases 1 and 2 change **no product behaviour**. Every functional change lives in phase 3, under contracts already reviewed.
- Ordering is load-bearing: the restructure must land before M4, or M4's code gets moved twice.

## 10. Rejected, with reasons

- Recorded so these are not silently revisited.

| # | Tool | Reason for rejection |
|---|---|---|
| 1 | **NeMo Guardrails** | Duplicates the M5 input/output-rail architecture; each rail costs a local inference pass on a 4B model; introduces Colang, a DSL, against the explicit-named-modules convention; puts a framework between the safety layer and the model, weakening the "cannot be reasoned away" guarantee. |
| 2 | **Guardrails AI** | Lighter than NeMo and DSL-optional, but its one relevant validator (`DetectPII`) is itself built on Presidio, which decision 4 adopts directly. Reconsider past ~4 validators. |
| 3 | **Outlines** | `from_lmstudio()` exists, but its own docs state server-based models give it "limited control … restricted support for certain output types". Constrained decoding needs logits access, unavailable over HTTP. The guarantee does not survive the LM Studio backend. **Revisit if the backend moves to vLLM.** |
| 4 | **Zep** | Positioned as a managed cloud platform ("enterprise scale", "governed Context Lake", sub-200ms SLA). Self-hosting is not its centre of gravity; routing health memory through it contradicts local-first. |
| 5 | **Mem0** | Closest call. Genuinely self-hostable (SQLite at `~/.mem0/vector_store.db`, Ollama-backable). But memory extraction costs an extra local inference per turn, and Epic 2 M4 `profile_memory` is a single-profile structured store — a small SQLite table. **Revisit if profile memory needs semantic recall over conversation history rather than structured-fact lookup.** |
| 6 | **CrewAI** | Core abstraction is role-playing agent *teams*; TaRa is single-agent, single-profile, one action at a time. |
| 7 | **Microsoft Agent Framework** | Real (the AutoGen + Semantic Kernel consolidation) but its centre of gravity is .NET/Azure, against a Python local-first app. |
| 8 | **Langfuse** (as default) | Requires PostgreSQL + ClickHouse + MinIO; too heavy beside a local model on a laptop. Kept as a one-variable swap since both speak OTLP. |

## 11. Verified facts underpinning these decisions

- Checked against live documentation on 2026-08-14, not recalled.

1. Langfuse exposes native OTLP ingestion at `/api/public/otel`, self-hosted from v3.22.0 — so the trace backend is swappable by endpoint.
2. Phoenix self-hosts as a single container, `arizephoenix/phoenix:latest`, ports 6006 and 4317.
3. LangGraph is at 1.0.x; `interrupt()` + `Command(resume=...)` + a checkpointer give durable pause/resume, and `interrupt_before=["tools"]` halts before tool execution.
4. DeepEval's `GEval` accepts a `DeepEvalBaseLLM` instance directly — no remote call — and `DEEPEVAL_TELEMETRY_OPT_OUT=true` disables telemetry. `assert_test()` raises `AssertionError`, so it can gate a build.
5. Llama Guard's stock taxonomy is 14 MLCommons-aligned categories: S1 Violent Crimes, S2 Non-Violent Crimes, S3 Sex Crimes, S4 Child Exploitation, S5 Defamation, S6 Specialized Advice, S7 Privacy, S8 Intellectual Property, S9 Indiscriminate Weapons, S10 Hate, S11 Self-Harm, S12 Sexual Content, S13 Elections, S14 Code Interpreter Abuse.
6. **No stock category covers medical urgency** (chest pain, stroke, anaphylaxis) — but the taxonomy is supplied in the prompt and is fully replaceable, so a custom `Medical Emergency` category is possible. Recall is unproven zero-shot; the M8 fixture must prove it before any weight is placed on it.
7. Presidio supports custom recognizers from regex deny-lists — needed for insurer-specific identifiers (member/group numbers) its stock entity set misses.

## 12. Forward decisions for Epic 2

- Recorded now so the Epic 2 doc is rewritten against them.

1. **LangGraph replaces the hand-rolled orchestrator.** Its `interrupt()` primitive maps near-literally onto the confirmation-gate contract:
   - `HumanInterrupt.description` → the action `preview`;
   - `Command(resume=...)` → the explicit affirmative;
   - the checkpointer → `proposed` → `confirmed`/`cancelled` surviving a restart;
   - `interrupt_before=["tools"]` → the executor refusing unconfirmed consequential tools.
2. **LM Studio can back a LangChain `BaseChatModel`** via `langchain_openai.ChatOpenAI(base_url=...)`, so LangGraph needs no hosted provider and no new runtime. Add a `langchain_openai`-backed `LLMClient` implementation when LangGraph lands — not before.
3. **Instructor overlap to re-examine at that point:** LangChain's `.with_structured_output()` covers the same ground. Keep one, not both.

## 13. Open items

1. `rerank_abstain_threshold` has no value until M8 calibration.
2. The custom Llama Guard emergency taxonomy text is undrafted; it lands with M5.
3. Whether `hosted_client.py` targets Anthropic or another provider is still unsettled (`hosted_api_key` is deliberately provider-agnostic).
4. A rotation is outstanding for the `HUGGINGFACEHUB_API_KEY` and `NVIDIA_API_KEY` values present in the local `.env` — gitignored and never committed, but exposed in a session transcript.
