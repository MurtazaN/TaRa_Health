# TaRa Health — Epic 3: External Actions *(former Phase 3)*

- **Epic 3 scope:** Tara's **external actions** — drafting/sending email (to insurers and providers), grocery/food **delivery**, and **pharmacy refills**.
- Higher-stakes than Epic 2's calendar/reminders: they touch money, third-party accounts, and gated APIs.
- **Defining design decision:** the **assisted-handoff pattern** — where a direct, automated API isn't available or is too risky, Tara *prepares* the action and hands the user a link/draft to confirm on the provider's own surface.
- **Builds on:** [Epic2_first_actions.md](Epic2_first_actions.md). Epic 3 reuses, unchanged, the Epic 2 M1 foundations:
  - **Orchestrator/planner** (perceive → plan → confirm → act → observe).
  - **Tool protocol** (name, JSON schema, `consequential`, `preview`, `execute`).
  - **Confirmation gate** (server-side, mandatory, explicit "yes").
  - **Action audit + idempotency** (`actions` table, idempotency keys).
  - **OAuth/secret storage** (encrypted tokens, redaction).
  - And, before all of it, the **Epic 1 safety pre-check** (Epic 1 M5).
- Epic 3 adds two things on top: the **assisted-handoff** tool kind + **heightened confirmation for financial actions** (both M1 below); everything else is new tools plugged into the existing seams.
- **Status:** Draft v0.1 (content), restructured Phase→Epic / Modules 2026-07-07.
- **Last updated:** 2026-07-07.
- **Modules in this epic:** M1 assisted_handoff · M2 email · M3 delivery · M4 pharmacy · M5 secret_hardening · M6 eval.
- Source of truth for the roadmap is [PRD.md](PRD.md) §11.
- Epic 3 settles two former open questions — pharmacy/delivery gating (M1, M3, M4) and messages/SMS (decision recorded under "What this epic excludes"); see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) for what remains undecided.

---

## 1. Goals

1. Let Tara **draft and send email** to insurers/providers, with the user approving the exact recipient and body (UC-2).
2. Let Tara **prepare delivery orders** (groceries via Instacart; food via DoorDash/Uber Eats) and **pharmacy refills** (CVS/Walgreens) — placing them directly where an API allows, and via **assisted handoff** where it doesn't.
3. Establish the **assisted-handoff pattern** as the default for gated or financial integrations: "Tara prepares it, you tap to confirm on their site."
4. **Harden confirmation for anything involving money** — explicit amounts, itemized previews, and a stricter affirmative.
5. Preserve local-first, single-profile, safety-first, and full auditability.

- **Success bar (UC-2):** "I think I need a doctor for high blood sugar" → Tara surfaces the grounded copay/coverage (Epic 1), then offers to draft an email to the provider and (separately) verify cost with the insurer → user reviews the exact draft → sends.
- **Success bar (UC-6):** "Refill my metformin" → Tara confirms the prescription, then either places the refill (if the pharmacy API allows) or hands off a pre-filled refill/checkout link → reports status.

---

## 2. High-level architecture

- Epic 3 changes the *execute* step's repertoire, not the loop; two execution kinds now exist behind the same gate.

```
   (Epic 2 loop unchanged: safety → orchestrator → plan → confirm → act → observe)

                         CONFIRMATION GATE
                  ┌──────────────┴───────────────┐
       direct-API │                              │ assisted-handoff
                  ▼                              ▼
   ┌────────────────────────┐     ┌─────────────────────────────────────┐
   │ Tool.execute(args)     │     │ Tool.prepare(args) → link / draft    │
   │ (Gmail send, CVS refill│     │ (Instacart checkout URL, refill page,│
   │  where API allows)     │     │  pharmacy app deep link)             │
   └───────────┬────────────┘     └──────────────────┬──────────────────┘
               ▼                                      ▼
   provider performs action          user completes on provider's surface;
   → observe → report → AUDIT        Tara records "handed off" → AUDIT
                                     (optional later status check)
```

- **Financial actions** (anything that spends money — placing a paid order) get the heightened gate (M1) regardless of which execution kind is used.

---

## M1 — assisted_handoff

