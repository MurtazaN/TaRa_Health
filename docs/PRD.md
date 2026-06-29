# Product Requirements Document (PRD)

**Product:** TaRa Health
**Assistant name:** Tara
**Author:** [Your name]
**Status:** Draft v0.2
**Last updated:** [Date]

---

## 1. Overview

TaRa Health is a personal, **agentic** AI assistant — **Tara** — that ingests a
single user's health and insurance documents and helps them **understand** their
situation and **act** on it. Tara answers health and coverage questions grounded
in the user's actual documents, and — with explicit confirmation — takes
real-world actions such as scheduling appointments, adding calendar events,
contacting insurers, refilling prescriptions, and ordering food or supplies.

This is an **agentic application**: it does not merely retrieve and answer, it
plans multi-step tasks and executes them via integrated tools, always pausing for
user approval before taking consequential action.

**Two product decisions are now fixed:**
- **Single profile only** — TaRa serves one user. No family/caregiver/multi-profile support.
- **Local-first** — the user's documents and data live on their device by default.

---

## 2. Problem Statement

People hold their health and insurance information across scattered PDFs, portals,
and emails, and struggle to:

- Understand what their insurance actually covers and what a visit will cost.
- Decide whether a symptom warrants self-care or a doctor.
- Navigate the logistics of care (booking, verifying coverage, preparing).

The information needed to answer these questions usually already exists in the
user's own documents — it's just inaccessible at the moment of need. TaRa makes
that information conversational and actionable.

---

## 3. Goals & Non-Goals

### Goals
- Let the user upload health and insurance documents and query them in natural language.
- Provide grounded, document-aware answers (cite the source document/section).
- Take useful real-world actions on the user's behalf, with confirmation.
- Maintain a coherent picture of the user across sessions (plan, history, preferences).

### Non-Goals
- Not a diagnostic medical device. Tara does not diagnose, prescribe, or replace clinicians.
- Not an insurance broker or claims-filing system.
- **Not multi-user** — single profile only.
- No real-time biometric monitoring or wearable integration in v1.

---

## 4. Target User & Persona

**The Self-Manager:** an adult managing their own care who is comfortable with
apps, wants quick answers about symptoms and costs, and values having logistics
handled for them. This is the *only* persona — the product is deliberately
single-user.

---

## 5. Key Use Cases

| # | User input | Expected Tara behavior |
|---|-----------|------------------------|
| UC-1 | "I have a headache and haven't eaten all day, what should I do?" | Give safe, general guidance (likely low blood sugar; eat something). Offer an action: order food via delivery. **Do not** assert a guaranteed timeline or diagnosis. |
| UC-2 | "I think I need a doctor for high blood sugar." | Explain when to seek care, surface the user's actual copay/coverage from their documents, and offer to (a) book a visit via the provider portal and (b) verify cost with insurance. Ask which to do first. |
| UC-3 | "I have a doctor's appointment on June 25, put it on my calendar." | Create the calendar event, confirm it, and offer prep help. |
| UC-4 | "How much will an MRI cost me?" | Read coverage terms from insurance docs, estimate out-of-pocket cost, cite the relevant policy section, and flag uncertainty. |
| UC-5 | "What were the results of my last blood test?" | Retrieve and plainly summarize values from an uploaded lab report; explain reference ranges without diagnosing. |
| UC-6 | "Refill my metformin." | Confirm the prescription, then place a refill via the connected pharmacy and report pickup/delivery status. |

---

## 6. Functional Requirements

