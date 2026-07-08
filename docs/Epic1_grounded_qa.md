# TaRa Health — Epic 1: Grounded Q&A *(former Phase 1)*

- **Epic 1 scope:** grounded, read-only Q&A over the user's documents.
- **Explicitly out of scope for Epic 1:** any agentic *action* (no calendar, email, pharmacy, delivery).
- Epic 1 builds the foundation — ingestion, retrieval, grounded answering, citations, and the safety layer — that every later epic depends on.
- The action seam itself is designed in [Epic2_first_actions.md](Epic2_first_actions.md).
- **Status:** Draft v0.3 (content), restructured Phase→Epic / sections→Modules 2026-07-07.
- **Last updated:** 2026-07-07.
- **Modules in this epic:** M1 ingestion_pipeline · M2 local_storage · M3 retrieval · M4 grounded_answering · M5 safety · M6 ocr · M7 classification · M8 eval_harness.

### Changelog v0.2 → v0.3

- Verification pass (architecture / clinical-safety / stack reviews) tightened the design in place; design and contract changes only, no behavior implemented:
  1. Required emergency taxonomy + fail-closed safety decision rule (M5).
  2. Citation provenance carries char spans end-to-end (M1, M4, data model).
  3. Embedding model/dimension validation + a re-index path (M2).
  4. Transactional ingestion with a defined failure path (M1).
  5. Buildable document-purge contract (M2, Privacy).
  6. Concrete document-type-filtered retrieval contract with abstention (M3, M7).
  7. Reconciled encryption-at-rest posture incl. blobs (M2, Privacy).
  8. Answer post-processing order + numeric grounding (M4).
  9. Audit-log writer + egress record (data model, Privacy).
  10. PHI-safe request handling (Privacy).

---

## 1. Goals

1. User uploads health/insurance documents; TaRa parses and indexes them locally.
2. User asks natural-language questions; **Tara** answers using *only* what the documents support, and **cites the source** (document + page).
3. When a document doesn't contain the answer, Tara says so rather than guessing — and never states a coverage amount or lab value that isn't grounded in a cited excerpt.
4. The **safety layer** runs on every health query (emergency detection + framing).
5. Everything is **local-first** and **single-profile**.

- **Success bar:**
  - A coverage question ("what's my specialist copay?") returns the correct number with a citation to the right page.
  - A missing-info question returns an honest "I don't see that in your documents."

---

## 2. High-level architecture

```
                 ┌─────────────────────────────────────────────┐
   Upload  ─────▶│              INGESTION PIPELINE              │
                 │  detect type → extract text (PDF/OCR) →      │
                 │  classify doc → chunk → embed → index        │
                 │  (single transaction; blob cleaned on fail)  │
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │           LOCAL STORAGE (on device)          │
                 │  • file blob store (original docs)           │
                 │  • metadata DB (docs, chunks, pages, audit)  │
                 │  • vector index (chunk embeddings)           │
                 └───────────────┬─────────────────────────────┘
                                 ▲
   Question ──▶ ┌────────────────┴──────────────┐
                │   SAFETY / TRIAGE (pre-check)  │ ── emergency? ──▶ escalate, stop
                │   (fail-closed; over-triggers) │
                └────────────────┬──────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  RETRIEVAL: embed query → vector search +    │
                 │  doc-type filter → (rerank) → assemble ctx   │
                 │  → abstain if best score below threshold     │
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  ANSWERING LLM (grounding + citation prompt) │
                 │  → map chunk_id→citation → numeric grounding │
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  SAFETY (append-only framing) → cited answer │
                 │  → write audit record (incl. model route)    │
                 └─────────────────────────────────────────────┘
```

### Key flows

- **Ingestion (sequence — M1):**

```
upload → validate (size, extension) → detect type → extract text (+page/char spans)
       → classify doc → chunk (deterministic ids, page-bounded)
       → content-hash dedup check (reject or replace; M1)
       → BEGIN: write documents + chunks rows  ─┐
       → write vectors (keyed by chunk_id)       │ one logical unit; M1
       → COMMIT, status='indexed'  ──────────────┘
       → confirm "Indexed N pages from <filename>"
   (on failure: rollback rows, delete orphan blob, mark indexing_failed)
```

- **Query (sequence — M3 → M4 → M5):**

