# TaRa Health — Phase 3 Technical Design

**Phase 3 scope:** Tara's **external actions** — drafting/sending email (to insurers
and providers), grocery/food **delivery**, and **pharmacy refills**. These are
higher-stakes than Phase 2's calendar/reminders: they touch money, third-party
accounts, and gated APIs. The defining design decision of Phase 3 is the
**assisted-handoff pattern** — where a direct, automated API isn't available or is
too risky, Tara *prepares* the action and hands the user a link/draft to confirm on
the provider's own surface.

**Builds on:** [PHASE_2_TECHNICAL_DESIGN.md](PHASE_2_TECHNICAL_DESIGN.md). Phase 3
reuses, unchanged, the Phase 2 foundations:
- **Orchestrator/planner** (perceive → plan → confirm → act → observe) — §2 P2.
- **Tool protocol** (name, JSON schema, `consequential`, `preview`, `execute`) — §3.2 P2.
- **Confirmation gate** (server-side, mandatory, explicit "yes") — §3.3 P2.
- **Action audit + idempotency** (`actions` table, idempotency keys) — §3.5 P2.
- **OAuth/secret storage** (encrypted tokens, redaction) — §4/§7 P2.
- And, before all of it, the **Phase 1 safety pre-check**.

Phase 3 adds two things on top: the **assisted-handoff** tool kind (§3.1) and
**heightened confirmation for financial actions** (§3.3). Everything else is new
tools plugged into the existing seams.

**Status:** Draft v0.1
**Last updated:** 2026-06-28

> Source of truth for phasing is [PRD.md](PRD.md) §11. Phase 3 settles two former
> open questions — pharmacy/delivery gating (§3.1–§3.2) and messages/SMS (§3.5);
> their decisions are recorded in this doc. See
> [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) for what remains undecided.

---

## 1. Goals

1. Let Tara **draft and send email** to insurers/providers, with the user approving
   the exact recipient and body (UC-2).
2. Let Tara **prepare delivery orders** (groceries via Instacart; food via
   DoorDash/Uber Eats) and **pharmacy refills** (CVS/Walgreens) — placing them
   directly where an API allows, and via **assisted handoff** where it doesn't.
3. Establish the **assisted-handoff pattern** as the default for gated or financial
   integrations: "Tara prepares it, you tap to confirm on their site."
4. **Harden confirmation for anything involving money** — explicit amounts, itemized
   previews, and a stricter affirmative.
5. Preserve local-first, single-profile, safety-first, and full auditability.

Success bar (UC-2): "I think I need a doctor for high blood sugar" → Tara surfaces
the grounded copay/coverage (Phase 1), then offers to draft an email to the provider
and (separately) verify cost with the insurer → user reviews the exact draft →
sends. (UC-6): "Refill my metformin" → Tara confirms the prescription, then either
places the refill (if the pharmacy API allows) or hands off a pre-filled
refill/checkout link → reports status.

---

## 2. High-level architecture

Phase 3 changes the *execute* step's repertoire, not the loop. Two execution kinds
now exist behind the same gate:

