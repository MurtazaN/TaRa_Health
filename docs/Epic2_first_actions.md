# TaRa Health — Epic 2: First Actions — Calendar & Reminders *(former Phase 2)*

- **Epic 2 scope:** Tara's **first actions** — calendar and reminders; TaRa stops being read-only and starts *doing* things, always behind a confirmation gate.
- Calendar + reminders are deliberately first: lowest-risk actions — no money moves, no PHI leaves the system beyond the event/reminder text the user already supplied.
- **Builds on:** [epic1_grounded_qa/](epic1_grounded_qa/README.md) — ingestion, retrieval, grounded answering, and (critically) the safety pre-check ([Epic 1 M5](epic1_grounded_qa/M5_safety.md)), which still runs first on every turn.
- **Introduces (reused by Epics 3–4):** the agent **orchestrator**, the **tool protocol**, the **confirmation gate**, the **action audit + idempotency** layer, and **OAuth/secret storage** — all in **M1** below. Later epics reference M1 rather than re-specifying it.
- **Status:** Draft v0.1 (content), restructured Phase→Epic / Modules 2026-07-07.
- **Last updated:** 2026-07-07.
- **Modules in this epic:** M1 agent_foundations · M2 calendar · M3 reminders · M4 profile_memory · M5 eval.
- Source of truth for the roadmap is [PRD.md](PRD.md) §11; open design questions live in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
- This is a design doc, not an implementation; contracts here are the spec the Epic 2 stubs should honor.

---

## 1. Goals

1. Introduce an **orchestrator** that, per turn, decides between grounded Q&A (Epic 1) and proposing an **action**.
2. Add a **tool layer** with a uniform contract, and wire the first two tools: **Google Calendar** (create/read events) and **Reminders** (medication, appointments, follow-ups).
3. Enforce a **hard confirmation gate**: no action with an external effect executes without an explicit user "yes" on a concrete preview.
4. Make actions **idempotent and auditable**: never double-book; log every action so the user can see what Tara did.
5. Keep everything **local-first** and **single-profile**, and keep the **safety layer in front of everything** — emergencies still short-circuit before any planning.

- **Success bar (UC-3):** "I have a doctor's appointment on June 25, put it on my calendar" → Tara shows a concrete event preview → user confirms → the event is created exactly once → Tara reports success and offers prep help, with the action in the audit log.

---

## 2. High-level architecture

- Epic 2 wraps the Epic 1 query flow in an orchestrator and adds the action path.

```
   User turn ──▶ ┌──────────────────────────────┐
                 │  SAFETY / TRIAGE (pre-check)  │ ── emergency? ──▶ escalate, STOP
                 │   (Epic 1 M5, unchanged)      │
                 └───────────────┬──────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │            ORCHESTRATOR (planner)            │
                 │  perceive → plan → confirm → act → observe   │
                 └───────┬───────────────────────────┬─────────┘
              answer?    │                            │   action?
                         ▼                            ▼
            ┌────────────────────────┐   ┌───────────────────────────────┐
            │  Epic 1 ANSWERER       │   │  TOOL CALL (proposed)         │
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

### Key flow — action turn (UC-3: add appointment to calendar)

```
user turn → SAFETY pre-check (Epic 1 M5)
            ├─ emergency? → escalate, STOP
            └─ otherwise ↓
         → ORCHESTRATOR plans
            ├─ answer? → Epic 1 answerer (grounded + cited), done
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

---

## M1 — agent_foundations

- **Purpose:** the shared action-layer foundations — orchestrator/planner, tool protocol, confirmation gate, action audit + idempotency, OAuth/secret storage, and the MCP client seam. Epics 3–4 reuse these unchanged.

### Design / contract — orchestrator / planner