- **Purpose:** the new tool kind (prepare → link/draft, user completes on the provider's surface) plus the heightened financial confirmation tier.

### Design / contract — assisted-handoff tool kind

- Many Epic 3 integrations either don't expose a direct order-placement API or gate it heavily (PRD §7); rather than block the capability or over-build against brittle APIs, Tara supports a second execution kind on the Epic 2 M1 `Tool` contract:
  - A **direct-API** tool implements `execute(args, idempotency_key)` as in Epic 2.
  - An **assisted-handoff** tool implements `prepare(args) -> Handoff`, returning a ready-to-complete artifact: a deep link to a pre-filled provider page, a checkout URL, or a finished draft.
  - Tara never completes the consequential step itself; the user does, on the provider's surface.
- Both kinds still pass through the confirmation gate — the user approves *what Tara is about to prepare/send*.
- The audit log distinguishes `executed` (direct) from `handed_off` (assisted).
- This is the **graceful-degradation** principle from PRD §9: where a clean API exists we use it; where it doesn't, we degrade to handoff rather than fail.
- A tool can also **fall back** from direct to handoff at runtime (e.g. API unavailable) without changing the user-visible contract.

### Design / contract — heightened confirmation for financial actions

- The Epic 2 gate is mandatory for all consequential actions; Epic 3 adds a stricter tier for **financial** actions (spends money, places a paid order):
  - The preview must be **itemized and show the total cost** (or state explicitly that the final amount is set on the provider's checkout, for handoffs).
  - The affirmative is **specific** ("yes, send this email to insurer@…", "yes, prepare this $42 order") — not a generic "ok".
  - Aligns with PRD §9 "no consequential action without explicit yes" and §10 "zero unconfirmed consequential actions" — for money, the bar is highest.
- For assisted handoffs, the money actually moves on the provider's site — an additional natural safety margin — but Tara still gates *preparing/sending* the handoff.

### Data-model deltas (extends the Epic 2 `actions` / `oauth_tokens` tables)

```
actions (extends Epic 2)
  status            -- add: handed_off (assisted-handoff prepared, user completes)
  execution_kind    -- direct | assisted_handoff (which path was used)
  cost_estimate     -- shown at the financial gate; nullable
  handoff_url       -- for assisted handoffs; SENSITIVE, redacted in logs

oauth_tokens (extends Epic 2)
  provider          -- add: gmail | instacart | cvs | walgreens | doordash | ubereats
  scopes            -- minimized per provider (M5)
```

- No new top-level tables — Epic 3 reuses the Epic 2 `actions`, `oauth_tokens`, and `profile` stores.
- `profile` may gain delivery address / preferred pharmacy (single profile), stored locally like all other preferences.

### Tests / acceptance

- `prepare` produces a valid, pre-filled link/draft and **never** completes the consequential step itself; audit status is `handed_off`.
- Financial actions refuse a generic "ok"; itemized preview required.
- Direct→handoff fallback preserves the user-visible contract and idempotency.

---

## M2 — email

- **Purpose:** Gmail draft + send to insurers/providers (UC-2).

### Design / contract

- Integration: Gmail API / Gmail (Google Workspace) MCP server — mature (PRD §7).
- `draft_email` — side-effect-free; produces the body for review.
- `send_email` — consequential → gated; the gate preview shows the **exact recipient, subject, and full body**; nothing is sent until approved.
- Reuses the Epic 2 Google OAuth/token store (additional Gmail scopes).

### Key flow (UC-2, direct API)

```
turn → safety → orchestrator → plan: draft_email
  → draft_email(args) → body produced (no send)
  → CONFIRMATION GATE shows full recipient/subject/body
     ├─ no → cancelled
     └─ yes → send_email (consequential) → status=executed → report + audit
```

### Data-model deltas

- `oauth_tokens.provider` gains `gmail` (see M1 sketch).

### Tests / acceptance

- **Email fidelity:** the sent message exactly matches the approved preview (recipient, subject, body) — no post-approval mutation.

---

## M3 — delivery

- **Purpose:** grocery delivery (Instacart, the canonical assisted handoff) + food delivery (DoorDash / Uber Eats, handoff/link-out).

### Design / contract — groceries (Instacart)

- Instacart Developer Platform (IDP) is a **public API that does not place orders directly** — it returns a link to an Instacart-hosted checkout page (PRD §7).
- This is the canonical **assisted handoff** (M1): `prepare` builds the cart/recipe and returns the checkout URL; the user completes payment on Instacart.
- Note the ~30–40 day approval lead time (PRD §7).

### Design / contract — food (DoorDash / Uber Eats)

- Consumer-order APIs are limited (PRD §7).
- Default to **assisted handoff** (deep link / link-out) unless/until partner access is justified.
- Surfaces UC-1's "want me to order food?" offer.

### Key flow (Instacart, assisted handoff)

```
turn → safety → orchestrator → plan: instacart.prepare
  → prepare(cart/recipe) → Instacart checkout URL (no order placed)
  → FINANCIAL GATE (itemized; total set at checkout) shows what will be prepared
     ├─ no → cancelled
     └─ yes → present checkout link → status=handed_off
  → (optional later) status check → audit
```

### Data-model deltas

- `oauth_tokens.provider` gains `instacart | doordash | ubereats` (see M1 sketch).

### Tests / acceptance

- Grocery `prepare` yields a valid checkout URL; no order is placed by Tara; `handed_off` audited.
- Re-prepare of the same intent returns the same handoff link (idempotency), not duplicates.

---

## M4 — pharmacy

- **Purpose:** CVS / Walgreens prescription refills (UC-6) as direct-or-handoff.

### Design / contract

- CVS and Walgreens developer portals offer refill APIs but **gate access and may restrict to mobile apps** (PRD §7; note **Capsule is a separate company, not CVS**).
- `refill` is a direct-API tool **where access is provisioned**, with **assisted handoff** (pre-filled refill page / pharmacy app deep link) as the default fallback.
- **Confirm the specific prescription before any refill.**

### Key flow (UC-6, direct-or-handoff)

```
turn → safety → orchestrator → confirm WHICH prescription
  → refill.execute(rx) if API provisioned
        ├─ success → status=executed → report pickup/delivery
        └─ unavailable/gated → FALL BACK to prepare() → pre-filled refill link
                              → status=handed_off
  → audit (execution_kind records which path)
```

### Data-model deltas

- `oauth_tokens.provider` gains `cvs | walgreens` (see M1 sketch).

### Tests / acceptance

- Repeated refill intents don't duplicate (direct); re-prepare returns the same handoff (assisted).
- Direct→handoff fallback engages when the API is unavailable/gated.

---

## M5 — secret_hardening

- **Purpose:** harden the Epic 2 secret posture as providers and tokens multiply.

### Design / contract

- **Scope minimization** — request the narrowest OAuth scopes per provider (e.g. Gmail send vs. full mailbox).
- **Per-provider revocation** — the user can disconnect any single integration; its tokens are purged and its tools disabled.
- **No secret egress** — tokens stay encrypted at rest (Epic 2 posture), are never placed in planner/model context, and are redacted from `actions.result`, handoff URLs shown in logs, and error messages.
- **Handoff-URL hygiene** — pre-filled links can embed PHI (medication, address); treat them as sensitive (not logged in plaintext beyond the local audit record).

### Data-model deltas

- `oauth_tokens.scopes` minimized per provider (see M1 sketch).

### Tests / acceptance

- Tokens/handoff URLs never appear in logs or model context.
- Revocation disables the tool and purges its tokens.

---

## M6 — eval

- **Purpose:** tests/evals gating the Epic 3 guarantees.

### Design / contract (test battery)

- **Financial gate (release gate):** no money-moving action executes without the heightened, itemized confirmation; generic "ok" is rejected for financial actions (M1).
- **Assisted-handoff correctness:** `prepare` produces a valid, pre-filled link/draft and never completes the consequential step; audit status `handed_off` (M1).
- **Direct→handoff fallback:** when a provisioned API is unavailable, the tool falls back to handoff without changing the user-visible contract or losing idempotency (M1, M4).
- **Email fidelity:** sent message exactly matches the approved preview — recipient, subject, body (M2).
- **Idempotency:** repeated refill/order intents don't duplicate (direct); re-prepare returns the same handoff (assisted) (M3, M4).
- **Secret hygiene:** tokens/handoff URLs never in logs or model context; revocation disables + purges (M5).
- **Safety precedence:** emergency-phrased ordering/email turns short-circuit first (Epic 1 M5).

---

## Cross-cutting: Safety, Privacy & security

- **Safety & confirmation:**
  - **Safety pre-check still first** (Epic 1 M5) — e.g. "order me something for chest pain" triggers the emergency short-circuit before any ordering.
  - **Confirmation gate mandatory; financial tier stricter** (M1) — no paid order or sent email without an explicit, specific yes.
  - **Assisted handoff is itself a safety margin** — the irreversible/financial step happens on the provider's authenticated surface, not silently inside Tara.
  - **Idempotency across both kinds** — a direct refill can't double-fill; a handoff re-prepare returns the same link rather than spawning duplicates.
  - **Graceful, visible failure** — gated/denied APIs degrade to handoff or report clearly; never a silent drop or partial order (PRD §9).
- **Privacy & security:**
  - **More providers, same local-first core:** all preferences, audit, and tokens stay on-device; only the specific fields an action needs go to each provider.
  - **Hardened secrets (M5):** scope minimization, per-provider revocation, no secret egress, handoff-URL hygiene.
  - **PHI in outbound content:** emails and refill/checkout links can carry PHI (conditions, medications, address); the gate preview is the user's checkpoint on exactly what PHI leaves; the audit log records it.
  - **Auditability (PRD §8):** every send/order/handoff is logged with provider, payload summary (secrets redacted), and outcome.

---

## What this epic excludes

- No health-portal (Epic on FHIR) integration and no proactive behavior — those are [Epic4_portal_and_proactive.md](Epic4_portal_and_proactive.md); Tara still acts only when asked.
- No automated *payment* inside Tara — money always moves on the provider's surface (direct API where the provider owns the charge, or assisted-handoff checkout).
- **Messages / SMS — scoped decision (resolved here):**
  - iMessage has no official API; SMS via a provider (e.g., Twilio) is possible (PRD §7).
  - **Decision:** default to in-app + email notifications (already available by end of Epic 2/3); treat SMS as opt-in only if a real need appears (YAGNI). Not built by default.
- No multi-profile / multi-user.

---

## Build order (module sequence)

1. **M2 (email first)** — lowest-friction, mature API, no money: `draft_email` → `send_email` through the existing gate (extends the Epic 2 Google OAuth scopes).
2. **M1 (handoff kind):** add `prepare()`/`Handoff` to the tool contract and the `handed_off` status + `execution_kind` to `actions`.
3. **M3 + M1 (financial gate):** Instacart `prepare` (the canonical handoff) + the heightened financial confirmation.
4. **M4:** pharmacy refill as direct-or-handoff (UC-6), with the direct→handoff fallback.
5. **M3:** food delivery as handoff/link-out (UC-1 offer).
6. **M5:** secret-management hardening — scope minimization + per-provider revocation.
7. **M6:** tests/evals, gating the financial-confirmation and handoff guarantees.

---

## Repository layout (deltas from Epic 2)

- Names follow the settled Epic 1/2 conventions (`agent_tools/`, `agent_orchestration/`, `local_data_stores/`).

```
backend/src/tara/
├── agent_tools/
│   ├── tool_protocol.py       # EXTEND: add prepare()/Handoff for the assisted-handoff kind (M1)
│   ├── gmail_email.py         # NEW: Gmail draft/send (MCP or API, OAuth2) (M2)
│   ├── delivery_orders.py     # NEW: Instacart (handoff) + food delivery (handoff/link-out) (M3)
│   └── pharmacy_refills.py    # NEW: CVS/Walgreens refill (direct-or-handoff) (M4)
├── agent_orchestration/
│   └── confirmation_gate.py   # EXTEND: financial/heightened confirmation tier (M1)
├── local_data_stores/         # EXTEND actions (handed_off, execution_kind, cost_estimate, handoff_url);
│                              #   oauth_tokens new providers + minimized scopes
└── (orchestrator, safety_checks, question_answering unchanged from Epics 1–2)
```

- Config additions (all `TARA_`-prefixed): per-provider enable flags + OAuth client credentials/endpoints (Gmail, Instacart, CVS, Walgreens, food delivery), and a default "prefer handoff over direct API" safety toggle.
- Enabling any integration remains configuration, not code.
