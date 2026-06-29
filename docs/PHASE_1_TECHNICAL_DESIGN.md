 # TaRa Health — Phase 1 Technical Design

**Phase 1 scope:** Grounded, read-only Q&A over the user's documents.
**Explicitly out of scope for Phase 1:** any agentic *action* (no calendar, email,
pharmacy, delivery). Phase 1 builds the foundation — ingestion, retrieval,
grounded answering, citations, and the safety layer — that every later phase
depends on. The action seam itself is designed in
[PHASE_2_TECHNICAL_DESIGN.md](PHASE_2_TECHNICAL_DESIGN.md).

**Status:** Draft v0.3
**Last updated:** 2026-06-28

> **Changelog v0.2 → v0.3.** Verification pass (architecture / clinical-safety /
> stack reviews) tightened the design in place. Material changes: a required
> emergency taxonomy and a fail-closed safety decision rule (§3.3); citation
> provenance now carries char spans end-to-end (§3.5, §4); embedding
> model/dimension validation and a re-index path (§3.2); transactional ingestion
> with a defined failure path (§3.1f, §5.1); a buildable document-purge contract
> (§3.2, §7); a concrete document-type-filtered retrieval contract with abstention
> (§3.4); reconciled encryption-at-rest posture incl. blobs (§7); answer
> post-processing order + numeric grounding (§3.5, §6); an audit-log writer and
> egress record (§4, §7); and PHI-safe request handling (§7). These are design and
> contract changes; no behavior was implemented.

---

## 1. Goals

1. User uploads health/insurance documents; TaRa parses and indexes them locally.
2. User asks natural-language questions; **Tara** answers using *only* what the
   documents support, and **cites the source** (document + page).
3. When a document doesn't contain the answer, Tara says so rather than guessing —
   and never states a coverage amount or lab value that isn't grounded in a cited
   excerpt.
4. The **safety layer** runs on every health query (emergency detection + framing).
5. Everything is **local-first** and **single-profile**.

Success bar: a coverage question ("what's my specialist copay?") returns the
correct number with a citation to the right page, and a missing-info question
returns an honest "I don't see that in your documents."

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

---

## 3. Components

### 3.1 Ingestion pipeline

**a. File-type detection.** Accept PDF and image formats. Branch on whether the
PDF has a real text layer vs. is a scan. Validate the file at this boundary:
enforce a maximum upload size (`TARA_MAX_UPLOAD_BYTES`, default 50 MB) and an
allowed-extension whitelist (`.pdf, .png, .jpg, .jpeg, .tiff`) before any
processing, so a malformed or oversized upload fails fast rather than OOM-ing the
process.

**b. Text extraction.**
- Native-text PDFs: extract text + per-word/character positions and page numbers.
  **Char spans must index into a single canonical text representation** (the exact
  string stored on the chunk), not a reflowed/markdown rendering. Practically this
  means using a raw-position API (e.g. PyMuPDF `get_text("words"/"rawdict")`)
  rather than a markdown exporter — a markdown layer rearranges characters (headers,
  table wrapping) and breaks the offset↔source mapping that citations depend on.
- Scanned PDFs and images: OCR. *Local-first preference:* on-device OCR (Tesseract)
  or a local vision model, so PHI doesn't leave the device. Keep a cloud-OCR option
  behind an explicit opt-in for hard cases. **OCR caveat:** OCR char offsets do not
  map to pixel coordinates, so citations on scanned docs resolve to **page
  granularity only** (no in-page highlight) — see §3.5.
- Preserve **page number** and **character span** for every extracted piece — this
  is what makes citations possible later.

**c. Document classification.** Tag each document: `insurance_policy`,
`benefits_summary`, `eob`, `bill`, `lab_report`, `prescription`,
`after_visit_summary`, `other`. A small LLM call or a lightweight classifier is
fine. Classification powers metadata-filtered retrieval (§3.4).

**d. Chunking.** Split text into retrievable chunks (e.g., ~500–1000 tokens with
overlap), but chunk *structurally* where possible — insurance docs have tables and
sections; lab reports have result tables. Each chunk stores
`{chunk_id, doc_id, page, char_start, char_end, text}`.
- **Chunk IDs are deterministic:** `chunk_id = f"{doc_id}:{page}:{char_start}"`.
  Stable IDs keep historical citations in the audit log valid and make re-ingest
  idempotent (§3.1f).
- **A chunk never crosses a page boundary.** Because `Chunk.page` is a single page,
  any chunk that would span pages is split at the boundary so `(page, char_start,
  char_end)` stays well-defined and citable.