- Runs the core agent loop — **perceive → plan → confirm → act → observe** — and is the new entry point for a turn; it does **not** replace Epic 1, it *wraps* it.
- **Perceive:** receives the user message and conversation state (single-profile memory, M4); the Epic 1 safety pre-check has already run upstream — the orchestrator never sees an emergency turn.
- **Plan:** a single LLM planning call (via the Epic 1 `LLMClient`, same local/hosted switch) decides the turn's shape, given the available tool schemas:
  - *Answer* → delegate to the Epic 1 answerer (grounded, cited); no gate.
  - *Act* → emit one or more **proposed** tool calls (tool name + arguments).
  - *Clarify* → ask the user a question (e.g., missing date).
- **Confirm / act / observe:** proposed consequential tool calls go through the confirmation gate; confirmed calls execute; results are observed, reported, then audited.
- Plans stay **shallow** in Epic 2 (single action or a short, linear sequence) — YAGNI on multi-branch planning until a later epic needs it.
- Planner output is a structured object (tool name, args) — never free-text the executor has to parse.

### Design / contract — tool protocol

- A `Tool` is the action-layer analogue of Epic 1's `LLMClient` protocol seam: a uniform abstraction so the orchestrator is decoupled from any specific integration, and **local-vs-remote (MCP) is a config decision, not a code change** — mirroring Epic 1's local/hosted model switch.
- Each tool provides:
  - `name` and a JSON **parameter schema** — so the planner can target it and arguments are validated at the boundary before anything executes.
  - `consequential: bool` — whether a call has an external/financial effect and must pass the confirmation gate; read-only calls (e.g. *read* calendar) may be exempt — configurable.
  - `preview(args) -> ActionPreview` — a **side-effect-free** human-readable description of exactly what will happen ("Create event 'Dr. Smith' on 2026-06-25 10:00, calendar: Personal"); the gate shows this.
  - `execute(args, idempotency_key) -> ActionResult` — performs the action; must be safe to retry with the same key.
- Tools are discovered from config (an allow-list) — enabling/disabling an integration is configuration.
- A tool may be backed by a local implementation or by an **MCP client** (below); the orchestrator can't tell the difference.

### Design / contract — confirmation gate

- The hard guarantee from PRD §6.3/§9: **no consequential action without explicit user approval.**
- A proposed consequential tool call is **never** executed inline by the planner — it is materialized as an `actions` row in `status='proposed'` with its `preview`.
- The gate presents the preview and requires an **explicit affirmative** ("yes", tap-to-confirm) — not mere absence of objection; ambiguous or "maybe" → treated as no.
- On approval → `status='confirmed'`, then execute; on decline/timeout → `status='cancelled'`, nothing runs.
- The gate is **server-side and mandatory** — not a UI nicety the planner can skip; the executor refuses to run a consequential tool whose action row is not `confirmed`.

### Design / contract — action audit + idempotency

- **Audit:** the `actions` table (below) records tool, arguments, preview, status, result, and timestamps; it extends the Epic 1 `queries` audit log so the user has one place to see "what did Tara do?" (PRD §8 auditability).
- **Idempotency:**
  - Each proposed action gets an `idempotency_key` derived from the semantic content — e.g. calendar `create_event` keyed on title+start+calendar — so a retry of the *same* intent doesn't double-book.
  - `execute` checks the key/status before acting; a key already `executed` is a no-op that returns the prior result.
  - Where the provider supports its own idempotency token, pass it through.
- **Reliability (PRD §8):** "actions must be idempotent or confirmable" — Epic 2 delivers both: confirmable via the gate, idempotent via the key.

### Design / contract — OAuth / secret storage

- Tokens are stored encrypted (reuse the Epic 1 `TARA_DB_KEY` posture); never logged; redacted from `actions.result`, logs, and any error surfaced to the model.
- OAuth connect flow (first calendar use):

```
user enables Calendar → OAuth 2.0 consent (Google) → store access/refresh tokens
   (encrypted) in oauth_tokens → tool available
   (token refresh handled transparently; refresh failure → ask user to reconnect)
```

### Design / contract — MCP client seam

- Where an integration ships an MCP server (calendar; later email), TaRa talks to it through an **MCP client** wrapped behind the `Tool` contract above.
- MCP server endpoints/credentials come from config.
- Keeps "which integration backs this tool" a configuration concern; Epics 3–4 add MCP-backed tools without touching the orchestrator.

