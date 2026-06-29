# TaRa Health — Phase 2 Technical Design

**Phase 2 scope:** Tara's **first actions** — calendar and reminders. This is where
TaRa stops being read-only and starts *doing* things, always behind a confirmation
gate. Calendar + reminders are deliberately first because they are the lowest-risk
actions: no money moves and no PHI leaves the system beyond the event/reminder text
the user already supplied.

**Builds on:** [PHASE_1_TECHNICAL_DESIGN.md](PHASE_1_TECHNICAL_DESIGN.md) (ingestion,
retrieval, grounded answering, and — critically — the safety pre-check, which still
runs first on every turn).
**Introduces (reused by Phases 3–4):** the agent **orchestrator**, the **tool
protocol**, the **confirmation gate**, the **action audit + idempotency** layer, and
**OAuth/secret storage**. These foundations live here (§3.1–§3.5) because Phase 2 is
the first phase that needs them; later phases reference these sections rather than
re-specifying them.

**Status:** Draft v0.1
**Last updated:** 2026-06-28

> Source of truth for phasing is [PRD.md](PRD.md) §11. Open design questions live in
> [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). This is a design doc, not an implementation;
> contracts here are the spec the Phase 2 stubs should honor.

---

## 1. Goals

1. Introduce an **orchestrator** that, per turn, decides between grounded Q&A
   (Phase 1) and proposing an **action**.
2. Add a **tool layer** with a uniform contract, and wire the first two tools:
   **Google Calendar** (create/read events) and **Reminders** (medication,
   appointments, follow-ups).
3. Enforce a **hard confirmation gate**: no action with an external effect executes
   without an explicit user "yes" on a concrete preview.
4. Make actions **idempotent and auditable**: never double-book; log every action so
   the user can see what Tara did.
5. Keep everything **local-first** and **single-profile**, and keep the **safety
   layer in front of everything** — emergencies still short-circuit before any
   planning.

Success bar (UC-3): "I have a doctor's appointment on June 25, put it on my
calendar" → Tara shows a concrete event preview → user confirms → the event is
created exactly once → Tara reports success and offers prep help, with the action in
the audit log.

---

## 2. High-level architecture

Phase 2 wraps the Phase 1 query flow in an orchestrator and adds the action path.

```
   User turn ──▶ ┌──────────────────────────────┐
                 │  SAFETY / TRIAGE (pre-check)  │ ── emergency? ──▶ escalate, STOP
                 │   (Phase 1 §3.3, unchanged)   │
                 └───────────────┬──────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │            ORCHESTRATOR (planner)            │
                 │  perceive → plan → confirm → act → observe   │
                 └───────┬───────────────────────────┬─────────┘
              answer?    │                            │   action?
                         ▼                            ▼
            ┌────────────────────────┐   ┌───────────────────────────────┐
            │  Phase 1 ANSWERER      │   │  TOOL CALL (proposed)         │
            │  (grounded + cited)    │   │   → preview                   │
            └────────────────────────┘   └───────────────┬───────────────┘
                                                          ▼
                                          ┌───────────────────────────────┐
                                          │      CONFIRMATION GATE        │
                                          │  show preview → explicit YES  │ ──▶ no → cancel
                                          └───────────────┬───────────────┘
                                                          ▼
                                          ┌───────────────────────────────┐
                                          │  Tool.execute (idempotent)    │
                                          │  Calendar MCP / Reminders     │
                                          └───────────────┬───────────────┘
                                                          ▼
                                          ┌───────────────────────────────┐
                                          │  observe → report → AUDIT     │
                                          │  (actions table)              │
                                          └───────────────────────────────┘
```

---

## 3. Components

### 3.1 Orchestrator / planner (foundation)

The orchestrator runs the core agent loop — **perceive → plan → confirm → act →
observe** (README) — and is the new entry point for a turn. It does **not** replace
Phase 1; it *wraps* it.

- **Perceive.** Receives the user message and conversation state (single-profile
  memory, §3.6). The Phase 1 safety pre-check has already run upstream; the
  orchestrator never sees an emergency turn.
