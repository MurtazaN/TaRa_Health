# Plan: Restructure docs/ — Phases → Epics, Slices → Modules (Option A)

- **Status:** EXECUTED 2026-07-07 (historical record; `PHASE_*` names below refer to the deleted source files).
- **Do NOT rewrite docs in the session that created this plan** (cost/context ceiling hit).
- **Formatting rule (MANDATORY, all output):** bullets/numbered lists only — no prose paragraphs — in chat AND in every file written. (See `CLAUDE.md` Conventions + memory `formatting-bullets-not-paragraphs`.)

## 1. Terminology & hierarchy (approved)
1. **Phase → Epic** = top-level roadmap unit.
2. **Slice → Module** = implementation-sized unit inside an epic.
3. Result: 4 Epics (= former 4 phases), each decomposed into numbered Modules.

## 2. Layout — Option A (approved)
- One doc per **Epic**, each internally sectioned by its **Modules** (numbered `##` sections).
- 4 epic docs total, descriptive names (no "technical_design"):
  1. `docs/Epic1_grounded_qa.md`
  2. `docs/Epic2_first_actions.md`
  3. `docs/Epic3_external_actions.md`
  4. `docs/Epic4_portal_and_proactive.md`

## 3. Approved Epic → Module breakdown
- **Epic 1 — Grounded Q&A** (former Phase 1; source: `PHASE_1_TECHNICAL_DESIGN.md` v0.3)
  1. M1 ingestion_pipeline — detect → extract(+spans) → chunk → embed → index (transactional)
  2. M2 local_storage — SQLite + sqlite-vec, schema, purge, encryption, index-meta
  3. M3 retrieval — embed query → doc-type filter → post-filter → abstain → assemble
  4. M4 grounded_answering — LLM grounding, decline-if-unsupported, numeric grounding, citations
  5. M5 safety — emergency pre-check (fail-closed) + framing post-check + recall gate
  6. M6 ocr — scanned-doc / image OCR path
  7. M7 classification — doc-type tagging + filtered retrieval
  8. M8 eval_harness — retrieval/citation/value/honesty/safety/OCR metrics
- **Epic 2 — First Actions: Calendar & Reminders** (former Phase 2; source: `PHASE_2_TECHNICAL_DESIGN.md`)
  1. M1 agent_foundations — orchestrator/planner, tool protocol, confirmation gate, action audit/idempotency, OAuth/secrets
  2. M2 calendar — Google Calendar (MCP, OAuth2)
  3. M3 reminders — device-bound reminders + fallback
  4. M4 profile_memory — single-profile preferences
  5. M5 eval — gate-enforcement + idempotency tests
- **Epic 3 — External Actions** (former Phase 3; source: `PHASE_3_TECHNICAL_DESIGN.md`)
  1. M1 assisted_handoff — handoff tool kind + financial-tier gate
  2. M2 email — Gmail draft/send
  3. M3 delivery — Instacart handoff + food delivery
  4. M4 pharmacy — CVS/Walgreens refill (direct-or-handoff)
  5. M5 secret_hardening — scope minimization, per-provider revocation
  6. M6 eval
- **Epic 4 — Health Portal & Proactive** (former Phase 4; source: `PHASE_4_TECHNICAL_DESIGN.md`)
  1. M1 fhir_read — Epic on FHIR / SMART OAuth2, USCDI read
  2. M2 fhir_to_retrieval — normalize FHIR → Epic-1 pipeline (connect-back)
  3. M3 scheduling — write-back (direct-or-handoff)
  4. M4 proactive_engine — triggers + local scheduler
  5. M5 proactive_consent — opt-in, deterministic disclaimer, quiet hours
  6. M6 eval

## 4. Per-epic doc skeleton (keep consistent; all bullets)
1. Header: epic name, "(former Phase N)", Status/Last-updated, "Builds on" links to prior epic docs.
2. Goals (numbered).
3. High-level architecture (keep the ASCII diagrams from the source docs).
4. Modules — one numbered `##` section each, with sub-bullets:
   - Purpose
   - Design/contract (port the v0.3 substance verbatim in meaning — do not drop any contract)
   - Data-model deltas (if any)
   - Tests / acceptance
5. Cross-cutting: Safety, Privacy & security (bullets).
6. What this epic excludes.
7. Build order (module sequence).
8. Repo layout (deltas).

## 5. Content rule
- **Preserve all substance** from the v0.3 phase docs — every decision, contract, and constraint (safety taxonomy & fail-closed rule, citation char spans, embed-dim validation, transactional ingest, purge contract, retrieval post-filter+abstain, encryption posture, numeric grounding, audit writer, assisted-handoff, financial gate, FHIR connect-back, proactive consent, etc.).
- Only the **structure** (phase→epic/module) and **format** (prose→bullets) change. This is not a redesign.

## 6. Cross-reference updates (do all)
1. `docs/PRD.md` §11 — relabel Phase 1–4 as Epic 1–4; point each to its new `Epic*.md` file.
2. `docs/OPEN_QUESTIONS.md` — update the `PHASE_*_TECHNICAL_DESIGN.md` links (#2 consent → Epic4_portal_and_proactive.md; any others) to the new epic docs.
3. `CLAUDE.md` — update the phase-doc-series links + wording (Phase→Epic) in "What this is".
4. `.claude/plan/phase-1-implementation.md` — update references from `PHASE_1_TECHNICAL_DESIGN.md` to `Epic1_grounded_qa.md`; keep its slices aligned to Epic-1 modules.
5. Inter-doc "Builds on" links inside the new epic docs.
6. Memory: update `phase-1-impl-readiness.md` wording (slice→module) and this file's pointer.

## 7. Old files
- After the 4 epic docs are written and links updated, `git rm` the 4 `PHASE_1..4_TECHNICAL_DESIGN.md` files.
- Verify no dangling references remain: `grep -rn "PHASE_[1-4]_TECHNICAL_DESIGN" docs/ CLAUDE.md .claude/` must return nothing.

## 8. Execution order (fresh session)
1. Re-read this plan + the 4 source `PHASE_*` docs.
2. Write `Epic1_grounded_qa.md` (map §3 components + §10 build order → M1–M8).
3. Write `Epic2_first_actions.md`, `Epic3_external_actions.md`, `Epic4_portal_and_proactive.md`.
4. Update all cross-refs (§6).
5. `git rm` old PHASE_* docs (§7) and run the grep check.
6. Final pass: confirm every doc is bullets/numbering only (no paragraphs).

## 9. Acceptance
1. 4 `Epic*.md` docs exist, module-sectioned, bullets-only.
2. No `PHASE_*_TECHNICAL_DESIGN` references anywhere; all links resolve.
3. No v0.3 contract/decision lost (spot-check safety, citations, purge, handoff, FHIR, proactive consent).
