# TaRa Health — Phase 4 Technical Design

**Phase 4 scope:** **Health-portal integration** (Epic on FHIR / MyChart) and
**proactive help**. Two firsts: Tara reads structured clinical data directly from the
user's provider (then, later, writes back appointment scheduling), and Tara begins
to act **unprompted** — preparing for upcoming visits and following up afterward.
Both are powerful and both raise new consent/safety surfaces, so Phase 4 is as much
about *guardrails on proactivity* as about the integration.

**Builds on:** [PHASE_1_TECHNICAL_DESIGN.md](PHASE_1_TECHNICAL_DESIGN.md) (ingestion,
retrieval, grounded+cited answering, safety pre-check) and
[PHASE_2_TECHNICAL_DESIGN.md](PHASE_2_TECHNICAL_DESIGN.md) /
[PHASE_3_TECHNICAL_DESIGN.md](PHASE_3_TECHNICAL_DESIGN.md). Reused unchanged:
- **Orchestrator/planner**, **tool protocol**, **confirmation gate**, **action audit
  + idempotency**, **OAuth/secret storage** (Phase 2 §3.1–§3.5, §4, §7).
- **Assisted-handoff** tool kind and **financial/heightened confirmation** (Phase 3
  §3.1, §3.3) — reused for scheduling where direct write-back isn't available.
- **Phase 1 retrieval + citations** — FHIR-sourced facts flow back into the same
  grounded-answer pipeline so they can be cited like any document.

Phase 4 adds: the **FHIR read→write integration** (§3.1–§3.2), **FHIR data
re-entering the Phase 1 pipeline** (§3.3), and the **proactive engine** with its own
**consent surface** (§3.4–§3.5).

**Status:** Draft v0.1
**Last updated:** 2026-06-28

> Source of truth for phasing is [PRD.md](PRD.md) §11. Phase 4 settles the former
> provider-portal open question (read-first FHIR + assisted-handoff scheduling;
> decision recorded in §3.1–§3.2) and touches the consent-flow question
> ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) #2).

---

## 1. Goals

1. Connect to the user's provider via **Epic on FHIR / SMART on FHIR** (OAuth 2.0,
   patient auth through MyChart) and **read** their clinical record (USCDI:
   conditions, medications, labs, allergies, appointments).
2. Feed that structured data back into the **Phase 1 retrieval pipeline** so Q&A can
   ground answers on portal data with citations (UC-4/UC-5 get richer).
3. Add **appointment scheduling write-back** — read-first, scheduling later —
   through the confirmation gate, with **assisted handoff** where Epic write access
   isn't granted (§3.2).
4. Introduce **proactive help** — visit prep and follow-ups — the first time Tara
   acts without being asked, behind an explicit **opt-in consent** surface and a
   deterministic disclaimer.
5. Preserve every prior guarantee: local-first, single-profile, safety-first,
   confirmation-gated actions, full auditability.

Success bar: with MyChart connected, "What were the results of my last blood test?"
(UC-5) answers from FHIR-sourced labs **with a citation**; an upcoming appointment
triggers a proactive, opted-in, clearly-disclaimed prep nudge; and booking a visit
(UC-2) goes through the gate (direct write-back or handoff) exactly once.

---

## 2. High-level architecture