- **Plan.** A single LLM planning call (via the Phase 1 `LLMClient`, same
  local/hosted switch) decides the turn's shape, given the available tool schemas:
  - *Answer* → delegate to the Phase 1 answerer (grounded, cited). No gate.
  - *Act* → emit one or more **proposed** tool calls (tool name + arguments).
  - *Clarify* → ask the user a question (e.g., missing date).
- **Confirm / act / observe.** Proposed consequential tool calls go through the
  confirmation gate (§3.3); confirmed calls execute (§3.4) and their results are
  observed and reported, then audited (§3.5).

Phase 2 keeps plans **shallow** (single action or a short, linear sequence) — YAGNI
on multi-branch planning until a later phase needs it. The planner output is a
structured object (tool name, args), never free-text the executor has to parse.

### 3.2 Tool protocol (foundation)

A `Tool` is the action-layer analogue of Phase 1's `LLMClient` protocol seam: a
uniform abstraction so the orchestrator is decoupled from any specific integration,
and **local-vs-remote (MCP) is a config decision, not a code change** — mirroring
Phase 1's local/hosted model switch.

Contract (each tool provides):
- `name` and a JSON **parameter schema** (so the planner can target it and arguments
  can be validated at the boundary before anything executes).
- `consequential: bool` — whether a call has an external/financial effect and
  therefore must pass the confirmation gate. (Read-only calls, e.g. *read* calendar,
  may be exempt — configurable.)