**e. Embedding + indexing.** Embed each chunk and store the vector in the local
index. *Local-first preference:* on-device embedding model so document text never
leaves the device during indexing — **embeddings stay local in every
`TARA_MODEL_MODE`, including `hosted`** (only the answering step may egress; see
§3.5). The embedding dimension is validated against the model at startup (§3.2).

**f. Idempotency & re-ingest.** On upload, compute a content hash of the file bytes
and store it on the document row. If a document with the same hash already exists,
the pipeline does not create a duplicate — the default is **reject-as-duplicate**
(report "already indexed"); a `replace=true` upload deletes the prior document
(via the purge contract, §3.2/§7) and re-indexes in a single transaction. This
prevents duplicate documents/chunks/vectors and dangling citations.

**g. Failure handling & transactionality.** Ingestion writes to three stores; a
crash mid-way must not leave them inconsistent. Ordering and rules:
1. Write the blob to disk first; record its path.
2. Insert the `documents` row and all `chunks` rows in **one DB transaction**
   (`status='indexing'`).
3. Insert vectors keyed by `chunk_id`.
4. On success, set `status='indexed'` and confirm "Indexed N pages from
   <filename>".
On any exception: roll back the DB transaction, delete the orphan blob, and — if
the doc row was already committed — mark `status='indexing_failed'` rather than
leaving it in an unknown state. A document not in `status='indexed'` is invisible
to retrieval.

### 3.2 Local storage

Three stores, all on device:
- **Blob store:** the original uploaded files (for display + re-processing).
- **Metadata DB:** documents, chunks, page map, classification, timestamps, the
  query/audit log, and an index-metadata row (embedding model + dimension).
- **Vector index:** chunk embeddings for similarity search.

**Decision:** the metadata DB and vector index are both **SQLite + sqlite-vec**, in
one portable file under `TARA_DATA_DIR`, with the original blobs alongside.
(LanceDB and Chroma were considered; SQLite won for keeping everything in a single
portable file — backup/migration is "copy the file" — which best fits local-first.)
The vector table is created separately from the relational schema because it needs
the sqlite-vec extension loaded; it is created on a separate connection against the
same db file (not the same connection object). Connections opened for request
handlers use `check_same_thread=False` because FastAPI runs sync handlers in a
threadpool (§3.5). `connect()` sets `PRAGMA foreign_keys = ON` so declared cascades
actually fire.

**Embedding model/dimension integrity.** `TARA_EMBED_DIM` must match
`TARA_EMBED_MODEL`. The `vec0` table bakes the dimension in at creation, so a later
model change silently corrupts search. Therefore:
- At startup, validate `embed_dim == model.get_sentence_embedding_dimension()`; fail
  loudly on mismatch.
- Persist the embedding model name + dimension as an index-metadata row when the
  store is first created.
- If `TARA_EMBED_MODEL` changes after indexing, that is a **re-index migration**:
  drop and rebuild the vector table and re-embed all chunks. The mismatch is
  detected by comparing config against the stored index-metadata row; the app
  refuses to serve queries against a stale index rather than returning garbage
  distances.

**Document purge (buildable delete; §7).** Because the `vec_chunks` virtual table
has no foreign-key relationship to `chunks`, deletion is **not** automatic. A
`purge_document(doc_id)` operation, in one transaction, must: (1) delete the
`vec_chunks` rows for the document's `chunk_id`s explicitly; (2) delete `chunks`
(the `documents`→`chunks` cascade fires now that `foreign_keys` is ON); (3) delete
the `documents` row; (4) delete the blob file; (5) delete or redact related
`queries` rows per the retention policy (§7). Order steps so a failure leaves no
"document gone but vectors remain" state.

**Encryption at rest.** SQLCipher (optional `[encryption]` extra) encrypts the DB
file when `TARA_DB_KEY` is set. **Blobs are the richest PHI and are not covered by
SQLCipher**, so when `TARA_DB_KEY` is set the blob files are encrypted with the same
key (AES-GCM). Default install (no key) stores both DB and blobs **unencrypted** —
see §7 for the reconciled posture and residual-risk statement.

### 3.3 Safety / triage layer

Runs **before** the answering LLM on any health-related query. Intentionally
separate from the answering prompt so it can't be "reasoned away" by the main model
and can be tested independently. **Biased toward over-triggering:** a single missed
emergency is far worse than many false alarms.