```
   MyChart / Epic ──(SMART on FHIR, OAuth2 patient auth)──▶ FHIR READ (USCDI)
            │                                                     │
            │                                       normalize → ingest into
            │                                       Phase 1 retrieval (cited)
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

The action loop (safety → orchestrator → plan → confirm → act → observe) is
unchanged; Phase 4 adds a new *source* of turns (proactive triggers) and a new tool
(health portal). **Proactive triggers enter the same loop** — they never bypass
safety or the gate.

---

## 3. Components

### 3.1 Health-portal integration — Epic on FHIR (read first)

- **Auth:** SMART on FHIR / OAuth 2.0, patient-facing authorization through MyChart.
  A **free sandbox with test patients** exists for development; **production access
  requires Epic's app review** (PRD §7). The design assumes sandbox during
  build and treats production approval as a gating external dependency.
- **Read scope (USCDI):** conditions, medications, allergies, lab results,
  immunizations, and appointments. Read is the easy, high-value path and is built
  first.
- **Tool shape:** a `health_portal` tool on the Phase 2 `Tool` contract. Read
  operations are side-effect-free (no gate). Tokens use the Phase 2 encrypted
  `oauth_tokens` store (new `epic` provider, minimized scopes per Phase 3 §3.4).

### 3.2 Scheduling write-back (read-first, then write)

- Write-back (booking/rescheduling) is **heavier** than read and may not be granted
  (PRD §7). Therefore scheduling is **direct-or-handoff** (Phase 3 §3.1):
  `book_appointment` executes directly where Epic write access is provisioned,
  otherwise **falls back to assisted handoff** (deep link into MyChart scheduling).
- Consequential → **confirmation gate** (Phase 2 §3.3). Idempotent (Phase 2 §3.5) so
  a retry never double-books. This is the resolved provider-portal stance: "read-only FHIR +
  assisted handoff for scheduling, defer full automated booking" — yes, by default.

### 3.3 FHIR data → Phase 1 retrieval (the connect-back)

Portal data is only useful if Tara can answer over it **with citations**. Phase 4
normalizes FHIR resources into the Phase 1 stores so they're first-class retrievable
content:
- Each relevant FHIR resource (a lab result, a medication, a condition) is rendered
  into a **canonical text record** and ingested via the Phase 1 pipeline as a
  document of a new `doc_type` (`fhir_record`), with provenance
  `source='fhir'`, the FHIR resource type/id, and the retrieval date.
- These records get chunks, embeddings, and **citations** like any uploaded document
  — so UC-5 ("my last blood test") cites the FHIR-sourced lab, and the §3.5-P1
  numeric-grounding check still applies to portal values.
- **Provenance & freshness:** citations distinguish portal-sourced facts ("from
  MyChart, retrieved 2026-06-20") from uploaded-document facts, and stale FHIR data
  can be refreshed/re-ingested idempotently (Phase 1 §3.1f).

This keeps a single answering path: portal data and uploaded documents are unified in
retrieval rather than answered by a separate code path.

### 3.4 Proactive engine

The first time Tara acts unprompted (PRD §11 Phase 4; README "proactive prep and
follow-ups"). Structure:
- **Triggers.** Time/event-based: an upcoming appointment (from calendar or FHIR) →
  *prep* suggestion; a recent visit/after-visit summary → *follow-up*; a medication
  due → *refill reminder* (ties to Phase 3 pharmacy). Triggers are evaluated by a
  local scheduler; no always-on cloud service.
- **Generation.** A proactive item is generated grounded in the user's data (Phase 1
  answerer + retrieval), so prep/follow-up content is cited and honest, not generic.
- **Delivery.** Informational nudges are delivered via consented channels (in-app +,
  from Phase 2/3, calendar/email). Anything that *acts* (book, order, refill) is a
  proposed action and **still goes through the confirmation gate** — proactive ≠
  autonomous; Tara suggests, the user approves.

### 3.5 Proactive consent & safety surface (new)

Acting unprompted demands explicit, revocable consent and stronger framing:
- **Opt-in consent.** Proactivity is **off by default**. The user opts in, by
  category (visit prep / follow-ups / refill reminders), and can revoke any category.
  Stored in `profile` (single-profile). Relates to OPEN_QUESTIONS.md #2 (consent flow).
- **Deterministic disclaimer.** Every proactive health nudge carries a **fixed,
  non-model disclaimer** (general information, not a diagnosis) — not a
  model-generated one — so the framing guarantee doesn't depend on generation. This
  strengthens the Phase 1 framing concern for the unprompted case.
- **Frequency & quiet hours.** Rate limits and quiet-hours windows prevent nagging;
  configurable.
- **Safety precedence.** Proactive content is still health output: it runs through
  the safety framing rules, never diagnoses, and proactive triggers never produce an
  emergency-bypassing action. An emergency is never something Tara "reminds" about —
  it's the Phase 1 short-circuit.

---

## 4. Data model (deltas from Phases 1–3)

```
documents (extends Phase 1)
  doc_type          -- add: fhir_record
  source            -- uploaded | fhir            (provenance; §3.3)
  source_ref        -- FHIR resourceType/id when source=fhir
  retrieved_at      -- freshness for portal data

