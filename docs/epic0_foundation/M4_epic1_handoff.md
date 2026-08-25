# Epic 0 · M3 — epic1_handoff

- **Parent:** [Epic 0 — Foundation](README.md) — overview · decisions · build order · global constraints.
- **Seams:** the bridge back to [Epic 1](../epic1_grounded_qa/README.md). Records the deltas Epic 0's decisions impose on Epic 1 [M3](../epic1_grounded_qa/M3_retrieval.md), [M4](../epic1_grounded_qa/M4_grounded_answering.md), [M5](../epic1_grounded_qa/M5_safety.md), and [M8](../epic1_grounded_qa/M8_eval_harness.md).

---

> **This file is deliberately not a task-by-task plan.** Read §1 for why, then use §3 as the input to each module's own plan.

**Goal:** Record exactly how the foundation decisions change each remaining Epic 1 module, so each module's plan can be written against a concrete delta rather than re-derived.

**Design sections:** [Epic 0 README](README.md) §3, §6, §9, §12

---

## 1. Why this module has no task list

- **Each remaining module already has a contract document.** `M4_grounded_answering.md` … `M8_eval_harness.md` are the specs. A task plan written now would either duplicate them or drift from them.
- **A plan should produce working, testable software on its own.** Epic 0 M1 and M2 do. "M4 through M8" is five modules and is not one plan.
- **Writing detailed steps for M6, M7, and M8 today would be speculative.** M8's thresholds depend on M4's output; M7's filtered retrieval depends on M3's reranked scores. Planning them before their inputs exist produces fiction.
- **The correct unit is one module per plan cycle**, following the repository's standing workflow: brainstorm → plan → implement → review.

## 2. Build order (unchanged from the Epic 1 README)

| # | Module | Prerequisite | Plan file to write when reached |
|---|---|---|---|
| 1 | M4 grounded answering | Epic 0 M1 and M2 complete | `docs/epic1_grounded_qa/M4_grounded_answering_plan.md` |
| 2 | M5 safety | M4 | `M5_safety_plan.md` |
| 3 | M6 OCR | M5 | `M6_ocr_plan.md` |
| 4 | M7 classification | M6 | `M7_classification_plan.md` |
| 5 | M8 eval harness | M7 | `M8_eval_harness_plan.md` |

- M5's safety-recall fixture gates M5 itself; it is **not** deferred to M8. That ordering is from the Epic 1 README and this spec does not change it.

## 3. Per-module deltas introduced by the foundation spec

- These are the *only* changes the foundation work imposes on the Epic 1 contracts. Everything else in each module doc stands unchanged.

### 3.1 M4 — grounded answering

| # | Delta | Detail |
|---|---|---|
| 1 | **Structured output via Instructor** | `llm_clients/structured_completion.py` exposes `generate_structured_object()`. The answering call returns a validated Pydantic model carrying the answer text and the list of cited chunk identifiers. |
| 2 | **Citation mapping stops being string parsing** | `_map_cited_chunks_to_citations` at `question_answerer.py:51-57` currently plans to regex `[chunk_id]` markers out of free text. With a typed response model the identifiers arrive as a list, so the function maps identifiers to `Citation` objects and nothing more. |
| 3 | **Answering spans land here** | M2 deliberately left `answer_question` uninstrumented because it cannot run until M5. Add `ask_question`, `llm_generate`, and `map_citations` spans using `traced_span()`. |
| 4 | **Agent Platform egress passes through redaction** | When `generation_mode` is `agent_platform` or `hybrid`, the assembled context goes through `redact_phi()` before the call to `AgentPlatformClient` (`llm_clients/agent_platform_client.py`, Epic 0 M5 — replaces the `hosted_client.py` stub this row originally pointed at). The egress payload is unchanged from what was planned here: the system prompt plus one assembled user prompt, never the corpus and never at ingestion time. |
| 5 | **Local backend routing** | Done in Epic 0 M5: `get_llm_client()` routes on `local_llm_backend` between `OllamaClient` and `OpenAICompatibleClient` (`llm_clients/openai_compatible_client.py`). No longer owed by M4. |

### 3.2 M3 — retrieval (reopened by the reranker)

| # | Delta | Detail |
|---|---|---|
| 1 | **New module** | `semantic_search/chunk_reranker.py` with `rerank_chunks()`. |
| 2 | **Model and runtime** | `BAAI/bge-reranker-v2-m3` run through the `CrossEncoder` class from `sentence-transformers`, which Epic 0 M1 retained for exactly this purpose. |
| 3 | **Candidate fetch widens** | `retrieve_chunks()` fetches `top_k × rerank_candidate_multiplier` (default 4) before reranking, then keeps `top_k`. |
| 4 | **Abstention reads one score, not two** | When `rerank_enabled` is true the cosine gate does **not** apply — pre-filtering weak candidates defeats the purpose of a cross-encoder. The decision reads the rerank score against `rerank_abstain_threshold`. When false, it reads cosine against `abstain_threshold`. Two settings exist because both paths must keep working. |
| 5 | **The threshold is calibrated, not guessed** | `rerank_abstain_threshold` has no value until M8 measures it. `rerank_enabled` stays false until then. |
| 6 | **Settings this module adds** | M2 added only the five tracing and redaction settings from spec §7. The reranker's four are added here: `TARA_RERANK_ENABLED` (default `false`), `TARA_RERANK_MODEL` (default `BAAI/bge-reranker-v2-m3`), `TARA_RERANK_CANDIDATE_MULTIPLIER` (default `4`), `TARA_RERANK_ABSTAIN_THRESHOLD` (unset until calibrated). |

