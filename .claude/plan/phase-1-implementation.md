# Epic 1 Implementation Plan (for review) *(formerly "Phase 1"; Slices renamed Modules)*

> Plan only — no code yet beyond the noted progress. Spec is
> [docs/epic1_grounded_qa/](../../docs/epic1_grounded_qa/README.md) (content = design **v0.3**; one doc per design module M1–M8);
> honor the v0.3 contracts (the scaffold stubs don't reflect them yet). Build order
> follows the Epic 1 doc's "Build order" section. Workflow: **TDD** (red → green →
> refactor), ruff + mypy clean, ≥80% coverage on touched modules, `code-reviewer`
> pass per module.
> Note: build-order Modules 0–7 below are sequenced work units; the Epic 1 doc's
> design modules are M1–M8 (referenced inline).

## Environment (verified 2026-06-28)
- `.venv` via uv, **Python 3.12.13**; all deps import (fastapi, pydantic-settings,
  sentence-transformers, sqlite-vec, pymupdf4llm, docling, ollama, anthropic, pytest).
- `.env` present and populated.
- Run tests with the venv: `.venv/bin/python -m pytest`.

## Decisions — RESOLVED (2026-07-05)
1. **Local LLM backend → BOTH, config-selected.** Implement an Ollama client *and*
   an OpenAI-compatible client (LM Studio), chosen by `TARA_LOCAL_BACKEND`
   (`ollama` | `openai_compatible`, default `openai_compatible`). LM Studio base =
   `{TARA_LMSTUDIO_HOST}/v1`. (LLM clients themselves land in Module 2.)
2. **Embeddings → LM Studio `/v1/embeddings`.** `text-embedding-qwen3-embedding-0.6b`,
   dim 1024. Vectors are unit-normalized in the embedder. The static config validator
   only sanity-checks `embed_dim > 0`; the real model↔dim integrity check is a runtime
   probe + the `index_meta` singleton row (an API-served model's dim can't be derived
   from its name).
3. **pytest scope → `testpaths = ["tests"]`.** Done (ECC collection clash gone).

## Progress
- **Module 0 — DONE.** config/models/db aligned to v0.3; `index_meta` singleton;
  `ensure_dirs()` split out of the cached factory; app.py `/ask` moved to a request
  body (Epic 1 Privacy); `.env.example` refreshed; mypy pinned to 3.12 (matches the uv venv).
  Gate: tests green, ruff+mypy clean, code-reviewer APPROVED.
- **Module 1 — DONE (pending review sign-off).** detect+extract(raw PyMuPDF words)+
  chunk(page-bounded, deterministic ids, exact-offset invariant)+embedder(OpenAI-
  compat)+blobs/vector/purge+pipeline(txn + content-hash dedup + failure cleanup)+
  retriever(L2→cosine + abstention). 34 tests pass (incl. integration: fixture PDF →
  retrieve w/ provenance; dedup; purge; failure invisibility), ruff+mypy clean, 94%
  coverage on touched modules. `openai` + `pytest-cov` added to deps.

## (historical) Decisions as originally posed
1. **Local LLM backend.** `.env` has both `TARA_OLLAMA_HOST` and `TARA_LMSTUDIO_HOST`.
   Design (Epic 1 M4) = Ollama. Options: (a) Ollama only (matches design); (b) add an
   OpenAI-compatible local client so LM Studio works too.
2. **Embedding model/dim.** Confirm `TARA_EMBED_MODEL` ↔ `TARA_EMBED_DIM` agree.
3. **pytest scope.** OK to set `testpaths = ["tests"]`?

---

## Module 0 — Align scaffold to design v0.3 + clean test harness
Small, mostly declarative; no business logic. Unblocks everything else.

- **config.py** — add `anthropic_api_key`, `max_upload_bytes` (50 MB), `llm_timeout_seconds`;
  `@model_validator` that fails when `model_mode in (hosted, hybrid)` and key is empty;
  embed model↔dim validator. Move `mkdir` side-effects out of the `lru_cache`d factory.
- **storage/models.py** — `Citation += char_start, char_end, snippet`; `Document +=
  content_hash, status`; `Chunk` deterministic-id helper (`{doc_id}:{page}:{char_start}`);
  replace `datetime.utcnow()` → `datetime.now(timezone.utc)`.