```
question (in request BODY, not URL; Privacy) → SAFETY pre-check (fail-closed)
            ├─ emergency OR check failed? → escalation message, STOP
            └─ otherwise ↓
         → embed query → infer doc_type → retrieve (post-filtered)
            ├─ best score < threshold? → "I don't see that in your documents"
            └─ otherwise ↓
         → assemble context (token-budgeted)
         → answering LLM (grounded + cite)
         → map chunk_id→Citation → numeric-grounding check → append framing
         → write audit record (safety_flag, model_route, retrieved_chunk_ids)
         → return cited answer (+ "open source page" links to local docs)
```

---

## M1 — ingestion_pipeline

- **Purpose:** turn an uploaded file into indexed, citable chunks — detect → extract(+spans) → chunk → embed → index, as one transactional unit.

### Design / contract

- **File-type detection + upload validation (boundary):**
  - Accept PDF and image formats; branch on whether the PDF has a real text layer vs. is a scan.
  - Validate at this boundary: enforce a maximum upload size (`TARA_MAX_UPLOAD_BYTES`, default 50 MB) and an allowed-extension whitelist (`.pdf, .png, .jpg, .jpeg, .tiff`) **before any processing** — a malformed or oversized upload fails fast rather than OOM-ing the process.
- **Text extraction (native-text PDFs):**
  - Extract text + per-word/character positions and page numbers.
  - **Char spans must index into a single canonical text representation** (the exact string stored on the chunk), not a reflowed/markdown rendering.
  - Practically: use a raw-position API (e.g. PyMuPDF `get_text("words"/"rawdict")`), not a markdown exporter — a markdown layer rearranges characters (headers, table wrapping) and breaks the offset↔source mapping citations depend on.
  - Preserve **page number** and **character span** for every extracted piece — this is what makes citations possible later.
  - Scanned PDFs and images take the OCR path — see **M6**.
  - Document classification happens in this pipeline but is specified in **M7**.
- **Chunking:**
  - Split text into retrievable chunks (e.g., ~500–1000 tokens with overlap).
  - Chunk *structurally* where possible — insurance docs have tables and sections; lab reports have result tables.
  - Each chunk stores `{chunk_id, doc_id, page, char_start, char_end, text}`.
  - **Chunk IDs are deterministic:** `chunk_id = f"{doc_id}:{page}:{char_start}"` — stable IDs keep historical citations in the audit log valid and make re-ingest idempotent.
  - **A chunk never crosses a page boundary:** `Chunk.page` is a single page, so any chunk that would span pages is split at the boundary — `(page, char_start, char_end)` stays well-defined and citable.
- **Embedding + indexing:**
  - Embed each chunk and store the vector in the local index.
  - *Local-first preference:* on-device embedding model, so document text never leaves the device during indexing.
  - **Embeddings stay local in every `TARA_MODEL_MODE`, including `hosted`** — only the answering step may egress (M4).
  - The embedding dimension is validated against the model at startup (M2).
- **Idempotency & re-ingest:**
  - On upload, compute a content hash of the file bytes; store it on the document row.
  - If a document with the same hash already exists, do **not** create a duplicate — default is **reject-as-duplicate** (report "already indexed").
  - `replace=true` upload: delete the prior document (via the purge contract, M2) and re-index in a single transaction.
  - Prevents duplicate documents/chunks/vectors and dangling citations.
- **Failure handling & transactionality:** ingestion writes to three stores; a crash mid-way must not leave them inconsistent. Ordering and rules:
  1. Write the blob to disk first; record its path.
  2. Insert the `documents` row and all `chunks` rows in **one DB transaction** (`status='indexing'`).
  3. Insert vectors keyed by `chunk_id`.
  4. On success, set `status='indexed'` and confirm "Indexed N pages from <filename>".
  - On any exception: roll back the DB transaction, delete the orphan blob, and — if the doc row was already committed — mark `status='indexing_failed'` rather than leaving an unknown state.
  - A document not in `status='indexed'` is invisible to retrieval.

### Data-model deltas

- Owns the `documents.content_hash` (dedup) and `documents.status` (`indexing | indexed | indexing_failed`) semantics; schema lives in M2.

### Tests / acceptance

- Fixture PDF ingests end to end; chunks carry correct `(page, char_start, char_end)` into the canonical text.
- Re-ingest of the same file is rejected as duplicate; `replace=true` swaps atomically.
- Induced failure mid-pipeline leaves no orphan blob, no partial rows, and the document invisible to retrieval.

---

## M2 — local_storage

- **Purpose:** the on-device state plane — SQLite + sqlite-vec, schema, purge, encryption, and embedding-index integrity.

