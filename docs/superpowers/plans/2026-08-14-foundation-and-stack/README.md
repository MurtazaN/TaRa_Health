# Foundation & Tech-Stack — Implementation Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement these plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give TaRa Health the infrastructure and tooling layer the epic docs never specified — monorepo separation, CI, containers, execution tracing, PHI redaction — without changing any Epic 1 module contract.

**Spec:** [docs/superpowers/specs/2026-08-14-foundation-and-stack-design.md](../../specs/2026-08-14-foundation-and-stack-design.md)

**Tech Stack:** Python 3.12 · FastAPI · uv · OpenTelemetry + OpenInference · Arize Phoenix · Presidio · Instructor · `BAAI/bge-reranker-v2-m3` · DeepEval · Docker Compose · GitHub Actions

---

## Phases

| # | Phase | Plan | Changes behaviour? | Gate |
|---|---|---|---|---|
| 1 | Foundation | [phase_1_foundation.md](phase_1_foundation.md) | No | Suite still 67 passed / 3 skipped; `docker compose up` serves `/` |
| 2 | Observability | [phase_2_observability.md](phase_2_observability.md) | No | An `/ask` call produces a redacted span tree at `localhost:6006` |
| 3 | Epic 1 resume | [phase_3_epic1_resume.md](phase_3_epic1_resume.md) | Yes | Per the existing Epic 1 module contracts |

- **Ordering is load-bearing.** Phase 1 must land before any M4 code, or M4's files get moved twice.
- **Phases 1 and 2 are behaviour-neutral by design.** Every functional change lives in phase 3.

## Global Constraints

- **Python:** 3.11+ source compatibility; the dev interpreter is 3.12. `from __future__ import annotations` at the top of every module.
- **Naming (non-negotiable, from `CLAUDE.md`):** every package/file/function names its object — `local_data_stores`, never `storage`; `retrieve_chunks()`, never `retrieve()`. Modules are noun phrases; functions are verb+object. No single-letter variables. No one-concept packages — a shared concern is a well-named root module.
- **Docstrings:** purpose first, rationale second.
- **Import direction:** kernel (`config`, `data_models`, `app_errors`, `upload_validation`, `phi_redaction`) ← planes (`llm_clients`, `local_data_stores`, `execution_tracing`) ← capabilities (`document_ingestion`, `semantic_search`, `question_answering`) ← `safety_checks` ← `web_app`. Capabilities never import each other, except `question_answering → semantic_search` and `→ safety_checks`.
- **All SQL lives in `local_data_stores/`.** No SQL anywhere else.
- **Configuration is centralized** in `config.py`, env-prefixed `TARA_`. Code never hard-codes a provider, model, host, or directory.
- **Output format for every file created:** bulleted or numbered lists, never prose paragraphs. At most a one-line lead-in before a list.
- **New settings default to off or safe**, so infrastructure work changes nothing observable.
- **Commit after every task.** Branch is `feat/foundation-and-stack`.

## Out-of-band item (not a code task)

- **Rotate the `HUGGINGFACEHUB_API_KEY` and `NVIDIA_API_KEY` values in the local `.env`** — spec §13.4. The file is gitignored and has never been committed, so nothing leaked to version control, but both values appeared in a session transcript. No plan task covers this because it is an action on the provider consoles, not a change to the repository.

## Verification commands

- Run from the repository root after phase 1:

```bash
make lint        # ruff check backend/src backend/tests
make typecheck   # mypy (from backend/)
make test        # pytest (from backend/)
make up          # docker compose -f deployment/docker/compose.yaml up -d
make eval        # DeepEval gate — local only, never in CI
```
