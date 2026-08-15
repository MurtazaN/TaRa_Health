# TaRa Health — Epic 4: Health Portal & Proactive *(former Phase 4)*

- **Epic 4 scope:** **health-portal integration** (Epic on FHIR / MyChart) and **proactive help**.
- Two firsts:
  - Tara reads structured clinical data directly from the user's provider (then, later, writes back appointment scheduling).
  - Tara begins to act **unprompted** — preparing for upcoming visits and following up afterward.
- Both are powerful and both raise new consent/safety surfaces — Epic 4 is as much about *guardrails on proactivity* as about the integration.
- **Builds on:** [epic1_grounded_qa/](epic1_grounded_qa/README.md) (ingestion, retrieval, grounded+cited answering, safety pre-check) and [Epic2_first_actions.md](Epic2_first_actions.md) / [Epic3_external_actions.md](Epic3_external_actions.md). Reused unchanged:
  - **Orchestrator/planner, tool protocol, confirmation gate, action audit + idempotency, OAuth/secret storage** (Epic 2 M1).
  - **Assisted-handoff** tool kind and **financial/heightened confirmation** (Epic 3 M1) — reused for scheduling where direct write-back isn't available.
  - **Epic 1 retrieval + citations** — FHIR-sourced facts flow back into the same grounded-answer pipeline so they can be cited like any document.
- Epic 4 adds: the **FHIR read→write integration** (M1, M3), **FHIR data re-entering the Epic 1 pipeline** (M2), and the **proactive engine** with its own **consent surface** (M4, M5).
- **Status:** Draft v0.1 (content), restructured Phase→Epic / Modules 2026-07-07.
- **Last updated:** 2026-07-07.
- **Modules in this epic:** M1 fhir_read · M2 fhir_to_retrieval · M3 scheduling · M4 proactive_engine · M5 proactive_consent · M6 eval.
- Source of truth for the roadmap is [PRD.md](PRD.md) §11.
- Epic 4 settles the former provider-portal open question (read-first FHIR + assisted-handoff scheduling; decision recorded in M1/M3) and touches the consent-flow question ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) #2).

---

## 1. Goals

1. Connect to the user's provider via **Epic on FHIR / SMART on FHIR** (OAuth 2.0, patient auth through MyChart) and **read** their clinical record (USCDI: conditions, medications, labs, allergies, appointments).
2. Feed that structured data back into the **Epic 1 retrieval pipeline** so Q&A can ground answers on portal data with citations (UC-4/UC-5 get richer).
3. Add **appointment scheduling write-back** — read-first, scheduling later — through the confirmation gate, with **assisted handoff** where Epic write access isn't granted.
4. Introduce **proactive help** — visit prep and follow-ups — the first time Tara acts without being asked, behind an explicit **opt-in consent** surface and a deterministic disclaimer.
5. Preserve every prior guarantee: local-first, single-profile, safety-first, confirmation-gated actions, full auditability.

- **Success bar:**
  - With MyChart connected, "What were the results of my last blood test?" (UC-5) answers from FHIR-sourced labs **with a citation**.
  - An upcoming appointment triggers a proactive, opted-in, clearly-disclaimed prep nudge.
  - Booking a visit (UC-2) goes through the gate (direct write-back or handoff) exactly once.

---

## 2. High-level architecture

```
   MyChart / Epic ──(SMART on FHIR, OAuth2 patient auth)──▶ FHIR READ (USCDI)
            │                                                     │
            │                                       normalize → ingest into
            │                                       Epic 1 retrieval (cited)
            ▼                                                     ▼
   FHIR WRITE-BACK (scheduling)                      grounded Q&A over portal + docs
   via confirmation gate                                         │
   (direct or assisted handoff)                                  │
                                                                 │
   PROACTIVE ENGINE ── trigger (visit soon / post-visit) ───────┘
        │  (only if user opted in; quiet hours respected)
        ▼
   generate suggestion → deterministic disclaimer
        ├─ informational nudge → notify (consented)
        └─ proposes an action → still goes through the CONFIRMATION GATE
```

- The action loop (safety → orchestrator → plan → confirm → act → observe) is unchanged.
- Epic 4 adds a new *source* of turns (proactive triggers) and a new tool (health portal).
- **Proactive triggers enter the same loop** — they never bypass safety or the gate.

---

## M1 — fhir_read

- **Purpose:** connect to Epic on FHIR (SMART OAuth2 via MyChart) and read the USCDI clinical record.

### Design / contract

