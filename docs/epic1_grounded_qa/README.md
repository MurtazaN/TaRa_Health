# TaRa Health — Epic 1: Grounded Q&A *(former Phase 1)*

- **Epic 1 scope:** grounded, read-only Q&A over the user's documents.
- **Explicitly out of scope for Epic 1:** any agentic *action* (no calendar, email, pharmacy, delivery).
- Epic 1 builds the foundation — ingestion, retrieval, grounded answering, citations, and the safety layer — that every later epic depends on.
- The action seam itself is designed in [Epic2_first_actions.md](../Epic2_first_actions.md).
- **Status:** Draft v0.3 (content); split into per-module docs 2026-07-08 (content unchanged).
- **Last updated:** 2026-07-08.

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

## Modules

1. [M1 — ingestion_pipeline](M1_ingestion_pipeline.md) — turn an uploaded file into indexed, citable chunks — detect → extract(+spans) → chunk → embed → index, as one transactional unit.
1. [M2 — local_storage](M2_local_storage.md) — the on-device state plane — SQLite + sqlite-vec, schema, purge, encryption, and embedding-index integrity.
1. [M3 — retrieval](M3_retrieval.md) — embed the query, filter by inferred document type, post-filter KNN results, abstain when weak, and assemble token-budgeted context.
1. [M4 — grounded_answering](M4_grounded_answering.md) — answer only from retrieved chunks, cite them, decline when unsupported, and enforce numeric grounding after the model returns.
1. [M5 — safety](M5_safety.md) — emergency pre-check (fail-closed, before the answering model) + append-only framing post-check, with a 100%-recall release gate.
1. [M6 — ocr](M6_ocr.md) — the scanned-document / image extraction path — OCR with page-granularity citations.
1. [M7 — classification](M7_classification.md) — tag each document with a type and use inferred types to filter retrieval.
1. [M8 — eval_harness](M8_eval_harness.md) — measurable Epic-1 quality — retrieval, citation, value accuracy, honesty, safety recall, OCR fidelity — against a fixture set of sample documents.

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
- These arrive in Epics 2–4 (see PRD §11), building on the retrieval + safety foundation established here; the action seam is designed in [Epic2_first_actions.md](../Epic2_first_actions.md).

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