oauth_tokens (extends Phase 2)
  provider          -- add: epic (SMART on FHIR; minimized scopes)

proactive_subscriptions          -- what the user opted into (§3.5)
  category          (visit_prep | follow_up | refill_reminder)
  enabled           (bool; off by default)
  quiet_hours / frequency settings

proactive_items                  -- log of proactive nudges (audit)
  item_id           (pk)
  category
  trigger_ref       (appointment id / visit / medication)
  content           (grounded + cited)
  delivered_at / channel
  resulting_action_id  (fk -> actions, if the user acted; nullable)

profile (extends Phase 2/3)
  proactive_consent per category; channel preferences; quiet hours
```

FHIR-sourced records reuse the Phase 1 `chunks`/`vec_chunks` stores (they're just
documents with `source='fhir'`), so retrieval/citation/purge all work unchanged.

---

## 5. Key flows

### 5.1 Connect MyChart + read (USCDI → retrieval)
```
user connects MyChart → SMART on FHIR OAuth2 (patient auth) → store epic tokens (encrypted)
  → read USCDI resources → normalize to canonical text (doc_type=fhir_record, source=fhir)
  → Phase 1 ingest (chunk → embed → index)  → now citable in Q&A
  (refresh = idempotent re-ingest; §3.1f P1)
```

### 5.2 Answer over portal data (UC-5)
```
"my last blood test results?" → safety → retrieve (incl. fhir_record chunks)
  → grounded answer + numeric-grounding check (P1 §3.5)
  → cite "MyChart lab, retrieved <date>" → done
```

### 5.3 Schedule a visit (UC-2, direct-or-handoff)
```
turn → safety → orchestrator → plan: book_appointment
  → CONFIRMATION GATE (date/time/provider preview)
     ├─ no → cancelled
     └─ yes → book_appointment.execute if Epic write provisioned
                 ├─ success → status=executed (idempotent; no double-book)
                 └─ not granted → FALL BACK to MyChart scheduling handoff (status=handed_off)
  → report + audit
```

### 5.4 Proactive visit prep (opt-in)
```
scheduler: appointment in N days AND user opted into visit_prep AND not quiet hours
  → generate grounded prep (retrieval + answerer) + deterministic disclaimer
  → deliver nudge (consented channel) → log proactive_items
  → if it proposes an action (e.g., add prep reminder) → CONFIRMATION GATE as usual