### 6.1 Document ingestion
- Upload PDFs and images (lab results, insurance cards, policy summaries, EOBs, after-visit summaries).
- OCR for scanned documents.
- Parse and index content for retrieval (RAG over the user's local corpus).
- Classify document type (insurance policy, lab report, prescription, bill, etc.).

### 6.2 Conversational Q&A
- Natural-language questions grounded in the user's documents.
- Answers cite which document/section they came from.
- Explicit "I don't have a document that says this" when information is missing — never fabricate coverage numbers.

### 6.3 Agentic actions (each requires explicit user confirmation)
- **Calendar:** create/read appointment events.
- **Email:** draft and send messages (e.g., to insurer or provider).
- **Reminders:** medication, appointments, follow-ups.
- **Health portal:** read records and (later) request appointments via the provider portal.
- **Pharmacy:** refill prescriptions.
- **Delivery/commerce:** order food or supplies.

### 6.4 Agent orchestration
- A planning layer that decomposes a request into steps and selects tools.
- A tool/function-calling interface for each integration (see §7).
- A confirmation gate before any action with external or financial effect.
- Memory of the user profile, preferences, and past interactions (single profile).

### 6.5 Safety layer
- **Emergency detection:** recognize red-flag symptoms (chest pain, stroke signs, suicidal ideation, etc.) and immediately direct the user to emergency services rather than self-care advice.
- **Scope framing:** all health output framed as general information, not diagnosis; encourage professional care for anything serious or persistent.
- **No definitive promises:** avoid guaranteed timelines/outcomes.

---

## 7. Tool Layer — Integration Landscape

Each capability maps to an existing API and/or MCP server. Maturity varies a lot;
this drives the phasing in §11.

| Capability | Integration option(s) | Notes / friction |
|-----------|----------------------|------------------|
| **Calendar** | Google Calendar official remote **MCP server** (OAuth 2.0); community MCP servers; Google Calendar REST API | Lowest-friction integration. Read + create/update/delete events. |
| **Email** | Gmail API; Gmail / Google Workspace **MCP servers** | Mature. Draft + send. |
| **Reminders** | Apple Reminders (device-local automation / MCP servers); local notifications | Device-bound; no universal cloud API. |
| **Messages / SMS** | No official iMessage API. Use an SMS provider (e.g., Twilio) for text notifications | iMessage is locked down; plan around it. |
| **Health portal (MyChart)** | **Epic on FHIR** / SMART on FHIR (OAuth 2.0, patient auth via MyChart) | Free sandbox with test patients; **production requires Epic app review**. Read (USCDI) is the easy path; write-back (scheduling, messaging) is heavier. |
| **Pharmacy** | **CVS Health Developer Portal** (Guest Refill, auto-refill APIs — OAuth2, must be provisioned); **Walgreens Developer Portal** (refill/transfer + scheduling) | Note: **Capsule is a separate company (capsule.com), not CVS.** Pharmacy APIs often gate access and may restrict to mobile apps. |
| **Delivery (groceries)** | **Instacart Developer Platform (IDP)** — public API | Public API does **not** place orders directly; it returns a link to an Instacart-hosted checkout page. ~30–40 day approval. |
| **Delivery (food)** | DoorDash / Uber Eats developer programs | Direct consumer-order APIs are limited; may require partner status or a link-out flow. |

**Design implication:** prefer **MCP servers** where they exist (calendar, email)
for fast wiring into the agent; treat health-portal and pharmacy/delivery as
longer-lead integrations that may start as *assisted handoffs* (Tara prepares the
action and hands the user a link/draft) before becoming fully automated.

---

## 8. Non-Functional Requirements

- **Privacy & security:** local-first storage; encrypt at rest and in transit; minimize data sent to third-party model providers; prefer on-device processing for the most sensitive content; clear retention and deletion controls.
- **Regulatory awareness:** in the US, personal health data and provider/insurer integrations raise HIPAA considerations; financial actions raise their own compliance questions. Design as if these matter — it shapes whether this can ever become a shippable product.
- **Reliability:** actions must be idempotent or confirmable (don't double-book, double-order, double-refill).
- **Auditability:** log every action taken on the user's behalf, viewable by the user.
- **Latency:** conversational responses feel real-time; long-running actions report progress.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Wrong or overconfident medical advice | Safety layer, conservative framing, emergency escalation, professional-care nudges. |
| Incorrect coverage/cost estimates | Always cite source doc; flag uncertainty; offer to verify with insurer first. |
| Unwanted actions (rogue ordering/booking/refill) | Hard confirmation gate; no consequential action without explicit "yes." |
| Data breach of sensitive PHI | Local-first, encryption, minimization, strict access control. |
| Integration brittleness / gated APIs | Start with assisted handoffs where direct APIs don't exist; degrade gracefully. |

---

## 10. Success Metrics (personal MVP)

- Ingest and correctly retrieve facts from ≥ 90% of uploaded document types.
- Answer a coverage/cost question with correct citation in one turn.
- Complete a full agentic flow (e.g., book + add to calendar + prep) end to end.
- Zero unconfirmed consequential actions.
- *You* actually use it weekly.

---

## 11. Phased Roadmap

**Phase 1 — Grounded Q&A (read-only).** Upload, parse, RAG, cite. No actions. Safety layer in place. *(See PHASE_1_TECHNICAL_DESIGN.md.)*

**Phase 2 — First actions.** Calendar + reminders (lowest-risk, no money/PHI leaving the system; calendar has an official MCP server). *(See [PHASE_2_TECHNICAL_DESIGN.md](PHASE_2_TECHNICAL_DESIGN.md) — also defines the shared orchestrator/tool/confirmation-gate foundations.)*

**Phase 3 — External actions.** Insurance email drafting, delivery/commerce, pharmacy refills — all behind the confirmation gate, starting as assisted handoffs. *(See [PHASE_3_TECHNICAL_DESIGN.md](PHASE_3_TECHNICAL_DESIGN.md).)*

**Phase 4 — Health-portal & proactive help.** Epic on FHIR (read, then scheduling); proactive prep and follow-ups. *(See [PHASE_4_TECHNICAL_DESIGN.md](PHASE_4_TECHNICAL_DESIGN.md).)*

---

> Open design questions live in **OPEN_QUESTIONS.md**.
