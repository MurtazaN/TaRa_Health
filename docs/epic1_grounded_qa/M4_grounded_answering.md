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