**Emergency detection (pre-check).** Two layers, combined by a fixed decision rule:
- A fast **keyword/pattern layer** over a red-flag list.
- A **lightweight LLM confirmation layer**. This is **not optional** — it is the
  safety net for phrasings, misspellings, and negations the keyword list misses.
  (If Phase 1 ships without it, the design must explicitly scope the safety net to
  English keyword matching and record that limitation; the default is to include
  the LLM layer.)

**Required minimum emergency taxonomy.** The red-flag set must cover at least:
chest pain / pressure; stroke signs (face droop, slurred speech, sudden one-sided
weakness or numbness, "FAST"); difficulty breathing / choking; anaphylaxis /
throat or tongue swelling; severe bleeding; suicidal ideation and self-harm
(including variants: "kill myself", "end it", "no reason to live", "hurt myself");
overdose / poisoning / ingestion; seizure; loss of consciousness / unresponsive /
fainting; sepsis signs (high fever + confusion); meningitis signs (stiff neck +
fever); pregnancy emergencies (heavy vaginal bleeding, no fetal movement);
"worst headache of my life"; severe abdominal pain. This taxonomy is the gate for
the §8 safety-recall eval — it is a required floor, not an "etc." list.

**Decision rule (fail-closed).**
- Escalate if the keyword layer **OR** the LLM layer flags. The LLM may **never
  downgrade** a keyword hit.
- If the pre-check cannot complete (LLM down, classifier error, timeout), **fail
  toward escalation** — do not answer; show the conservative safety message.
- When escalating, always return a **non-empty, locale-aware escalation message**
  (emergency number is configurable; 911 is US-specific). Tara does not give
  self-care advice on the emergency path; it directs the user to emergency services
  and stops.

**Framing (post-check).** Ensures the final answer is framed as general
information, includes a professional-care nudge for anything serious or persistent,
and avoids guaranteed outcomes/timelines. **Framing is append-only and
non-destructive** — it may add disclaimers but must not edit the grounded facts or
the citation markers (see ordering in §3.5/§6). If framing fails, return the
grounded answer with a default static disclaimer rather than erroring.

### 3.4 Retrieval

1. Embed the query (same on-device model as indexing).
2. **Infer document type** from the question (a small rule/LLM step):
   cost/coverage → `insurance_policy`/`benefits_summary`/`eob`/`bill`; "my
   results" → `lab_report`; medication → `prescription`; etc. The inferred type(s)
   are translated to the matching `doc_id`s via a `documents` lookup.
3. **Vector search with a document-type filter.** sqlite-vec `vec0` does **not**
   support an arbitrary `WHERE` on non-vector columns inside the KNN query, so the
   Phase 1 contract is **post-filtering**: run KNN for `k * multiplier`, then keep
   the first `k` whose `doc_id` is in the allowed set (correct and cheap at
   single-user scale). Falls back to unfiltered search if type inference is
   low-confidence.
4. Optional rerank for precision.
5. **Abstention guard.** If the best retrieval score is below a configured
   threshold, treat the question as unsupported — the answerer should decline
   ("I don't see that in your documents") rather than stretch weak context. This
   complements the prompt-level honesty rule (§3.5).
6. Assemble the top-k chunks into context, each tagged with its `chunk_id` and
   source (doc name + page). **Cap the assembled context to a token budget** sized
   to the answering model's window (`qwen3:8b` is small) — reduce `k` before
   overflowing rather than truncating mid-chunk.

### 3.5 Answering LLM

Given the assembled context, the model must:
- Answer **only** from the provided chunks.
- **Cite** the chunk(s) it used (the app maps `chunk_id → document + page + char
  span` for display).
- Say **"I don't see that in your documents"** when the context doesn't support an
  answer — never fabricate coverage numbers, results, or policy terms.

**Post-processing order (fixed).** Operate on one canonical answer string:
1. Parse the `[chunk_id]` markers the model emitted and map each to a `Citation`.
2. **Numeric-grounding check:** every monetary amount / lab value / policy number
   stated in the answer must appear in the text of a cited chunk. A figure that
   isn't grounded is dropped or the answer is downgraded to an abstention — a
   confidently wrong copay with a citation is more dangerous than a refusal.
3. Apply append-only safety framing (§3.3).
This ordering guarantees the user-visible text, the citation markers, and the
framing never diverge.

**Citation provenance carries the span.** A `Citation` carries `{chunk_id,
filename, page, char_start, char_end, snippet}` — not just `page`. The char span is
what lets the UI open the source page and highlight the cited text. (On OCR'd
scans, char spans aren't pixel-mappable, so the citation resolves to page level;
§3.1b.)