### 3.3 M5 — safety

| # | Delta | Detail |
|---|---|---|
| 1 | **New module** | `safety_checks/hazard_classification.py` with `classify_hazards()`. Named for the job, not the model, so Llama Guard stays a configuration choice like `LLMClient`. |
| 2 | **Custom taxonomy, not the stock one** | Llama Guard's 14 stock categories contain **no** medical-urgency category. Chest pain, stroke signs, and anaphylaxis are invisible to it out of the box. The taxonomy is supplied in the prompt and is fully replaceable, so M5 defines a `Medical Emergency` category covering cardiac, stroke, respiratory, anaphylactic, haemorrhagic, and psychiatric red flags. |
| 3 | **Retain S6 Specialized Advice** | Useful for the output rail — it flags an answer drifting into unqualified medical advice. |
| 4 | **Fail-closed structure is unchanged** | The keyword pass over `RED_FLAG_PATTERNS` stays authoritative. Either layer may escalate; neither may downgrade the other. |
| 5 | **Trust is earned by the fixture, not the model card** | A custom category is zero-shot on a model never trained for it. The safety-recall fixture measures its recall before any weight is placed on it. Below 100 percent recall, it stays purely additive. |
| 6 | **Settings this module adds** | `TARA_HAZARD_CLASSIFIER_MODEL` (default empty, meaning keyword-only), completing spec §7. |

### 3.4 M8 — eval harness

| # | Delta | Detail |
|---|---|---|
| 1 | **DeepEval replaces the hand-rolled harness** | `tests/behavior_evals/` (the name already reserved in the Epic 1 layout). `assert_test()` raises `AssertionError`, which is what makes it a gate rather than a dashboard. |
| 2 | **The judge is local** | `GEval` accepts a `DeepEvalBaseLLM` subclass instance directly; passing an instance rather than a model-name string means no remote call, so no document text egresses. |
| 3 | **Telemetry off** | Set `DEEPEVAL_TELEMETRY_OPT_OUT=true`. Without a Confident AI key, no evaluation data leaves the machine. |
| 4 | **Runs locally, never in CI** | The judge is the local LM Studio model, which a hosted runner does not have. `make eval` is the entry point; `make test` excludes `tests/behavior_evals`. |
| 5 | **It calibrates `rerank_abstain_threshold`** | See §3.2 row 5. |
| 6 | **It settles OPEN_QUESTIONS.md #1** | Measure citation correctness and honesty for `local` versus `hosted`, then pick the default with evidence. |

### 3.5 M6 and M7 — unchanged

- **M6 OCR:** no delta. Re-add `docling` via the `[ocr]` extra that M1 Task 2 created.
- **M7 classification:** no delta. The `doc_type_hint` parameter is already accepted and unused in `retrieve_chunks()`.

## 4. Forward decisions recorded for Epic 2

- Not Epic 0 work. Recorded here so the Epic 2 doc is rewritten against them before Epic 2 planning starts.

1. **LangGraph replaces the hand-rolled orchestrator.** Its `interrupt()` and `Command(resume=...)` primitives, plus a checkpointer, map onto the confirmation-gate contract: `HumanInterrupt.description` is the action preview, the resume value is the explicit affirmative, the checkpointer makes `proposed → confirmed`/`cancelled` survive a restart, and `interrupt_before=["tools"]` enforces the halt at framework level.
2. **LM Studio can back a LangChain `BaseChatModel`** via `langchain_openai.ChatOpenAI(base_url=...)`, so LangGraph needs no hosted provider and no new runtime. Add a `langchain_openai`-backed `LLMClient` implementation when LangGraph lands — not before.
3. **Re-examine Instructor at that point.** LangChain's `.with_structured_output()` covers the same ground. Keep one, not both.

## 5. Deferred adoptions with named triggers

- Recorded so these are revisited on evidence rather than on impulse.

| # | Tool | Revisit when |
|---|---|---|
| 1 | Outlines | The local backend moves from LM Studio to vLLM, at which point constrained decoding becomes available and is strictly stronger than retry-based validation. |
| 2 | Mem0 | Profile memory needs semantic recall over conversation history rather than lookup of structured facts. |
| 3 | Guardrails AI | The validator count passes roughly four, at which point a composition framework starts earning its keep. |
| 4 | Langfuse | Prompt management or cost tracking becomes worth a four-service stack. The swap is one environment variable, since both speak OTLP. |
| 5 | Hosted eval judge in CI | The fixture set grows large enough that running `make eval` locally becomes a chore. |

## 6. What to do next, concretely

1. [M1_repo_restructure.md](M1_repo_restructure.md) — **done 2026-08-15**.
2. Complete [M2_phi_redaction.md](M2_phi_redaction.md), then [M3_execution_tracing.md](M3_execution_tracing.md).
3. Start a fresh brainstorm → plan cycle for **M4 only**, using `docs/epic1_grounded_qa/M4_grounded_answering.md` as the contract and §3.1 and §3.2 above as the deltas.
4. Repeat per module, in the §2 order.