- **storage/db.py** — `connect()`: `PRAGMA foreign_keys = ON`, `check_same_thread=False`;
  schema: `documents.content_hash/status`, `queries.retrieved_chunk_ids/model_route`,
  new `index_meta(embed_model, embed_dim, created_at)`.
- **pyproject.toml** — `[tool.pytest.ini_options] testpaths = ["tests"]`.
- **Tests (first):** schema builds; FK cascade fires on document delete; config
  validator rejects missing hosted key; embed dim mismatch raises.
- **Done when:** `pytest` runs clean (no ECC errors), new tests green, mypy/ruff clean.

## Module 1 — Ingestion (native-text PDF) → chunk → embed → index → retrieval  (Epic 1 build-order step 1; design M1–M3)
The core "get retrieval working first" module. No Ollama needed.

- **ingestion/detect.py** — native-text vs scan; enforce size + extension whitelist
  (`.pdf/.png/.jpg/.jpeg/.tiff`).
- **ingestion/extract.py** — native PDF text + `(page, char_start, char_end)` via **raw
  PyMuPDF positions** (`get_text("words"/"rawdict")`), not markdown (per Epic 1 M1, so
  spans index the canonical text).
- **ingestion/chunk.py** — structural-ish chunking; deterministic `chunk_id`; **page-bounded**
  (no chunk crosses a page).
- **embeddings/embedder.py** — local sentence-transformers; validate dim vs `index_meta` at startup.
- **storage/blobs.py** — save `{doc_id}{suffix}` with extension whitelist.
- **storage/vector.py** — `vec0` create + insert (keyed by `chunk_id`) + KNN search with
  **post-filter by `doc_id`** (k*multiplier then filter; Epic 1 M3 contract).
- **ingestion/pipeline.py** — orchestrate with the **transactional write path** (Epic 1 M1:
  blob → rows in one txn → vectors → status=indexed; rollback + blob cleanup on failure)
  and **content-hash dedup** (Epic 1 M1).
- **retrieval/retriever.py** — embed query → vector search → **abstention guard** (below
  threshold ⇒ unsupported) → assemble token-budgeted context with provenance.
- **Tests (first):** unit per module; **integration:** ingest a tiny fixture PDF →
  retrieve the expected chunk with correct `(page, char_span)`; re-ingest same file ⇒ no
  duplicate; purge ⇒ rows + vectors + blob gone. All offline.
- **Done when:** fixture PDF ingests and the right chunk is retrieved with provenance, via
  a passing integration test; coverage ≥80% on the ingestion/retrieval/storage modules.
- **Note:** doc-type *classification* + *filtered* retrieval is build step 6 — Module 1
  retrieval is unfiltered + abstention; classification deferred.

## Later modules (outline — detail each when we reach it)
- **Module 2 — Answering** (build step 2; design M4): grounded prompt + "decline if
  unsupported"; post-order = map citations → numeric-grounding check → append-only framing.
  Needs the local LLM (decision #1). Tests: declines on weak context; never emits an
  ungrounded number.
- **Module 3 — Citations surfaced** (step 3; design M4): chunk → page + char-span in the API/UI; OCR ⇒ page-level.
- **Module 4 — Safety** (step 4; design M5): pre-check (required taxonomy, fail-closed) + post-check
  framing **and the safety-recall fixture as a release gate** (target 100% on the taxonomy).
- **Module 5 — OCR** (step 5; design M6): docling/Tesseract path for scans + images; page-level citations.
- **Module 6 — Classification + filtered retrieval** (step 6; design M7): doc-type inference → doc_id post-filter.
- **Module 7 — Eval harness** (step 7; design M8): retrieval / citation / value-accuracy / honesty / OCR.

## Per-module gates
tests green · ruff clean · mypy clean · coverage ≥80% on touched modules · `code-reviewer`
(and `security-reviewer` for the upload/PHI paths). Safety recall (Module 4) is a hard gate.

## Suggested first move in the fresh session
Confirm decisions #1–#3, then **Module 0** (align + clean harness) → **Module 1** TDD.