> **Privacy seam:** this is the main point where data may leave the device (if using
> a hosted model). **Decision:** model selection is a config switch —
> `TARA_MODEL_MODE` is `local` / `hosted` / `hybrid`, defaulting to `local`
> (Ollama); the hosted path uses Anthropic. Local-vs-hosted is never a code change.
> For this to be config-only, **all** provider settings live in `Settings`,
> including `TARA_ANTHROPIC_API_KEY`; a startup validator fails loudly when
> `model_mode in (hosted, hybrid)` and the key is missing, rather than a module
> hard-coding an env lookup. Retrieval and indexing stay local regardless; only the
> minimal assembled context + question ever go to the model, and the LLM client is
> created once with a configured timeout (`TARA_LLM_TIMEOUT_SECONDS`) so a stalled
> model can't hang the request indefinitely. What remains open is empirical —
> whether the local model's quality suffices for grounded reasoning (OPEN_QUESTIONS.md
> #1, to be settled with the §8 eval harness).

---

## 4. Data model (sketch)

```
documents
  doc_id          (pk)
  filename
  doc_type        (insurance_policy | lab_report | eob | bill | ...)
  content_hash    (for re-ingest dedup; §3.1f)
  status          (indexing | indexed | indexing_failed; §3.1g)
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

index_meta                       -- guards model/dim integrity (§3.2)
  embed_model
  embed_dim
  created_at

queries            (audit/eval; written on every answered query)
  query_id        (pk)
  question
  retrieved_chunk_ids            -- needed by §8 retrieval eval
  answer
  citations                      -- chunk_id + page + char span
  safety_flag     (none | emergency)
  model_route     (local | hosted)   -- so PHI egress is auditable (§7)
  created_at
```

A runtime **`Citation`** maps a cited `chunk_id` to `{filename, page, char_start,
char_end, snippet}` for display (§3.5).

---

## 5. Key flows

### 5.1 Ingestion (sequence)
```
upload → validate (size, extension) → detect type → extract text (+page/char spans)
       → classify doc → chunk (deterministic ids, page-bounded)
       → content-hash dedup check (reject or replace; §3.1f)
       → BEGIN: write documents + chunks rows  ─┐
       → write vectors (keyed by chunk_id)       │ one logical unit; §3.1g
       → COMMIT, status='indexed'  ──────────────┘
       → confirm "Indexed N pages from <filename>"
   (on failure: rollback rows, delete orphan blob, mark indexing_failed)
```