```

---

## 6. Safety & confirmation (Phase 4 specifics)

- **Safety pre-check first**, including on proactive-generated content.
- **Proactivity is consented and bounded** (§3.5): off by default, per-category
  opt-in, revocable, rate-limited, quiet-hours-aware, deterministically disclaimed.
- **Proactive never auto-acts.** Suggestions that act go through the confirmation
  gate; proactivity changes *who initiates the turn*, not *who approves the action*.
- **Scheduling is gated + idempotent**, with handoff fallback (no double-booking,
  no booking without an explicit yes).
- **Portal data honesty.** FHIR values are subject to the same numeric-grounding and
  citation rules as documents; freshness is shown so stale data isn't presented as
  current.

---

## 7. Privacy & security (Phase 4)

- **Most sensitive integration yet.** The full clinical record now flows in. It is
  ingested into the **local** stores (Phase 1), encrypted at rest when `TARA_DB_KEY`
  is set (Phase 2 §7), and never leaves the device except the minimal context to a
  hosted answering model if the user opted into `hosted`/`hybrid` (Phase 1 §3.5).
- **Epic tokens** stored encrypted, minimized scopes, per-provider revocation (Phase
  3 §3.4); disconnecting MyChart purges tokens and (per policy) the imported
  `fhir_record` documents.
- **Proactive = new egress/notification surface.** Consent governs whether Tara may
  message unprompted and through which channel; each proactive item is audited.
- **Auditability (PRD §8).** FHIR reads, scheduling write-backs, and every proactive
  item are logged and user-viewable.
- **Regulatory awareness (PRD §8).** Provider integration sharpens HIPAA
  considerations; the local-first, minimized-egress, audited posture is the
  mitigation, and productization triggers remain tracked in OPEN_QUESTIONS.md #3.

---

## 8. Testing & evaluation

- **FHIR read + citation:** USCDI resources normalize and become retrievable; a
  portal-sourced fact is answered **with a citation** and passes numeric grounding.
- **Scheduling gate + idempotency (release gate):** no booking without explicit
  confirmation; a repeated booking intent never double-books; direct→handoff fallback
  works when write access isn't granted.
- **Proactive consent (release gate):** **no proactive message is sent unless the
  user opted into that category**; revocation and quiet hours are honored.
- **Proactive groundedness & framing:** proactive health content is cited, honest,
  carries the deterministic disclaimer, never diagnoses.
- **Proactive action still gated:** a proactive suggestion that acts requires gate
  confirmation like any other action.
- **Freshness/provenance:** stale FHIR data is refreshable and is labeled with its
  retrieval date; uploaded vs. portal provenance is distinguishable in citations.
- **Safety precedence:** safety pre-check runs on proactive and portal-driven turns.

---

## 9. What Phase 4 deliberately excludes

- **No real-time biometric / wearable monitoring** (PRD §3 non-goal).
- **No multi-user / caregiver** access (productwide non-goal).
- **No fully-autonomous consequential action** — proactivity never removes the
  confirmation gate.
- **Full automated booking** only where Epic production write access is granted;
  otherwise assisted handoff (the deliberate resolved stance).
- Phase 4 is the last roadmap phase (PRD §11). Beyond it, productization questions
  (HIPAA, hosting, licensing, multi-user) live in OPEN_QUESTIONS.md #3, not in this design.

---

## 10. Suggested build order within Phase 4

1. SMART on FHIR OAuth2 + sandbox connection; read one USCDI resource end to end.
2. Normalize FHIR → canonical text → Phase 1 ingest (`doc_type=fhir_record`); make
   it retrievable and citable (UC-5).
3. Broaden USCDI read coverage (conditions, meds, allergies, appointments) +
   freshness/refresh.
4. Scheduling write-back as direct-or-handoff through the gate (UC-2), idempotent.
5. Proactive engine skeleton: triggers + local scheduler, **consent off by default**.
6. Proactive consent surface (§3.5): per-category opt-in, deterministic disclaimer,
   quiet hours, audit.
7. Proactive prep + follow-up generators (grounded, cited).
8. Tests/evals (§8), gating scheduling confirmation/idempotency and proactive
   consent.

---

## 11. Repository layout (deltas from Phases 1–3)

```
src/tara/
├── tools/
│   └── health_portal.py   # NEW: Epic on FHIR (SMART OAuth2) read + scheduling write-back/handoff
├── ingestion/
│   └── fhir.py            # NEW: normalize FHIR resources → canonical text → Phase 1 pipeline (§3.3)
├── proactive/             # NEW: proactive engine (§3.4–§3.5)
│   ├── triggers.py        #   visit-prep / follow-up / refill trigger evaluation
│   ├── scheduler.py       #   local scheduler (no always-on cloud)
│   └── consent.py         #   per-category opt-in, quiet hours, deterministic disclaimer
├── storage/               # EXTEND documents (source/source_ref/retrieved_at, fhir_record);
│                          #   oauth_tokens +epic; +proactive_subscriptions/+proactive_items;
│                          #   profile +proactive consent
└── (orchestrator, confirmation gate, answering, safety, retrieval reused unchanged)
```

Config additions (all `TARA_`-prefixed): Epic/SMART client credentials + FHIR base
URL (sandbox vs. production), proactive enable + default-off consent, quiet-hours and
frequency defaults. As always, integrations and endpoints are configuration, not
code.