### Design / contract

- **Three stores, all on device:**
  - **Blob store:** the original uploaded files (for display + re-processing).
  - **Metadata DB:** documents, chunks, page map, classification, timestamps, the query/audit log, and an index-metadata row (embedding model + dimension).
  - **Vector index:** chunk embeddings for similarity search.
- **Decision — SQLite + sqlite-vec for both metadata DB and vector index:**
  - One portable file under `TARA_DATA_DIR`, with the original blobs alongside.
  - LanceDB and Chroma were considered; SQLite won for keeping everything in a single portable file — backup/migration is "copy the file" — which best fits local-first.
  - The vector table is created separately from the relational schema because it needs the sqlite-vec extension loaded; it is created on a separate connection against the same db file (not the same connection object).
  - Connections opened for request handlers use `check_same_thread=False` because FastAPI runs sync handlers in a threadpool.
  - `connect_db()` sets `PRAGMA foreign_keys = ON` so declared cascades actually fire.
- **Embedding model/dimension integrity:**
  - `TARA_EMBED_DIM` must match `TARA_EMBED_MODEL`; the `vec0` table bakes the dimension in at creation, so a later model change silently corrupts search. Therefore:
    1. At startup, validate `embed_dim == model.get_sentence_embedding_dimension()`; fail loudly on mismatch.
    2. Persist the embedding model name + dimension as an index-metadata row when the store is first created.
    3. If `TARA_EMBED_MODEL` changes after indexing, that is a **re-index migration**: drop and rebuild the vector table and re-embed all chunks.
  - The mismatch is detected by comparing config against the stored index-metadata row; the app refuses to serve queries against a stale index rather than returning garbage distances.
- **Document purge (buildable delete):**
  - The `vec_chunks` virtual table has no foreign-key relationship to `chunks`, so deletion is **not** automatic.
  - `purge_document(doc_id)`, in one transaction, must:
    1. Delete the `vec_chunks` rows for the document's `chunk_id`s explicitly.
    2. Delete `chunks` (the `documents`→`chunks` cascade fires now that `foreign_keys` is ON).
    3. Delete the `documents` row.
    4. Delete the blob file.
    5. Delete or redact related `queries` rows per the retention policy (see Privacy).
  - Order steps so a failure leaves no "document gone but vectors remain" state.
- **Encryption at rest:**
  - SQLCipher (optional `[encryption]` extra) encrypts the DB file when `TARA_DB_KEY` is set.
  - **Blobs are the richest PHI and are not covered by SQLCipher** — when `TARA_DB_KEY` is set, blob files are encrypted with the same key (AES-GCM).
  - Default install (no key) stores both DB and blobs **unencrypted** — see the Privacy section for the reconciled posture and residual-risk statement.

### Data-model (base sketch for the epic)

```
documents
  doc_id          (pk)
  filename
  doc_type        (insurance_policy | lab_report | eob | bill | ...)
  content_hash    (for re-ingest dedup; M1)
  status          (indexing | indexed | indexing_failed; M1)
  uploaded_at     (ISO-8601 UTC string; use datetime.now(timezone.utc))
  page_count

chunks
  chunk_id        (pk)  -- deterministic: "{doc_id}:{page}:{char_start}"
  doc_id          (fk -> documents, ON DELETE CASCADE)
  page
  char_start
  char_end
  text
  embedding       (vector; stored in the vec_chunks vec0 table, keyed by chunk_id)

index_meta                       -- guards model/dim integrity (M2)
  embed_model
  embed_dim
  created_at

queries            (audit/eval; written on every answered query)
  query_id        (pk)
  question
  retrieved_chunk_ids            -- needed by the M8 retrieval eval
  answer
  citations                      -- chunk_id + page + char span
  safety_flag     (none | emergency)
  model_route     (local | hosted)   -- so PHI egress is auditable (Privacy)
  created_at
```

- A runtime **`Citation`** maps a cited `chunk_id` to `{filename, page, char_start, char_end, snippet}` for display (M4).

### Tests / acceptance

- Schema builds; FK cascade fires on document delete.
- Embed model/dim mismatch vs `index_meta` refuses to serve queries.
- `purge_document` leaves no rows, vectors, or blob behind, in any failure order.

---

## M3 — retrieval

- **Purpose:** embed the query, filter by inferred document type, post-filter KNN results, abstain when weak, and assemble token-budgeted context.

### Design / contract

