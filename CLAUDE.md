# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TaRa Health is a **local-first, single-profile AI health & insurance assistant**. The user uploads their own health/insurance documents and asks questions; "Tara" answers grounded in those documents with citations.

**This repo is currently a Phase 1 scaffold.** Nearly every core function is an intentional `NotImplementedError` stub carrying a docstring and a `TODO` that specifies its contract. The structure, data models, and module boundaries are real and settled; the implementations are not yet filled in. When implementing, honor the contract described in each stub's docstring rather than redesigning the interface.

- **Phase 1 scope (current):** read-only grounded Q&A over the user's documents — ingestion, retrieval, grounded+cited answering, and the safety layer.
- **Out of scope until Phase 2+:** any agentic *action* (calendar, email, pharmacy, delivery). The README describes the eventual product; the code does not yet do actions.

The authoritative spec is [docs/PHASE_1_TECHNICAL_DESIGN.md](docs/PHASE_1_TECHNICAL_DESIGN.md) — see its §11 "Repository layout" for the code-tree map.

## Commands

```bash
pip install -e ".[dev]"          # install with dev tools (pytest, ruff, mypy)
ollama pull qwen3:8b             # pull the local model named in .env (TARA_LOCAL_MODEL)
cp .env.example .env             # configure model mode, paths, models
python scripts/init_db.py        # create SQLite schema + sqlite-vec table (run once)
tara                             # run the local server at http://127.0.0.1:8000

pytest                           # run tests
pytest tests/test_safety.py      # single test file
pytest tests/test_safety.py::test_emergencies_are_caught   # single test
python tests/eval_harness.py     # Phase 1 eval metrics (retrieval/citation/honesty/safety/OCR)
ruff check src tests             # lint
mypy src                         # type-check
```

Optional encrypted-at-rest storage: `pip install -e ".[encryption]"` (pulls SQLCipher, which needs a system lib — kept optional so the default install works out of the box).

## Architecture

All configuration is centralized in [src/tara/config.py](src/tara/config.py) (`get_settings()`, env-prefixed `TARA_`). Code never hard-codes a provider, model, or directory — it reads from settings.

**Two pipelines, defined in the design doc and mirrored by the module layout:**

- **Ingestion** ([src/tara/ingestion/pipeline.py](src/tara/ingestion/pipeline.py)): `save blob → extract → classify → chunk → embed → index`. The pipeline orchestrates the other `ingestion/` modules plus `embeddings/` and `storage/`.
- **Answering** ([src/tara/answering/answerer.py](src/tara/answering/answerer.py)): `safety pre-check → retrieve → grounded+cited answer → safety framing`. This is the heart of Phase 1.

**Cross-cutting design constraints — preserve these when implementing:**

- **Citations depend on end-to-end provenance.** `extract()` must preserve `(page, char_start, char_end)` for every span; `Chunk` carries that provenance; the answerer maps cited chunk IDs back to `Citation`. Don't drop position information anywhere in the chain or citations break.
- **The LLM is an abstraction, not a hard dependency.** Everything talks to the `LLMClient` protocol in [src/tara/llm/base.py](src/tara/llm/base.py). `get_client(prefer_hosted=...)` chooses local (Ollama) vs hosted (Anthropic) based on `model_mode` (`local` / `hosted` / `hybrid`). Local-vs-hosted is a config decision, never a code change. Default mode is `local` (private, offline); hosted means data leaves the device.
- **Safety is deliberately separate from answering.** [src/tara/safety/triage.py](src/tara/safety/triage.py) runs an emergency pre-check *before* the answering model so it cannot be "reasoned away," and is biased toward over-triggering. [src/tara/safety/framing.py](src/tara/safety/framing.py) is a post-check on the answer. Test safety hardest.
- **Storage is local SQLite + sqlite-vec.** [src/tara/storage/db.py](src/tara/storage/db.py) holds the relational schema (documents, chunks, queries); [src/tara/storage/vector.py](src/tara/storage/vector.py) holds the `vec0` virtual table keyed by `chunk_id`. The vector table is created separately from the main schema because it needs the sqlite-vec extension loaded. Embedding dimension comes from config (`embed_dim`, must match `embed_model`).

**Suggested build order** (from design doc §10, since stubs depend on each other): native-text PDF ingestion + retrieval first → grounded answering with "decline if unsupported" → citations → safety pre/post checks → OCR path for scans → doc classification + filtered retrieval → eval harness.

## Conventions

- Python 3.11+, `from __future__ import annotations` at the top of every module.
- Package lives under `src/tara/` (src layout); the `tara` console script maps to `tara.app:main`.
- Data models are dataclasses in [src/tara/storage/models.py](src/tara/storage/models.py); `DocType` is a closed `Literal` set.
- This app handles sensitive PHI: keep processing on-device by default, log actions for auditability, and treat the hosted path as an explicit data-egress opt-in.
