# Epic 1 · M4 — grounded_answering

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** consumes [M3](M3_retrieval.md) context; maps citations via [M1](M1_ingestion_pipeline.md) provenance; applies [M5](M5_safety.md) framing as post-processing step 3; writes the `queries` audit row ([M2](M2_local_storage.md)).

---

- **Purpose:** answer only from retrieved chunks, cite them, decline when unsupported, and enforce numeric grounding after the model returns.

### Design / contract

- **The model must:**
  - Answer **only** from the provided chunks.
  - **Cite** the chunk(s) it used (the app maps `chunk_id → document + page + char span` for display).
  - Say **"I don't see that in your documents"** when the context doesn't support an answer — never fabricate coverage numbers, results, or policy terms.
- **Post-processing order (fixed), on one canonical answer string:**
  1. Parse the `[chunk_id]` markers the model emitted; map each to a `Citation`.
  2. **Numeric-grounding check:** every monetary amount / lab value / policy number stated in the answer must appear in the text of a cited chunk; an ungrounded figure is dropped or the answer is downgraded to an abstention — a confidently wrong copay with a citation is more dangerous than a refusal.
  3. Apply append-only safety framing (M5).
  - This ordering guarantees the user-visible text, the citation markers, and the framing never diverge.
- **Citation provenance carries the span:**
  - A `Citation` carries `{chunk_id, filename, page, char_start, char_end, snippet}` — not just `page`.
  - The char span is what lets the UI open the source page and highlight the cited text.
  - On OCR'd scans, char spans aren't pixel-mappable, so the citation resolves to page level (M6).