```
   (Phase 2 loop unchanged: safety → orchestrator → plan → confirm → act → observe)

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

**Financial actions** (anything that spends money — placing a paid order) get the
heightened gate (§3.3) regardless of which execution kind is used.

---

## 3. Components

### 3.1 Assisted-handoff pattern (new tool kind)

Many of Phase 3's integrations either don't expose a direct order-placement API or
gate it heavily (PRD §7). Rather than block the capability or over-build
against brittle APIs, Tara supports a second execution kind on the §3.2-P2 `Tool`
contract:

- A **direct-API** tool implements `execute(args, idempotency_key)` as in Phase 2.
- An **assisted-handoff** tool implements `prepare(args) -> Handoff`, returning a
  ready-to-complete artifact: a deep link to a pre-filled provider page, a checkout
  URL, or a finished draft. Tara never completes the consequential step itself; the
  user does, on the provider's surface.

Both kinds still pass through the confirmation gate (the user approves *what Tara is
about to prepare/send*). The audit log distinguishes `executed` (direct) from
`handed_off` (assisted). This is the **graceful-degradation** principle from PRD §9:
where a clean API exists we use it; where it doesn't, we degrade to handoff rather
than fail. A tool can also **fall back** from direct to handoff at runtime (e.g.
API unavailable) without changing the user-visible contract.

### 3.2 Tools wired in Phase 3

**a. Email (Gmail).** Draft + send to insurers/providers (UC-2). Integration: Gmail
API / Gmail (Google Workspace) MCP server — mature (PRD §7). `draft_email`
(side-effect-free; produces the body for review) and `send_email` (consequential →
gated). The gate preview shows the exact recipient, subject, and full body; nothing
is sent until approved. Reuses the Phase 2 Google OAuth/token store (additional
Gmail scopes).

**b. Delivery — groceries (Instacart).** Instacart Developer Platform (IDP) is a
**public API that does not place orders directly** — it returns a link to an
Instacart-hosted checkout page (PRD §7). This is the canonical **assisted-handoff**
(§3.1): `prepare` builds the cart/recipe and returns the checkout URL; the user
completes payment on Instacart. Note the ~30–40 day approval lead time (PRD §7).

**c. Delivery — food (DoorDash / Uber Eats).** Consumer-order APIs are limited (PRD
§7). Default to **assisted handoff** (deep link / link-out) unless/until partner
access is justified. Surfaces UC-1's "want me to order food?" offer.

**d. Pharmacy refills (CVS / Walgreens).** CVS and Walgreens developer portals offer
refill APIs but **gate access and may restrict to mobile apps** (PRD §7; note
Capsule is a separate company, not CVS). Phase 3 implements `refill` as a
direct-API tool **where access is provisioned**, with **assisted handoff** (pre-filled
refill page / pharmacy app deep link) as the default fallback (UC-6). Confirm the
specific prescription before any refill.

### 3.3 Heightened confirmation for financial actions

The Phase 2 gate (§3.3 P2) is mandatory for all consequential actions. Phase 3 adds
a stricter tier for **financial** actions (spends money, places a paid order):
- The preview must be **itemized and show the total cost** (or state explicitly that
  the final amount is set on the provider's checkout, for handoffs).
- The affirmative is **specific** ("yes, send this email to insurer@…", "yes,
  prepare this $42 order") — not a generic "ok".
- Aligns with PRD §9 "no consequential action without explicit yes" and §10 "zero
  unconfirmed consequential actions" — for money, the bar is highest.

For assisted handoffs, the money actually moves on the provider's site, which is an
additional natural safety margin — but Tara still gates *preparing/sending* the
handoff.

### 3.4 Secret-management hardening

Phase 3 multiplies providers and tokens, so the Phase 2 secret posture is hardened:
- **Scope minimization** — request the narrowest OAuth scopes per provider (e.g.
  Gmail send vs. full mailbox).
- **Per-provider revocation** — the user can disconnect any single integration; its
  tokens are purged and its tools disabled.
- **No secret egress** — tokens stay encrypted at rest (Phase 2 §7), are never placed
  in planner/model context, and are redacted from `actions.result`, handoff URLs
  shown in logs, and error messages.
- **Handoff-URL hygiene** — pre-filled links can embed PHI (medication, address);
  treat them as sensitive (not logged in plaintext beyond the local audit record).

### 3.5 Messages / SMS (scoped decision)

iMessage has no official API; SMS via a provider (e.g. Twilio) is possible (PRD §7).
Phase 3 is where the notification-channel question surfaces: is SMS worth it, or are
in-app + calendar/email notifications (already available by end of Phase 2/3)
enough? **Decision (resolved here)** — default to in-app + email
notifications and treat SMS as opt-in only if a real need appears (YAGNI).

---

## 4. Data model (deltas from Phase 2 §4)

```
actions (extends Phase 2)
  status            -- add: handed_off (assisted-handoff prepared, user completes)
  execution_kind    -- direct | assisted_handoff (which path was used; §3.1)
  cost_estimate     -- shown at the financial gate (§3.3); nullable
  handoff_url       -- for assisted handoffs; SENSITIVE, redacted in logs

oauth_tokens (extends Phase 2)
  provider          -- add: gmail | instacart | cvs | walgreens | doordash | ubereats
  scopes            -- minimized per provider (§3.4)
```

No new top-level tables are required — Phase 3 reuses the Phase 2 `actions`,
`oauth_tokens`, and `profile` stores. Profile may gain delivery address / preferred
pharmacy (single profile), stored locally like all other preferences.

---

## 5. Key flows

### 5.1 Email an insurer/provider (UC-2, direct API)
```
turn → safety → orchestrator → plan: draft_email
  → draft_email(args) → body produced (no send)
  → CONFIRMATION GATE shows full recipient/subject/body
     ├─ no → cancelled
     └─ yes → send_email (consequential) → status=executed → report + audit
```

### 5.2 Grocery order (Instacart, assisted handoff)
```
turn → safety → orchestrator → plan: instacart.prepare
  → prepare(cart/recipe) → Instacart checkout URL (no order placed)
  → FINANCIAL GATE (itemized; total set at checkout) shows what will be prepared
     ├─ no → cancelled
     └─ yes → present checkout link → status=handed_off
  → (optional later) status check → audit
```

### 5.3 Pharmacy refill (UC-6, direct-or-handoff)
```
turn → safety → orchestrator → confirm WHICH prescription
  → refill.execute(rx) if API provisioned
        ├─ success → status=executed → report pickup/delivery
        └─ unavailable/gated → FALL BACK to prepare() → pre-filled refill link
                              → status=handed_off
  → audit (execution_kind records which path)