1. Embed the query (same on-device model as indexing).
2. **Infer document type** from the question (a small rule/LLM step):
   - cost/coverage → `insurance_policy`/`benefits_summary`/`eob`/`bill`; "my results" → `lab_report`; medication → `prescription`; etc.
   - The inferred type(s) are translated to the matching `doc_id`s via a `documents` lookup.
   - Classification of documents themselves is M7.
3. **Vector search with a document-type filter:**
   - sqlite-vec `vec0` does **not** support an arbitrary `WHERE` on non-vector columns inside the KNN query.
   - Contract is therefore **post-filtering**: run KNN for `k * multiplier`, then keep the first `k` whose `doc_id` is in the allowed set (correct and cheap at single-user scale).
   - Falls back to unfiltered search if type inference is low-confidence.
4. Optional rerank for precision.
5. **Abstention guard:**
   - If the best retrieval score is below a configured threshold, treat the question as unsupported — the answerer should decline ("I don't see that in your documents") rather than stretch weak context.
   - Complements the prompt-level honesty rule (M4).
6. Assemble the top-k chunks into context, each tagged with its `chunk_id` and source (doc name + page):
   - **Cap the assembled context to a token budget** sized to the answering model's window (`qwen3:8b` is small).
   - Reduce `k` before overflowing rather than truncating mid-chunk.

### Data-model deltas

- None (reads `documents`/`chunks`/`vec_chunks`; writes nothing).

### Tests / acceptance

- Curated Q→expected-chunk pairs retrieve the right chunk (top-k hit rate; measured in M8 via `queries.retrieved_chunk_ids`).
- Below-threshold best score triggers abstention.
- Post-filter keeps only allowed `doc_id`s; low-confidence inference falls back to unfiltered.

---

## M4 — grounded_answering

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

---

## M5 — safety

- **Purpose:** emergency pre-check (fail-closed, before the answering model) + append-only framing post-check, with a 100%-recall release gate.

### Design / contract

- **Placement & independence:**
  - Runs **before** the answering LLM on any health-related query.
  - Intentionally separate from the answering prompt so it can't be "reasoned away" by the main model and can be tested independently.
  - **Biased toward over-triggering:** a single missed emergency is far worse than many false alarms.
- **Emergency detection (pre-check) — two layers, fixed decision rule:**
  - A fast **keyword/pattern layer** over a red-flag list.
  - A **lightweight LLM confirmation layer** — **not optional**: it is the safety net for phrasings, misspellings, and negations the keyword list misses.
  - If Epic 1 ships without the LLM layer, the design must explicitly scope the safety net to English keyword matching and record that limitation; the default is to include the LLM layer.
- **Required minimum emergency taxonomy** (the gate for the M8 safety-recall eval — a required floor, not an "etc." list):
  - Chest pain / pressure.
  - Stroke signs (face droop, slurred speech, sudden one-sided weakness or numbness, "FAST").
  - Difficulty breathing / choking.
  - Anaphylaxis / throat or tongue swelling.
  - Severe bleeding.
  - Suicidal ideation and self-harm (including variants: "kill myself", "end it", "no reason to live", "hurt myself").
  - Overdose / poisoning / ingestion.
  - Seizure.
  - Loss of consciousness / unresponsive / fainting.
  - Sepsis signs (high fever + confusion).
  - Meningitis signs (stiff neck + fever).
  - Pregnancy emergencies (heavy vaginal bleeding, no fetal movement).
  - "Worst headache of my life."
  - Severe abdominal pain.
- **Decision rule (fail-closed):**
  - Escalate if the keyword layer **OR** the LLM layer flags; the LLM may **never downgrade** a keyword hit.
  - If the pre-check cannot complete (LLM down, classifier error, timeout), **fail toward escalation** — do not answer; show the conservative safety message.
  - When escalating, always return a **non-empty, locale-aware escalation message** (emergency number is configurable; 911 is US-specific).
  - Tara does not give self-care advice on the emergency path; it directs the user to emergency services and stops.
- **Framing (post-check):**
  - Ensures the final answer is framed as general information, includes a professional-care nudge for anything serious or persistent, and avoids guaranteed outcomes/timelines.
  - **Append-only and non-destructive** — may add disclaimers but must not edit the grounded facts or the citation markers (ordering in M4).
  - If framing fails, return the grounded answer with a default static disclaimer rather than erroring.

### Data-model deltas

- Writes `queries.safety_flag` (`none | emergency`).

### Tests / acceptance