- **Privacy seam — model routing (config, never code):**
  - This is the main point where data may leave the device (if using a hosted model).
  - **Decision:** `TARA_MODEL_MODE` is `local` / `hosted` / `hybrid`, defaulting to `local` (Ollama); the hosted path uses Anthropic; local-vs-hosted is never a code change.
  - **All** provider settings live in `Settings`, including `TARA_ANTHROPIC_API_KEY`; a startup validator fails loudly when `model_mode in (hosted, hybrid)` and the key is missing — no module hard-codes an env lookup.
  - **Superseded by Epic 0 M5:** this routing decision (direct Anthropic key) did not ship. Hosted generation is `generation_mode` (`local` / `agent_platform` / `hybrid`) via `AgentPlatformClient` on Google Cloud Agent Platform, authenticated with Application Default Credentials — **no provider API key**. See [`docs/epic0_foundation/M4_epic1_handoff.md` §3.1](../epic0_foundation/M4_epic1_handoff.md#31-m4--grounded-answering) and [`docs/epic0_foundation/M5_model_backends.md`](../epic0_foundation/M5_model_backends.md).
  - Retrieval and indexing stay local regardless; only the minimal assembled context + question ever go to the model.
  - The LLM client is created once with a configured timeout (`TARA_LLM_TIMEOUT_SECONDS`) so a stalled model can't hang the request indefinitely.
  - What remains open is empirical — whether the local model's quality suffices for grounded reasoning (OPEN_QUESTIONS.md #1, settled via M8).

### Answering prompt (sketch)

> You are Tara, a personal health & insurance assistant. Answer the user's question using ONLY the document excerpts provided below. Each excerpt has an ID. When you state a fact, cite the excerpt ID(s) it came from. If the excerpts do not contain the answer, say you don't see it in their documents — do not guess or invent coverage amounts, results, or policy terms. Frame any health information as general information, not a diagnosis, and suggest professional care for anything serious or persistent.
>
> [excerpts: {chunk_id, source, page, text} ...]
> [question]

- Prompt notes:
  - Keep the safety pre-check a *separate* call/stage — do not rely on this prompt alone for emergency handling (M5).
  - The app, not the prompt, enforces the hard guarantees: citation mapping → numeric-grounding check → append-only framing run **after** the model returns, in that order.
  - The prompt requests good behavior; the post-checks enforce it.

### Data-model deltas

- Runtime `Citation` object (see M2 sketch); writes the `queries` audit row on every answered query.

### Tests / acceptance

- Cited page actually contains the stated fact.
- For answerable cost/coverage/lab questions, the stated **number** matches ground truth (not just the citation page).
- Questions the docs can't answer are declined, never invented.
- No ungrounded number survives post-processing.

---

## As built — 2026-08-26

Built to [`M4_grounded_answering_plan.md`](M4_grounded_answering_plan.md) in ten tasks; the code is the authority where it and the plan differ.

### Decisions taken with the repository owner

| # | Decision | Consequence |
|---|---|---|
| 1 | M4 implements a keyword-only `screen_for_emergency()` and a static `apply_safety_framing()` | M4 becomes runnable end to end. The hazard classifier, the custom taxonomy and the safety-recall fixture remain M5 work. |
| 2 | The M3 retrieval reranker is deferred out of M4 | `chunk_reranker.py`, the four `TARA_RERANK_*` settings and the second abstention route get their own plan cycle. Recorded in [`../epic0_foundation/M4_epic1_handoff.md`](../epic0_foundation/M4_epic1_handoff.md) §6 step 3. |
| 3 | An ungrounded figure abstains the whole answer | No answer text is ever edited by the app. The acceptance criterion becomes one assertion. |
| 4 | Structured output uses each backend's native JSON-schema facility, not Instructor | Deviates from the handoff document's §3.1 row 1. No new dependency, and nothing to remove when LangGraph lands (handoff §4.3 row 3). |
| 5 | Egress redaction happens inside `AgentPlatformClient`, not in the answerer | One audited chokepoint that no future caller can forget, mirroring why `traced_span()` is the only span-creation path. |
| 6 | `EGRESS_REDACTED_ENTITIES` lives in `phi_redaction.py` beside `REDACTED_ENTITIES` | The difference between the two lists is visible on one screen. |

### Suite at the end of the module

- **311 passed, 2 skipped, 15 xfailed** — up from the pre-M4 baseline of 243 passed, 4 skipped, 16 xfailed.
- `make lint` and `make typecheck` clean.
- The two skips are the real-embedding-model test and the new opt-in LM Studio constrained-decoding probe (`TARA_TEST_REAL_LOCAL_MODEL=1` to run it).
- The 15 remaining xfails are all PHI-recall cases; the web-app xfail of Epic 0 §9.1 row 9 flipped to a genuine pass here.

### Plan defects found and fixed during implementation

| # | Defect | Fix |
|---|---|---|
| 1 | `Sequence` was imported from the deprecated `typing` alias, which fails the ruff lint gate | Corrected to `collections.abc`. |
| 2 | `_normalise_figure` stripped the percent sign, so an answer claiming "30%" was grounded by the unrelated "30" in "30-day wait" — fail-open in the check whose whole purpose is catching wrong figures | The percent sign is now part of the comparison key. The currency symbol is still stripped, so "$40" grounds against a bare "40.00". |
| 3 | Adding a second method to the `LLMClient` protocol broke typecheck, because `AgentPlatformClient` only gained its implementation in Task 4 | Resolved with a temporary suppression that Task 4 deletes; the plan now carries that deletion as an explicit step. |
| 4 | The plan built the structured chat model outside the retry wrapper, so a credentials failure — which surfaces at construction — escaped the error taxonomy on the structured path only | Construction now happens inside the retried callable, and a test pins it. |
| 5 | The numeric-grounding check was originally given `citation.snippet`, truncated to 240 characters for display, so a figure further into a cited chunk would abstain a correct answer | It now receives the full cited chunk text. Caught during plan self-review, before implementation. |

### Deviation in the acceptance fixture

- The plan's acceptance fixture ingests all four plan facts onto one page, and `offline_ingest_env`'s deterministic bag-of-words embedder scored the copay question against that four-fact chunk at **0.236**, under the real `abstain_threshold` of 0.25.
- Effect if left alone: criterion 1 failed at retrieval, and criterion 4 passed for the wrong reason — it abstained before the numeric check ever ran.
- Fix: `tests/question_answering/test_m4_acceptance.py`'s `ingested_plan` fixture pins `TARA_ABSTAIN_THRESHOLD=0.1` for these four tests only. No assertion was changed.
- Why this and not a reworded fixture: the fake embedder's cosine scale is not the real model's — the same mismatch already documented in `tests/test_web_app.py` — and tuning fixture text to clear a threshold is fragile against both a threshold change and a chunking change. Retrieval, storage, the vector index and the whole post-retrieval flow stay real; the off-topic question still scores 0.0 and still abstains. Calibrating the real threshold is M8.