```

---

## 6. Safety & confirmation (Phase 3 specifics)

- **Safety pre-check still first** (Phase 1 §3.3) — e.g. "order me something for
  chest pain" triggers the emergency short-circuit before any ordering.
- **Confirmation gate mandatory; financial tier stricter** (§3.3). No paid order or
  sent email without an explicit, specific yes.
- **Assisted handoff is itself a safety margin** — the irreversible/financial step
  happens on the provider's authenticated surface, not silently inside Tara.
- **Idempotency across both kinds** — a direct refill can't double-fill; a handoff
  re-prepare returns the same link rather than spawning duplicates.
- **Graceful, visible failure** — gated/denied APIs degrade to handoff or report
  clearly; never a silent drop or partial order (PRD §9).

---

## 7. Privacy & security (Phase 3)

- **More providers, same local-first core.** All preferences, audit, and tokens stay
  on-device; only the specific fields an action needs go to each provider.
- **Hardened secrets** (§3.4): scope minimization, per-provider revocation, no secret
  egress, handoff-URL hygiene.
- **PHI in outbound content.** Emails and refill/checkout links can carry PHI
  (conditions, medications, address). The gate preview is the user's checkpoint on
  exactly what PHI leaves; the audit log records it.
- **Auditability (PRD §8).** Every send/order/handoff is logged with provider,
  payload summary (secrets redacted), and outcome.

---

## 8. Testing & evaluation

- **Financial gate (release gate):** no money-moving action executes without the
  heightened, itemized confirmation; generic "ok" is rejected for financial actions.
- **Assisted-handoff correctness:** `prepare` produces a valid, pre-filled link/draft
  and **never** completes the consequential step itself; audit status is `handed_off`.
- **Direct→handoff fallback:** when a provisioned API is unavailable, the tool falls
  back to handoff without changing the user-visible contract or losing idempotency.
- **Email fidelity:** the sent message exactly matches the approved preview
  (recipient, subject, body) — no post-approval mutation.
- **Idempotency:** repeated refill/order intents don't duplicate (direct) and
  re-prepare returns the same handoff (assisted).
- **Secret hygiene:** tokens/handoff URLs never appear in logs or model context;
  revocation disables the tool and purges its tokens.
- **Safety precedence:** emergency-phrased ordering/email turns short-circuit first.

---

## 9. What Phase 3 deliberately excludes

- No health-portal (Epic on FHIR) integration and no proactive behavior — those are
  [PHASE_4_TECHNICAL_DESIGN.md](PHASE_4_TECHNICAL_DESIGN.md). Tara still acts only
  when asked.
- No automated *payment* inside Tara — money always moves on the provider's surface
  (direct API where the provider owns the charge, or assisted-handoff checkout).
- SMS/messaging not built by default — in-app + email notifications suffice.
- No multi-profile / multi-user.

---

## 10. Suggested build order within Phase 3

1. Email first — lowest-friction, mature API, no money: `draft_email` →
   `send_email` through the existing gate (extends the Phase 2 Google OAuth scopes).
2. The assisted-handoff tool kind (§3.1): add `prepare()`/`Handoff` to the tool
   contract and the `handed_off` status + `execution_kind` to `actions`.
3. Instacart `prepare` (the canonical handoff) + the financial gate (§3.3).
4. Pharmacy refill as direct-or-handoff (UC-6), with the direct→handoff fallback.
5. Food delivery as handoff/link-out (UC-1 offer).
6. Secret-management hardening (§3.4): scope minimization + per-provider revocation.
7. Tests/evals (§8), gating the financial-confirmation and handoff guarantees.

---

## 11. Repository layout (deltas from Phase 2 §11)

```
src/tara/
├── tools/
│   ├── base.py            # EXTEND: add prepare()/Handoff for the assisted-handoff kind (§3.1)
│   ├── email.py           # NEW: Gmail draft/send (MCP or API, OAuth2)
│   ├── delivery.py        # NEW: Instacart (handoff) + food delivery (handoff/link-out)
│   └── pharmacy.py        # NEW: CVS/Walgreens refill (direct-or-handoff)
├── agent/
│   └── confirmation.py    # EXTEND: financial/heightened confirmation tier (§3.3)
├── storage/               # EXTEND actions (handed_off, execution_kind, cost_estimate, handoff_url);
│                          #   oauth_tokens new providers + minimized scopes
└── (orchestrator, safety, answering unchanged from Phase 2 / Phase 1)
```

Config additions (all `TARA_`-prefixed): per-provider enable flags + OAuth client
credentials/endpoints (Gmail, Instacart, CVS, Walgreens, food delivery), and a
default "prefer handoff over direct API" safety toggle. Enabling any integration
remains configuration, not code.