- `preview(args) -> ActionPreview` — a **side-effect-free** human-readable
  description of exactly what will happen ("Create event 'Dr. Smith' on 2026-06-25
  10:00, calendar: Personal"). The gate shows this.
- `execute(args, idempotency_key) -> ActionResult` — performs the action; must be
  safe to retry with the same key (§3.5).

Tools are discovered from config (an allow-list), so enabling/disabling an
integration is configuration. A tool may be backed by a local implementation or by
an **MCP client** (§3.7); the orchestrator can't tell the difference.

### 3.3 Confirmation gate (foundation)

The hard guarantee from PRD §6.3/§9: **no consequential action without explicit
user approval.**

- A proposed consequential tool call is **never** executed inline by the planner. It
  is materialized as an `actions` row in `status='proposed'` with its `preview`.
- The gate presents the preview and requires an **explicit affirmative** ("yes",
  tap-to-confirm) — not mere absence of objection. Ambiguous or "maybe" → treated as
  no.
- On approval → `status='confirmed'`, then execute. On decline/timeout →
  `status='cancelled'`, nothing runs.
- The gate is **server-side and mandatory** — it is not a UI nicety the planner can
  skip. The executor refuses to run a consequential tool whose action row is not
  `confirmed`.

### 3.4 Tools wired in Phase 2

**a. Calendar (Google Calendar).** Create and read appointment events. Integration:
the **official Google Calendar remote MCP server** (OAuth 2.0) — the lowest-friction
path and the first concrete `Tool`/MCP wiring (PRD §7). Operations: `create_event`
(consequential → gated), `list_events` / `read_event` (read-only → exempt unless
config requires confirmation). Time-zone handling and an explicit calendar selection
are part of the preview.

**b. Reminders.** Medication, appointment, and follow-up reminders. Reminders are
**device-bound** — there is no universal cloud API (PRD §7). Phase 2 supports local
notifications and/or a Reminders MCP/automation where available, and **degrades
gracefully** to an in-app reminder when the OS path isn't available. The device-bound
limitation is recorded, not hidden.

### 3.5 Action audit + idempotency (foundation)

Every action is recorded and every consequential action is idempotent.

- **Audit.** The `actions` table (§4) records tool, arguments, preview, status, the
  result, and timestamps. It extends the Phase 1 `queries` audit log so the user has
  one place to see "what did Tara do?" (PRD §8 auditability).
- **Idempotency.** Each proposed action gets an `idempotency_key` (derived from the
  semantic content — e.g. calendar `create_event` keyed on title+start+calendar — so
  a retry of the *same* intent doesn't double-book). `execute` checks the key/status
  before acting; a key already `executed` is a no-op that returns the prior result.
  Where the provider supports its own idempotency token, pass it through.
- **Reliability (PRD §8).** "Actions must be idempotent or confirmable" — Phase 2
  delivers both: confirmable via the gate (§3.3), idempotent via the key.

### 3.6 Single-profile memory (lightweight)

PRD §6.4 calls for memory of the user profile, preferences, and past interactions —
single profile only. Phase 2 adds a minimal, local **profile/preferences** store
(e.g. default calendar, time zone, reminder lead time) so actions don't re-ask
settled facts. This is intentionally small (KISS); richer memory is deferred until a
phase needs it.

### 3.7 MCP client seam

Where an integration ships an MCP server (calendar, and later email), TaRa talks to
it through an **MCP client** wrapped behind the §3.2 `Tool` contract. MCP server
endpoints/credentials come from config. This keeps "which integration backs this
tool" a configuration concern and lets Phases 3–4 add MCP-backed tools without
touching the orchestrator.

---

## 4. Data model (deltas from Phase 1 §4)

```
actions                          -- audit + idempotency for every action
  action_id        (pk)
  turn_id          (fk -> a conversation turn / queries.query_id)
  tool_name        (calendar.create_event | reminders.create | ...)
  args             (json; validated against the tool's param schema)
  preview          (text shown at the gate)
  status           (proposed | confirmed | executed | failed | cancelled)
  idempotency_key  (unique per semantic intent; §3.5)
  result           (json; provider response or error, secrets redacted)
  created_at
  confirmed_at
  executed_at

oauth_tokens                     -- per-provider credentials, ENCRYPTED at rest
  provider         (google_calendar | ...)
  access_token     (encrypted with TARA_DB_KEY; never logged)
  refresh_token    (encrypted)
  expires_at
  scopes

profile                          -- single-profile preferences (§3.6)
  key              (default_calendar | timezone | reminder_lead_minutes | ...)
  value
```

Secrets handling: tokens are stored encrypted (reuse the Phase 1 `TARA_DB_KEY`
posture, §7); they are redacted from `actions.result`, logs, and any error surfaced
to the model.

---

## 5. Key flows

### 5.1 Action turn (UC-3: add appointment to calendar)
```
user turn → SAFETY pre-check (Phase 1 §3.3)
            ├─ emergency? → escalate, STOP
            └─ otherwise ↓
         → ORCHESTRATOR plans
            ├─ answer? → Phase 1 answerer (grounded + cited), done
            ├─ clarify? → ask user (e.g., which calendar / missing time)
            └─ act? ↓
         → build proposed action → validate args vs tool schema
         → write actions row (status=proposed, idempotency_key, preview)
         → CONFIRMATION GATE: show preview
            ├─ no / timeout → status=cancelled, STOP
            └─ yes ↓
         → status=confirmed → Tool.execute(args, idempotency_key)
            ├─ key already executed → return prior result (no double-book)
            ├─ provider/OAuth error → status=failed, report graceful message
            └─ success → status=executed, store result
         → observe → report to user ("Done — added to your calendar") + offer prep
         → audit (actions row finalized)
```

### 5.2 OAuth connect (first calendar use)
```
user enables Calendar → OAuth 2.0 consent (Google) → store access/refresh tokens
   (encrypted) in oauth_tokens → tool available
   (token refresh handled transparently; refresh failure → ask user to reconnect)
```

---

## 6. Safety & confirmation (Phase 2 specifics)

- The Phase 1 **safety pre-check runs first, unchanged** — actions never bypass it.
  An emergency turn never reaches the orchestrator.
- The **confirmation gate (§3.3) is the action-layer safety guarantee.** It is
  mandatory and server-enforced; the planner cannot self-approve.
- **No definitive promises** (PRD §6.5) still applies to any health framing in an
  action turn (e.g. when suggesting a calendar reminder for a symptom follow-up).
- Failures degrade gracefully and visibly — a failed action is reported as failed,
  never silently dropped, and never leaves a partial/duplicate effect (idempotency).

---

## 7. Privacy & security (Phase 2)

- **Local-first preserved.** Profile, preferences, audit, and tokens all live in the
  same on-device store as Phase 1.
- **Secrets.** OAuth tokens are encrypted at rest (reuse `TARA_DB_KEY`; §4), never
  logged, and redacted from model-visible context and `actions.result`.
- **Minimal external data.** A calendar/reminder action sends only the fields that
  action needs (title, time, calendar id) to the provider — not document content or
  the conversation.
- **Auditability (PRD §8).** Every action is logged and user-viewable, including
  what was sent to which provider.
- **New egress surface.** Unlike Phase 1 (where egress is only the optional hosted
  model), Phase 2 introduces provider egress (Google). This is opt-in per tool
  (enabling the integration + OAuth consent) and recorded in the audit log.

---

## 8. Testing & evaluation

- **Confirmation-gate enforcement (gate):** a consequential tool **cannot** execute
  without a `confirmed` action row. Attempt to execute `proposed`/`cancelled` → must
  refuse. This is a release gate.
- **Idempotency:** issuing the same `create_event` intent twice creates exactly one
  event; replay with the same key returns the prior result.
- **Planner routing:** Q&A turns go to the Phase 1 answerer (no gate); action turns
  produce a valid, schema-checked tool call; ambiguous turns clarify rather than
  guess.
- **OAuth lifecycle:** token refresh works; refresh failure prompts reconnect rather
  than crashing; missing/expired token never blocks the Q&A path.
- **Graceful failure:** provider/network error → `status=failed`, clear user
  message, no partial effect.
- **Safety precedence:** an emergency phrased as an action ("I'm having chest pain,
  remind me to call my doctor") still triggers the Phase 1 emergency short-circuit
  before any planning.

---

## 9. What Phase 2 deliberately excludes

- No email, delivery/commerce, or pharmacy actions — those are
  [PHASE_3_TECHNICAL_DESIGN.md](PHASE_3_TECHNICAL_DESIGN.md).
- No health-portal (FHIR) integration and no proactive behavior — those are
  [PHASE_4_TECHNICAL_DESIGN.md](PHASE_4_TECHNICAL_DESIGN.md). Tara still only acts
  when asked.
- No multi-step/branching plans beyond a short linear sequence (YAGNI).
- No multi-profile / multi-user (out of scope productwide).

---

## 10. Suggested build order within Phase 2

1. Orchestrator skeleton that wraps the Phase 1 flow: every turn still runs safety →
   answerer, but now through the planner (answer-only path first).
2. Tool protocol + the `actions` table + the confirmation gate, with one trivial
   read-only tool to exercise routing.
3. OAuth/token storage (encrypted) + Google Calendar MCP wiring; `list_events`
   (read-only) end to end.
4. `create_event` (consequential) through the gate, with idempotency — the UC-3 flow.
5. Reminders tool (local notifications + graceful degradation).
6. Single-profile preferences (default calendar, timezone, lead time).
7. Tests/evals (§8), gating the confirmation-gate and idempotency guarantees.

---

## 11. Repository layout (deltas from Phase 1 §11)

```
src/tara/
├── agent/                 # NEW: orchestrator/planner loop + confirmation gate (§3.1, §3.3)
│   ├── orchestrator.py    #   perceive→plan→confirm→act→observe
│   ├── planner.py         #   LLM planning call → structured tool calls
│   └── confirmation.py    #   server-side gate (proposed→confirmed→execute)
├── tools/                 # NEW: tool protocol + integrations (§3.2, §3.4, §3.7)
│   ├── base.py            #   Tool protocol (name, schema, consequential, preview, execute)
│   ├── mcp_client.py      #   MCP client seam (§3.7)
│   ├── calendar.py        #   Google Calendar (MCP, OAuth2)
│   └── reminders.py       #   device-bound reminders + graceful fallback
├── storage/               # +actions, +oauth_tokens, +profile tables (§4); encrypted secrets
├── answering/             # unchanged (Phase 1) — orchestrator delegates here for Q&A
└── safety/                # unchanged (Phase 1) — runs before the orchestrator
```

Config additions (all `TARA_`-prefixed, per Phase 1's central-config rule): an
actions enable/allow-list, Google OAuth client credentials + MCP endpoint, default
timezone/calendar. No provider or endpoint is hard-coded — enabling an integration is
configuration.