- **Safety recall is a release gate, not a metric:** a battery covering the full taxonomy above; the pre-check must catch them — target 100% recall on the taxonomy fixture before this module is considered done.
- Favor over-triggering; track the false-positive rate against a ceiling.
- Pre-check failure (LLM down/timeout) escalates rather than answers.

---

## M6 — ocr

- **Purpose:** the scanned-document / image extraction path — OCR with page-granularity citations.

### Design / contract

- Scanned PDFs and images: OCR instead of native extraction (branch decided in M1 detection).
- *Local-first preference:* on-device OCR (Tesseract) or a local vision model, so PHI doesn't leave the device.
- Keep a cloud-OCR option behind an explicit opt-in for hard cases.
- **OCR caveat:** OCR char offsets do not map to pixel coordinates, so citations on scanned docs resolve to **page granularity only** (no in-page highlight) — see M4.
- Downstream (chunking, embedding, indexing, retrieval, answering) is unchanged from M1/M3/M4.

### Data-model deltas

- None (same `documents`/`chunks` rows; spans are OCR-text offsets).

### Tests / acceptance

- **OCR fidelity:** spot-check extracted numbers on scanned lab reports / EOBs — a misread digit in a copay or result is a real harm (measured in M8).
- Citations on OCR'd docs resolve to the correct page.

---

## M7 — classification

- **Purpose:** tag each document with a type and use inferred types to filter retrieval.

### Design / contract

- **Document classification (at ingest, M1 pipeline step):**
  - Tag each document: `insurance_policy`, `benefits_summary`, `eob`, `bill`, `lab_report`, `prescription`, `after_visit_summary`, `other`.
  - A small LLM call or a lightweight classifier is fine.
- **Powers metadata-filtered retrieval:** question-side type inference and the post-filter contract are specified in M3 (steps 2–3); this module supplies the document-side tags.
- Falls back gracefully: untyped/low-confidence docs remain retrievable via M3's unfiltered fallback.

### Data-model deltas

- Populates `documents.doc_type` (closed set above).

### Tests / acceptance

- Each fixture doc type classifies correctly.
- Type-filtered retrieval returns only chunks from allowed `doc_id`s; unfiltered fallback engages on low confidence.

---

## M8 — eval_harness

- **Purpose:** measurable Epic-1 quality — retrieval, citation, value accuracy, honesty, safety recall, OCR fidelity — against a fixture set of sample documents.

### Design / contract (metrics)

- **Retrieval accuracy:** curated Q→expected-chunk pairs across each doc type; measure top-k hit rate (uses `queries.retrieved_chunk_ids`).
- **Citation correctness:** does the cited page actually contain the stated fact?
- **Value/numeric accuracy:** for answerable cost/coverage/lab questions, does the stated **number** match ground truth — not just the citation page? A wrong-but-cited figure is a higher-harm failure than a refusal.
- **Hallucination / honesty:** ask questions the docs *can't* answer; the system must decline (prompt rule + the M3 abstention guard), not invent.
- **Safety recall (release gate):** the full M5 emergency taxonomy battery — gates M5, not deferred to this module's build step.
- **OCR fidelity:** spot-check extracted numbers on scanned lab reports / EOBs (M6).

### Data-model deltas

- None (reads the `queries` audit log).

### Tests / acceptance

- Harness runs over the fixture set and reports all six metric groups.
- Also settles OPEN_QUESTIONS.md #1: measure citation correctness and honesty for `local` vs `hosted` and pick the default with evidence.

---

## Cross-cutting: Safety, Privacy & security

- **Safety (M5) wraps everything:** pre-check before answering; append-only framing after; fail-closed on error.
- **Storage on device:** all three stores live on the device (M2).
- **Encryption at rest — reconciled posture:**
  - Encryption is **available and off by default**: setting `TARA_DB_KEY` encrypts the DB (SQLCipher) **and** the blob files (AES-GCM; M2).
  - The default install runs unencrypted for out-of-the-box simplicity; this residual risk is stated deliberately rather than implied as "always encrypted."
  - Enabling encryption is one config value plus the `[encryption]` extra.
- **On-device by default:** OCR + embeddings run on-device; cloud OCR only behind explicit opt-in; embeddings never egress, even in `hosted` mode.
- **Minimal egress:**
  - Send only the assembled context + question to any hosted model — never the whole corpus — and only when `model_mode` opts in.
  - `queries.model_route` records whether a given answer used the local or hosted model, so the user can audit what left the device.
