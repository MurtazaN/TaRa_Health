# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TaRa Health is a **local-first, single-profile AI health & insurance assistant**. The user uploads their own health/insurance documents and asks questions; "Tara" answers grounded in those documents with citations.

**This repo is currently an Epic 1 scaffold.** Nearly every core function is an intentional `NotImplementedError` stub carrying a docstring and a `TODO` that specifies its contract. The structure, data models, and module boundaries are real and settled; the implementations are not yet filled in. When implementing, honor the contract described in each stub's docstring rather than redesigning the interface.

- **Epic 1 scope (current):** read-only grounded Q&A over the user's documents — ingestion, retrieval, grounded+cited answering, and the safety layer.
- **Out of scope until Epic 2+:** any agentic *action* (calendar, email, pharmacy, delivery). The README describes the eventual product; the code does not yet do actions.
- The roadmap is 4 **Epics** (top-level units, former "Phases"), each decomposed into numbered **Modules** (M1, M2, … — implementation-sized units, former "Slices").

The authoritative spec is [docs/Epic1_grounded_qa.md](docs/Epic1_grounded_qa.md) — see its "Repository layout" section for the code-tree map. The Epic 2+ vision is designed (not yet built) in an epic-doc series: [Epic 2](docs/Epic2_first_actions.md) (calendar + reminders — also defines the shared agent/tool/confirmation-gate foundations), [Epic 3](docs/Epic3_external_actions.md) (email/delivery/pharmacy via assisted handoff), and [Epic 4](docs/Epic4_portal_and_proactive.md) (Epic on FHIR + proactive). Each epic doc is self-contained for that epic.

## Commands

```bash
pip install -e ".[dev]"          # install with dev tools (pytest, ruff, mypy)
ollama pull qwen3:8b             # pull the local model named in .env (TARA_LOCAL_MODEL)
cp .env.example .env             # configure model mode, paths, models
python scripts/initialize_data_stores.py        # create SQLite schema + sqlite-vec table (run once)
tara                             # run the local server at http://127.0.0.1:8000

pytest                           # run tests
pytest tests/safety_checks/test_emergency_triage.py   # single test file
pytest tests/safety_checks/test_emergency_triage.py::test_emergencies_are_caught  # single test
python tests/eval_harness.py     # Epic 1 eval metrics (retrieval/citation/honesty/safety/OCR)
ruff check src tests             # lint
mypy src                         # type-check
```

Optional encrypted-at-rest storage: `pip install -e ".[encryption]"` (pulls SQLCipher, which needs a system lib — kept optional so the default install works out of the box).

## Architecture

All configuration is centralized in [src/tara/config.py](src/tara/config.py) (`get_settings()`, env-prefixed `TARA_`). Code never hard-codes a provider, model, or directory — it reads from settings.

**Two pipelines, defined in the design doc and mirrored by the module layout:**

- **Ingestion** ([src/tara/document_ingestion/ingestion_pipeline.py](src/tara/document_ingestion/ingestion_pipeline.py)): `save blob → extract → classify → chunk → embed → index`. The pipeline orchestrates the other `document_ingestion/` modules plus `semantic_search/` and `local_data_stores/`.
- **Answering** ([src/tara/question_answering/question_answerer.py](src/tara/question_answering/question_answerer.py)): `safety pre-check → retrieve → grounded+cited answer → safety framing`. This is the heart of Epic 1.

**Cross-cutting design constraints — preserve these when implementing:**

- **Citations depend on end-to-end provenance.** `extract_text_spans()` must preserve `(page, char_start, char_end)` for every span; `Chunk` carries that provenance; the answerer maps cited chunk IDs back to `Citation`. Don't drop position information anywhere in the chain or citations break.
- **The LLM is an abstraction, not a hard dependency.** Everything talks to the `LLMClient` protocol in [src/tara/llm_clients/llm_client_interface.py](src/tara/llm_clients/llm_client_interface.py). `get_llm_client(prefer_hosted=...)` chooses a local backend (Ollama, or an OpenAI-compatible server such as LM Studio, per `local_llm_backend`) vs hosted based on `model_mode` (`local` / `hosted` / `hybrid`). Local-vs-hosted is a config decision, never a code change. Default mode is `local` (private, offline); hosted means data leaves the device.
- **Safety is deliberately separate from answering.** [src/tara/safety_checks/emergency_triage.py](src/tara/safety_checks/emergency_triage.py) runs an emergency pre-check *before* the answering model so it cannot be "reasoned away," and is biased toward over-triggering. [src/tara/safety_checks/answer_framing.py](src/tara/safety_checks/answer_framing.py) is a post-check on the answer. Test safety hardest.
- **Storage is local SQLite + sqlite-vec, one module per concern.** [src/tara/local_data_stores/](src/tara/local_data_stores/): `db_connection.py` (pragmas, SQLCipher hook), `db_schema.py` (DDL), `document_records.py` + `chunk_records.py` (row operations — **all SQL for a table lives in its record module; no SQL outside `local_data_stores/`**), `embedding_index_meta.py` (model/dim drift guard), `vector_index.py` (the `vec0` virtual table, created separately because it needs the sqlite-vec extension loaded), `blob_store.py`, `document_purge.py`. Embedding dimension comes from config (`embed_dim`, must match `embed_model`).

**Suggested build order** (from the Epic 1 doc's "Build order" section, since stubs depend on each other): native-text PDF ingestion + retrieval first → grounded answering with "decline if unsupported" → citations → safety pre/post checks → OCR path for scans → doc classification + filtered retrieval → eval harness.

## Conventions

- Python 3.11+, `from __future__ import annotations` at the top of every module.
- Package lives under `src/tara/` (src layout); the `tara` console script maps to `tara.web_app:main`.
- Data models are dataclasses in [src/tara/data_models.py](src/tara/data_models.py); error types live in [src/tara/app_errors.py](src/tara/app_errors.py); `DocType` is a closed `Literal` set.
- **Naming rules (enforced, non-negotiable):**
  1. Every package/file/function/variable names its object — `local_data_stores`, never `storage`; `agent_tools`, never `tools`; `retrieve_chunks()`, never `retrieve()`.
  2. Packages are capabilities or planes; files are their components. A name must answer "what does this do to what" without opening it.
  3. No one-concept packages — a shared model or error type is a well-named root module (`data_models.py`, `app_errors.py`), not a `domain/`/`core/` bucket.
  4. Modules are noun phrases (`text_chunking.py`); functions are verb+object (`chunk_spans()`); no single-letter variables.
  5. Docstrings state purpose first, rationale second.
- **Import direction:** kernel (`config`, `data_models`, `app_errors`, `upload_validation`) ← planes (`llm_clients`, `local_data_stores`) ← capabilities (`document_ingestion`, `semantic_search`, `question_answering`) ← `safety_checks`/agent packages ← `web_app.py`. Capabilities never import each other, except `question_answering → semantic_search` and `→ safety_checks` (the Epic 1 query flow). Epic 2 code lands in `agent_orchestration/` and `agent_tools/` (names reserved in the Epic 1 repository layout).
- This app handles sensitive PHI: keep processing on-device by default, log actions for auditability, and treat the hosted path as an explicit data-egress opt-in.
- **Output format (all chat replies AND all files created):** use bulleted/numbered lists, never prose paragraphs. Allow at most a one-line lead-in before a list. Applies to docs, plans, and design docs too.