- **Auth:** SMART on FHIR / OAuth 2.0, patient-facing authorization through MyChart.
  - A **free sandbox with test patients** exists for development; **production access requires Epic's app review** (PRD §7).
  - The design assumes sandbox during build and treats production approval as a gating external dependency.
- **Read scope (USCDI):** conditions, medications, allergies, lab results, immunizations, and appointments — read is the easy, high-value path and is built first.
- **Tool shape:** a `health_portal` tool on the Epic 2 M1 `Tool` contract.
  - Read operations are side-effect-free (no gate).
  - Tokens use the Epic 2 encrypted `oauth_tokens` store (new `epic` provider, minimized scopes per Epic 3 M5).

### Data-model deltas

```
oauth_tokens (extends Epic 2)
  provider          -- add: epic (SMART on FHIR; minimized scopes)
```

### Tests / acceptance

- Sandbox connect + read of one USCDI resource end to end; tokens encrypted; scopes minimized.

---

## M2 — fhir_to_retrieval

- **Purpose:** the connect-back — normalize FHIR resources into the Epic 1 stores so portal data is first-class retrievable, citable content.

### Design / contract

- Portal data is only useful if Tara can answer over it **with citations**; therefore:
  - Each relevant FHIR resource (a lab result, a medication, a condition) is rendered into a **canonical text record** and ingested via the Epic 1 pipeline as a document of a new `doc_type` (`fhir_record`), with provenance `source='fhir'`, the FHIR resource type/id, and the retrieval date.
  - These records get chunks, embeddings, and **citations** like any uploaded document — UC-5 ("my last blood test") cites the FHIR-sourced lab, and the Epic 1 M4 numeric-grounding check still applies to portal values.
- **Provenance & freshness:**
  - Citations distinguish portal-sourced facts ("from MyChart, retrieved 2026-06-20") from uploaded-document facts.
  - Stale FHIR data can be refreshed/re-ingested idempotently (Epic 1 M1 dedup/replace contract).
- Keeps a **single answering path**: portal data and uploaded documents are unified in retrieval rather than answered by a separate code path.

### Key flows

```
user connects MyChart → SMART on FHIR OAuth2 (patient auth) → store epic tokens (encrypted)
  → read USCDI resources → normalize to canonical text (doc_type=fhir_record, source=fhir)
  → Epic 1 ingest (chunk → embed → index)  → now citable in Q&A
  (refresh = idempotent re-ingest; Epic 1 M1)
```

```
"my last blood test results?" → safety → retrieve (incl. fhir_record chunks)
  → grounded answer + numeric-grounding check (Epic 1 M4)
  → cite "MyChart lab, retrieved <date>" → done
```

### Data-model deltas

```
documents (extends Epic 1)
  doc_type          -- add: fhir_record
  source            -- uploaded | fhir            (provenance)
  source_ref        -- FHIR resourceType/id when source=fhir
  retrieved_at      -- freshness for portal data
```