### Data-model deltas (from Epic 1)

```
actions                          -- audit + idempotency for every action
  action_id        (pk)
  turn_id          (fk -> a conversation turn / queries.query_id)
  tool_name        (calendar.create_event | reminders.create | ...)
  args             (json; validated against the tool's param schema)
  preview          (text shown at the gate)
  status           (proposed | confirmed | executed | failed | cancelled)
  idempotency_key  (unique per semantic intent)
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
```

### Tests / acceptance

- **Confirmation-gate enforcement (release gate):** a consequential tool **cannot** execute without a `confirmed` action row; attempting to execute `proposed`/`cancelled` → must refuse.
- **Idempotency:** the same intent twice creates exactly one effect; replay with the same key returns the prior result.
- **Planner routing:** Q&A turns → Epic 1 answerer (no gate); action turns → valid, schema-checked tool call; ambiguous turns clarify rather than guess.
- **OAuth lifecycle:** token refresh works; refresh failure prompts reconnect rather than crashing; missing/expired token never blocks the Q&A path.

---

## M2 — calendar

- **Purpose:** the first concrete tool — Google Calendar create/read appointment events over MCP + OAuth 2.0.

### Design / contract

- Integration: the **official Google Calendar remote MCP server** (OAuth 2.0) — the lowest-friction path and the first concrete `Tool`/MCP wiring (PRD §7).
- Operations:
  - `create_event` — consequential → gated.
  - `list_events` / `read_event` — read-only → exempt unless config requires confirmation.
- Time-zone handling and an explicit calendar selection are part of the preview.

### Data-model deltas

- `oauth_tokens.provider` gains `google_calendar` (see M1 sketch).

### Tests / acceptance

- UC-3 end to end: preview → explicit yes → event created exactly once → audited.
- `create_event` retried with the same idempotency key does not double-book.

---

## M3 — reminders

- **Purpose:** medication, appointment, and follow-up reminders — device-bound, with graceful fallback.

### Design / contract

- Reminders are **device-bound** — there is no universal cloud API (PRD §7).
- Support local notifications and/or a Reminders MCP/automation where available.
- **Degrade gracefully** to an in-app reminder when the OS path isn't available; the device-bound limitation is recorded, not hidden.

### Data-model deltas

- None beyond `actions` rows (`reminders.create`).

### Tests / acceptance

- Reminder creation goes through the gate when consequential; fallback path produces an in-app reminder when the OS path is unavailable.

---

## M4 — profile_memory

- **Purpose:** minimal, local single-profile preferences so actions don't re-ask settled facts.

### Design / contract

- PRD §6.4 calls for memory of the user profile, preferences, and past interactions — single profile only.
- A minimal, local **profile/preferences** store: e.g. default calendar, time zone, reminder lead time.
- Intentionally small (KISS); richer memory is deferred until an epic needs it.

### Data-model deltas

```
profile                          -- single-profile preferences
  key              (default_calendar | timezone | reminder_lead_minutes | ...)
  value
```

### Tests / acceptance

- A settled preference (e.g. default calendar) is not re-asked on the next action turn.

---

## M5 — eval

- **Purpose:** tests/evals gating the Epic 2 guarantees.

### Design / contract (test battery)

- **Confirmation-gate enforcement (release gate):** consequential execution requires a `confirmed` row; `proposed`/`cancelled` execution refused (M1).
- **Idempotency:** same `create_event` intent twice → exactly one event; same-key replay returns prior result (M1/M2).
- **Planner routing:** answer/act/clarify routed correctly; action args schema-checked (M1).
- **OAuth lifecycle:** refresh works; failure → reconnect prompt; Q&A path never blocked by token state (M1).
- **Graceful failure:** provider/network error → `status=failed`, clear user message, no partial effect.
- **Safety precedence:** an emergency phrased as an action ("I'm having chest pain, remind me to call my doctor") still triggers the Epic 1 emergency short-circuit before any planning.

---

## Cross-cutting: Safety, Privacy & security