### 5.2 Query (sequence)
```
question (in request BODY, not URL; §7) → SAFETY pre-check (fail-closed)
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

## 6. Answering prompt (sketch)

> You are Tara, a personal health & insurance assistant. Answer the user's question
> using ONLY the document excerpts provided below. Each excerpt has an ID. When you
> state a fact, cite the excerpt ID(s) it came from. If the excerpts do not contain
> the answer, say you don't see it in their documents — do not guess or invent
> coverage amounts, results, or policy terms. Frame any health information as
> general information, not a diagnosis, and suggest professional care for anything
> serious or persistent.
>
> [excerpts: {chunk_id, source, page, text} ...]
> [question]

Notes:
- Keep the safety pre-check as a *separate* call/stage — do not rely on this prompt
  alone for emergency handling (§3.3).
- The app, not the prompt, enforces the hard guarantees: citation mapping →
  numeric-grounding check → append-only framing run **after** the model returns, in
  that order (§3.5). The prompt requests good behavior; the post-checks enforce it.

---

## 7. Privacy & security (Phase 1)

- **Storage on device.** All three stores live on the device.
- **Encryption at rest — reconciled posture.** Encryption is **available and
  off by default**: setting `TARA_DB_KEY` encrypts the DB (SQLCipher) **and** the
  blob files (AES-GCM, §3.2). The default install runs unencrypted for
  out-of-the-box simplicity; this residual risk is stated here deliberately rather
  than implied as "always encrypted." Enabling encryption is one config value plus
  the `[encryption]` extra.
- **On-device by default.** OCR + embeddings run on-device; cloud OCR only behind
  explicit opt-in. Embeddings never egress, even in `hosted` mode.
- **Minimal egress.** Send only the assembled context + question to any hosted
  model — never the whole corpus — and only when `model_mode` opts in. The
  `queries.model_route` field records whether a given answer used the local or
  hosted model, so the user can audit what left the device.
- **PHI-safe request handling.** The question is sent in the **request body**, not
  as a URL/query parameter, so health text doesn't land in access logs or browser
  history.
- **Audit log.** Every answered query is logged locally (question, answer,
  citations, safety flag, model route) so the user can see what was asked/answered
  and what egressed.
- **Delete is real and complete.** `purge_document(doc_id)` removes the blob,
  chunks, and vectors (§3.2). The audit log can itself contain PHI; the retention
  policy is: document deletion redacts/links its `queries` rows, and a separate
  "clear history" purges the audit log. "Delete purges everything" is therefore
  literally true.

---

## 8. Testing & evaluation

- **Retrieval accuracy:** curated Q→expected-chunk pairs across each doc type;
  measure top-k hit rate (uses `queries.retrieved_chunk_ids`).
- **Citation correctness:** does the cited page actually contain the stated fact?
- **Value/numeric accuracy:** for answerable cost/coverage/lab questions, does the
  stated **number** match ground truth — not just the citation page? A
  wrong-but-cited figure is a higher-harm failure than a refusal.
- **Hallucination / honesty:** ask questions the docs *can't* answer; the system
  must decline (prompt rule + the §3.4 abstention guard), not invent.
- **Safety recall (release gate):** a battery covering the full §3.3 emergency
  taxonomy; the pre-check must catch them. **This is a gate, not a metric** — target
  100% recall on the taxonomy fixture before the safety layer is considered done.
  Favor over-triggering; track the false-positive rate against a ceiling.
- **OCR fidelity:** spot-check extracted numbers on scanned lab reports / EOBs,
  since a misread digit in a copay or result is a real harm.

---

## 9. What Phase 1 deliberately excludes

- No actions of any kind (calendar, email, reminders, pharmacy, delivery).
- No external integrations / MCP servers yet.
- No proactive behavior — Tara only responds when asked.

These arrive in Phase 2+ (see PRD §11), building on the retrieval + safety
foundation established here. The action seam is designed in
[PHASE_2_TECHNICAL_DESIGN.md](PHASE_2_TECHNICAL_DESIGN.md).

---

## 10. Suggested build order within Phase 1

1. Ingestion for native-text PDFs → chunk (deterministic ids) → local index, with
   the transactional write path (§3.1g) and embed-dim validation (§3.2). Get
   retrieval working first.
2. Answering LLM with grounding + "decline if unsupported" + the §3.4 abstention
   guard.
3. Citations (chunk → page + char-span mapping surfaced in the UI).
4. Safety pre-check (emergency detection, fail-closed) + post-check framing —
   **and the §8 safety-recall fixture alongside it**, gating this step. Don't defer
   safety measurement to step 7.
5. OCR path for scanned docs + images (page-level citations).
6. Document classification + filtered retrieval (post-filter contract, §3.4).
7. Full eval harness (§8) — retrieval/citation/value-accuracy/honesty/OCR — against
   a fixture set of sample documents. (Safety recall already gated at step 4.)

---

## 11. Repository layout

How the design above maps onto the code tree:

```
tara-health/
├── pyproject.toml          # deps wired to the chosen stack
├── .env.example            # config: model mode, paths, models, api key, limits
├── src/tara/
│   ├── config.py           # central settings (paths, model mode, embed model, api key, limits, timeouts)
│   ├── app.py              # FastAPI: /upload, /ask (body), / (UI)
│   ├── ingestion/          # detect → extract(+spans) → classify → chunk → pipeline (§3.1)
│   ├── embeddings/         # local sentence-transformers (§3.1e)
│   ├── storage/            # sqlite + sqlite-vec + blobs, purge, SQLCipher-ready (§3.2)
│   ├── retrieval/          # embed query → doc-type filter → post-filtered search → abstain (§3.4)
│   ├── llm/                # base + local_ollama + hosted (hybrid switch) (§3.5)
│   ├── safety/             # triage (pre-check, fail-closed) + framing (post-check) (§3.3)
│   ├── answering/          # prompts + answerer — full query flow incl. numeric grounding (§5.2, §6)
│   └── web/                # placeholder UI
├── scripts/init_db.py      # create schema + vector table + index_meta
└── tests/                  # ingestion/retrieval/safety + eval_harness (§8)
```

Every stub marks its intent with a docstring and a `TODO` describing its contract.
When implementing, honor the contracts above (the v0.3 changes tighten several
stub contracts — update the docstrings to match as each is built). Quickstart
commands live in the README and `CLAUDE.md`; build order is §10 above.