- FHIR-sourced records reuse the Epic 1 `chunks`/`vec_chunks` stores (they're just documents with `source='fhir'`), so retrieval/citation/purge all work unchanged.

### Tests / acceptance

- USCDI resources normalize and become retrievable; a portal-sourced fact is answered **with a citation** and passes numeric grounding.
- Stale FHIR data is refreshable; uploaded vs. portal provenance is distinguishable in citations, labeled with retrieval date.

---

## M3 — scheduling

- **Purpose:** appointment scheduling write-back (read-first, then write) as direct-or-handoff through the gate.

### Design / contract

- Write-back (booking/rescheduling) is **heavier** than read and may not be granted (PRD §7); therefore scheduling is **direct-or-handoff** (Epic 3 M1):
  - `book_appointment` executes directly where Epic write access is provisioned.
  - Otherwise it **falls back to assisted handoff** (deep link into MyChart scheduling).
- Consequential → **confirmation gate** (Epic 2 M1); idempotent so a retry never double-books.
- This is the resolved provider-portal stance: "read-only FHIR + assisted handoff for scheduling, defer full automated booking" — yes, by default.

### Key flow (UC-2, direct-or-handoff)

```
turn → safety → orchestrator → plan: book_appointment
  → CONFIRMATION GATE (date/time/provider preview)
     ├─ no → cancelled
     └─ yes → book_appointment.execute if Epic write provisioned
                 ├─ success → status=executed (idempotent; no double-book)
                 └─ not granted → FALL BACK to MyChart scheduling handoff (status=handed_off)
  → report + audit
```

### Data-model deltas

- None beyond the Epic 3 `actions` fields (`execution_kind`, `handed_off`).

### Tests / acceptance

- **Release gate:** no booking without explicit confirmation; a repeated booking intent never double-books; direct→handoff fallback works when write access isn't granted.

---

## M4 — proactive_engine

- **Purpose:** the first time Tara acts unprompted — triggers + local scheduler + grounded generation + consented delivery.

### Design / contract

- **Triggers.** Time/event-based, evaluated by a **local scheduler** (no always-on cloud service):
  - Upcoming appointment (from calendar or FHIR) → *prep* suggestion.
  - Recent visit / after-visit summary → *follow-up*.
  - Medication due → *refill reminder* (ties to Epic 3 pharmacy, M4 of Epic 3).
- **Generation.** A proactive item is generated grounded in the user's data (Epic 1 answerer + retrieval) — prep/follow-up content is cited and honest, not generic.
- **Delivery.**
  - Informational nudges go via consented channels (in-app +, from Epics 2/3, calendar/email).
  - Anything that *acts* (book, order, refill) is a proposed action and **still goes through the confirmation gate** — proactive ≠ autonomous; Tara suggests, the user approves.

### Key flow (proactive visit prep, opt-in)

```
scheduler: appointment in N days AND user opted into visit_prep AND not quiet hours
  → generate grounded prep (retrieval + answerer) + deterministic disclaimer
  → deliver nudge (consented channel) → log proactive_items
  → if it proposes an action (e.g., add prep reminder) → CONFIRMATION GATE as usual
```

### Data-model deltas

```
proactive_items                  -- log of proactive nudges (audit)
  item_id           (pk)
  category
  trigger_ref       (appointment id / visit / medication)
  content           (grounded + cited)
  delivered_at / channel
  resulting_action_id  (fk -> actions, if the user acted; nullable)
```

### Tests / acceptance

- Proactive content is cited, honest, and grounded; a proactive suggestion that acts requires gate confirmation like any other action.

---

## M5 — proactive_consent

- **Purpose:** the consent & safety surface for acting unprompted — opt-in, deterministic disclaimer, quiet hours, revocability.

### Design / contract

- **Opt-in consent:**
  - Proactivity is **off by default**.
  - The user opts in **by category** (visit prep / follow-ups / refill reminders) and can revoke any category.
  - Stored in `profile` (single-profile); relates to OPEN_QUESTIONS.md #2 (consent flow).
- **Deterministic disclaimer:**
  - Every proactive health nudge carries a **fixed, non-model disclaimer** (general information, not a diagnosis) — not a model-generated one — so the framing guarantee doesn't depend on generation.
  - Strengthens the Epic 1 framing concern for the unprompted case.
- **Frequency & quiet hours:** rate limits and quiet-hours windows prevent nagging; configurable.
- **Safety precedence:**
  - Proactive content is still health output: it runs through the safety framing rules, never diagnoses, and proactive triggers never produce an emergency-bypassing action.
  - An emergency is never something Tara "reminds" about — it's the Epic 1 short-circuit.

### Data-model deltas

```
proactive_subscriptions          -- what the user opted into
  category          (visit_prep | follow_up | refill_reminder)
  enabled           (bool; off by default)
  quiet_hours / frequency settings

profile (extends Epics 2/3)
  proactive_consent per category; channel preferences; quiet hours
```

### Tests / acceptance

- **Release gate:** **no proactive message is sent unless the user opted into that category**; revocation and quiet hours are honored.

---

## M6 — eval

- **Purpose:** tests/evals gating the Epic 4 guarantees.

### Design / contract (test battery)

- **FHIR read + citation:** USCDI resources normalize and become retrievable; a portal-sourced fact is answered **with a citation** and passes numeric grounding (M1/M2).
- **Scheduling gate + idempotency (release gate):** no booking without explicit confirmation; repeated booking intent never double-books; direct→handoff fallback works when write access isn't granted (M3).
- **Proactive consent (release gate):** no proactive message without category opt-in; revocation and quiet hours honored (M5).
- **Proactive groundedness & framing:** proactive health content is cited, honest, carries the deterministic disclaimer, never diagnoses (M4/M5).
- **Proactive action still gated:** a proactive suggestion that acts requires gate confirmation like any other action (M4).
- **Freshness/provenance:** stale FHIR data is refreshable and labeled with its retrieval date; uploaded vs. portal provenance distinguishable in citations (M2).
- **Safety precedence:** safety pre-check runs on proactive and portal-driven turns (Epic 1 M5).

---

## Cross-cutting: Safety, Privacy & security

- **Safety & confirmation:**
  - **Safety pre-check first**, including on proactive-generated content.
  - **Proactivity is consented and bounded** (M5): off by default, per-category opt-in, revocable, rate-limited, quiet-hours-aware, deterministically disclaimed.
  - **Proactive never auto-acts:** suggestions that act go through the confirmation gate; proactivity changes *who initiates the turn*, not *who approves the action*.
  - **Scheduling is gated + idempotent**, with handoff fallback (no double-booking, no booking without an explicit yes).
  - **Portal data honesty:** FHIR values are subject to the same numeric-grounding and citation rules as documents; freshness is shown so stale data isn't presented as current.
- **Privacy & security:**
  - **Most sensitive integration yet:** the full clinical record now flows in; it is ingested into the **local** stores (Epic 1), encrypted at rest when `TARA_DB_KEY` is set (Epic 2 posture), and never leaves the device except the minimal context to a hosted answering model if the user opted into `hosted`/`hybrid` (Epic 1 M4).
  - **Epic tokens:** stored encrypted, minimized scopes, per-provider revocation (Epic 3 M5); disconnecting MyChart purges tokens and (per policy) the imported `fhir_record` documents.
  - **Proactive = new egress/notification surface:** consent governs whether Tara may message unprompted and through which channel; each proactive item is audited.
  - **Auditability (PRD §8):** FHIR reads, scheduling write-backs, and every proactive item are logged and user-viewable.
  - **Regulatory awareness (PRD §8):** provider integration sharpens HIPAA considerations; the local-first, minimized-egress, audited posture is the mitigation; productization triggers remain tracked in OPEN_QUESTIONS.md #3.

---

## What this epic excludes

- **No real-time biometric / wearable monitoring** (PRD §3 non-goal).
- **No multi-user / caregiver** access (productwide non-goal).
- **No fully-autonomous consequential action** — proactivity never removes the confirmation gate.
- **Full automated booking** only where Epic production write access is granted; otherwise assisted handoff (the deliberate resolved stance).
- Epic 4 is the last roadmap epic (PRD §11); beyond it, productization questions (HIPAA, hosting, licensing, multi-user) live in OPEN_QUESTIONS.md #3, not in this design.

---

## Build order (module sequence)

1. **M1:** SMART on FHIR OAuth2 + sandbox connection; read one USCDI resource end to end.
2. **M2:** normalize FHIR → canonical text → Epic 1 ingest (`doc_type=fhir_record`); make it retrievable and citable (UC-5).
3. **M1/M2:** broaden USCDI read coverage (conditions, meds, allergies, appointments) + freshness/refresh.
4. **M3:** scheduling write-back as direct-or-handoff through the gate (UC-2), idempotent.
5. **M4:** proactive engine skeleton — triggers + local scheduler, **consent off by default**.
6. **M5:** proactive consent surface — per-category opt-in, deterministic disclaimer, quiet hours, audit.
7. **M4:** proactive prep + follow-up generators (grounded, cited).
8. **M6:** tests/evals, gating scheduling confirmation/idempotency and proactive consent.

---

## Repository layout (deltas from Epics 1–3)

- Names follow the settled Epic 1/2 conventions (`agent_tools/`, `document_ingestion/`, `local_data_stores/`).

```
backend/src/tara/
├── agent_tools/
│   └── health_portal.py         # NEW: Epic on FHIR (SMART OAuth2) read + scheduling write-back/handoff (M1, M3)
├── document_ingestion/
│   └── fhir_normalization.py    # NEW: normalize FHIR resources → canonical text → Epic 1 pipeline (M2)
├── proactive_engine/            # NEW: proactive engine + consent (M4–M5)
│   ├── trigger_evaluation.py    #   visit-prep / follow-up / refill trigger evaluation
│   ├── local_scheduler.py       #   local scheduler (no always-on cloud)
│   └── proactive_consent.py     #   per-category opt-in, quiet hours, deterministic disclaimer
├── local_data_stores/           # EXTEND documents (source/source_ref/retrieved_at, fhir_record);
│                                #   oauth_tokens +epic; +proactive_subscriptions/+proactive_items;
│                                #   profile +proactive consent
└── (orchestrator, confirmation gate, answering, safety, retrieval reused unchanged)
```

- Config additions (all `TARA_`-prefixed): Epic/SMART client credentials + FHIR base URL (sandbox vs. production), proactive enable + default-off consent, quiet-hours and frequency defaults.
- As always, integrations and endpoints are configuration, not code.