- **Safety & confirmation:**
  - The Epic 1 **safety pre-check runs first, unchanged** — actions never bypass it; an emergency turn never reaches the orchestrator.
  - The **confirmation gate (M1) is the action-layer safety guarantee** — mandatory and server-enforced; the planner cannot self-approve.
  - **No definitive promises** (PRD §6.5) still applies to any health framing in an action turn (e.g. suggesting a calendar reminder for a symptom follow-up).
  - Failures degrade gracefully and visibly — a failed action is reported as failed, never silently dropped, and never leaves a partial/duplicate effect (idempotency).
- **Privacy & security:**
  - **Local-first preserved:** profile, preferences, audit, and tokens all live in the same on-device store as Epic 1.
  - **Secrets:** OAuth tokens encrypted at rest (reuse `TARA_DB_KEY`), never logged, redacted from model-visible context and `actions.result`.
  - **Minimal external data:** a calendar/reminder action sends only the fields that action needs (title, time, calendar id) to the provider — not document content or the conversation.
  - **Auditability (PRD §8):** every action is logged and user-viewable, including what was sent to which provider.
  - **New egress surface:** unlike Epic 1 (where egress is only the optional hosted model), Epic 2 introduces provider egress (Google) — opt-in per tool (enabling the integration + OAuth consent) and recorded in the audit log.

---

## What this epic excludes

- No email, delivery/commerce, or pharmacy actions — those are [Epic3_external_actions.md](Epic3_external_actions.md).
- No health-portal (FHIR) integration and no proactive behavior — those are [Epic4_portal_and_proactive.md](Epic4_portal_and_proactive.md); Tara still only acts when asked.
- No multi-step/branching plans beyond a short linear sequence (YAGNI).
- No multi-profile / multi-user (out of scope productwide).

---

## Build order (module sequence)

1. **M1:** orchestrator skeleton wrapping the Epic 1 flow — every turn still runs safety → answerer, but through the planner (answer-only path first).
2. **M1:** tool protocol + the `actions` table + the confirmation gate, with one trivial read-only tool to exercise routing.
3. **M1/M2:** OAuth/token storage (encrypted) + Google Calendar MCP wiring; `list_events` (read-only) end to end.
4. **M2:** `create_event` (consequential) through the gate, with idempotency — the UC-3 flow.
5. **M3:** reminders tool (local notifications + graceful degradation).
6. **M4:** single-profile preferences (default calendar, timezone, lead time).
7. **M5:** tests/evals, gating the confirmation-gate and idempotency guarantees.

---

## Repository layout (deltas from Epic 1)

- Package/file names follow the settled Epic 1 naming conventions (`agent_orchestration/`, `agent_tools/` are the names reserved in the Epic 1 layout; `local_data_stores/` is the state plane).

```
src/tara/
├── agent_orchestration/         # NEW: orchestrator/planner loop + confirmation gate (M1)
│   ├── turn_orchestrator.py     #   perceive→plan→confirm→act→observe
│   ├── action_planner.py        #   LLM planning call → structured tool calls
│   └── confirmation_gate.py     #   server-side gate (proposed→confirmed→execute)
├── agent_tools/                 # NEW: tool protocol + integrations (M1–M3)
│   ├── tool_protocol.py         #   Tool protocol (name, schema, consequential, preview, execute)
│   ├── mcp_tool_client.py       #   MCP client seam (M1)
│   ├── google_calendar.py       #   Google Calendar (MCP, OAuth2) (M2)
│   └── device_reminders.py      #   device-bound reminders + graceful fallback (M3)
├── local_data_stores/           # +actions, +oauth_tokens, +profile tables; encrypted secrets
├── question_answering/          # unchanged (Epic 1) — orchestrator delegates here for Q&A
└── safety_checks/               # unchanged (Epic 1) — runs before the orchestrator
```

- Config additions (all `TARA_`-prefixed, per Epic 1's central-config rule): an actions enable/allow-list, Google OAuth client credentials + MCP endpoint, default timezone/calendar.
- No provider or endpoint is hard-coded — enabling an integration is configuration.