- **PHI-safe request handling:** the question is sent in the **request body**, not as a URL/query parameter, so health text doesn't land in access logs or browser history.
- **Audit log:** every answered query is logged locally (question, answer, citations, safety flag, model route) so the user can see what was asked/answered and what egressed.
- **Delete is real and complete:**
  - `purge_document(doc_id)` removes the blob, chunks, and vectors (M2).
  - The audit log can itself contain PHI; retention policy: document deletion redacts/links its `queries` rows, and a separate "clear history" purges the audit log.
  - "Delete purges everything" is therefore literally true.

---

## What this epic excludes

- No actions of any kind (calendar, email, reminders, pharmacy, delivery).
- No external integrations / MCP servers yet.
- No proactive behavior — Tara only responds when asked.
- These arrive in Epics 2–4 (see PRD §11), building on the retrieval + safety foundation established here; the action seam is designed in [Epic2_first_actions.md](Epic2_first_actions.md).

---

## Build order (module sequence)

1. **M1 (native-text path) + M2:** ingestion for native-text PDFs → chunk (deterministic ids) → local index, with the transactional write path and embed-dim validation; get retrieval (M3, unfiltered + abstention) working first.
2. **M4:** answering LLM with grounding + "decline if unsupported" + the M3 abstention guard.
3. **M4 citations:** chunk → page + char-span mapping surfaced in the UI.
4. **M5:** safety pre-check (emergency detection, fail-closed) + post-check framing — **and the safety-recall fixture alongside it**, gating this step; don't defer safety measurement to step 7.
5. **M6:** OCR path for scanned docs + images (page-level citations).
6. **M7:** document classification + filtered retrieval (post-filter contract, M3).
7. **M8:** full eval harness — retrieval/citation/value-accuracy/honesty/OCR — against the fixture set (safety recall already gated at step 4).

---

## Repository layout

- How the design maps onto the code tree:

```
tara-health/
├── pyproject.toml               # deps wired to the chosen stack
├── .env.example                 # config: model mode, paths, models, api key, limits
├── src/tara/
│   │  # -- shared kernel (importable by every layer; imports nothing above it) --
│   ├── config.py                # central settings (paths, model mode, embed model, api key, limits, timeouts)
│   ├── data_models.py           # Document, Chunk, Citation, DocType (M2 sketch)
│   ├── app_errors.py            # UploadError, IngestionError, IndexMismatchError → HTTP mapping in web_app
│   ├── upload_validation.py     # upload boundary checks (M1)
│   │  # -- capabilities: the verbs Tara can perform --
│   ├── document_ingestion/      # source detection → text extraction(+spans) → classification → chunking → pipeline (M1, M6, M7)
│   ├── semantic_search/         # text embedding + chunk retrieval w/ abstention (M1, M3)
│   ├── question_answering/      # answer prompts + question answerer — full query flow incl. numeric grounding (M4)
│   │  # -- planes: what every capability stands on --
│   ├── llm_clients/             # model plane: LLMClient interface + ollama/openai-compatible/hosted clients (M4)
│   ├── local_data_stores/       # state plane (M2): db_connection + db_schema + document_records +
│   │                            #   chunk_records + embedding_index_meta + vector_index + blob_store +
│   │                            #   document_purge — ALL SQL lives here, callers use record functions
│   ├── safety_checks/           # control plane: emergency triage (pre-check, fail-closed) + answer framing (post-check) (M5)
│   │  # -- surface --
│   ├── web_app.py               # FastAPI: /upload, /ask (body), / (UI); `tara` entry point; composition root
│   └── web_ui/                  # templates + static for the local UI
│   # reserved for Epic 2 (created when the code exists): agent_orchestration/, agent_tools/
├── scripts/initialize_data_stores.py   # create schema + vector table + index_meta
└── tests/                       # MIRRORS src/tara: one test module per source module
                                 #   (tests/<package>/test_<module>.py); behavior_evals/ lands with M8
```

- **Import direction (enforceable rule):** kernel ← planes ← capabilities ← safety/agent packages ← web_app.
- Capabilities never import each other, except `question_answering → semantic_search` and `→ safety_checks` (the query flow).
- Every stub marks its intent with a docstring and a `TODO` describing its contract; when implementing, honor the contracts above (the v0.3 changes tighten several stub contracts — update the docstrings to match as each is built).
- Quickstart commands live in the README and `CLAUDE.md`; build order is the section above.
