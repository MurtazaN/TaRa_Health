# TaRa Health

> Meet **Tara** — your personal AI health & insurance assistant. Upload your documents, ask questions, and let Tara handle the logistics.

---

## What it does

TaRa Health is an **agentic AI application**. You upload your own health and
insurance documents, and **Tara** can:

- 💬 **Answer questions** grounded in your actual documents ("What's my copay for a specialist?")
- 🧾 **Explain your coverage and costs** with citations to the source document
- 📅 **Take actions on your behalf** — add appointments to your calendar, draft messages to your insurer, set reminders, refill prescriptions, order food, and more
- 🛡️ **Stay safe** — Tara frames health guidance as general information, flags emergencies, and asks for confirmation before doing anything consequential

Tara does **not** diagnose conditions, prescribe treatment, or replace a licensed
clinician. See [Disclaimer](#disclaimer).

---

## Example interactions

**You:** I have a headache and I haven't eaten all day, what should I do?
**Tara:** Skipping meals can trigger headaches, so eating something is a good first step. If it doesn't ease up or it gets worse, consider checking in with a clinician. Want me to order food for you via a delivery app?

**You:** I think I need to see a doctor about my blood sugar.
**Tara:** Persistently high blood sugar is worth getting checked — a PCP visit with bloodwork is the usual next step. Based on your plan, that's a $20 copay for a PCP visit (or $30 for a specialist) plus ~$20 for labs. I can book the appointment through your provider portal and verify the exact cost with your insurer — which would you like first?

**You:** I have an appointment June 25, add it to my calendar.
**Tara:** Done — added to your calendar. Want me to help you prepare anything before the visit?

---

## Architecture

```
User ─▶ Tara Orchestrator (LLM planner)
          ├─ Retrieval (RAG over your local document store)
          ├─ Safety / triage layer
          ├─ Tools: calendar · email · reminders · health portal · pharmacy · delivery
          └─ Confirmation gate ─▶ action execution
```

Core loop: **perceive → plan → confirm → act → observe.**

This is a **single-profile**, **local-first** application: your data lives on
your device by default, and the app serves one user (you).

---

## Tech stack

> Fill in as you decide — suggested starting point:

- **Model / orchestration:** [LLM provider + agent framework, e.g. function calling / tool use]
- **Document parsing:** [PDF parser + OCR]
- **Vector store / retrieval:** [local-first vector store]
- **Backend:** [language / framework]
- **Frontend:** [web / mobile]
- **Integrations (via APIs / MCP servers):** Google Calendar, Gmail, Reminders, Epic on FHIR (MyChart), CVS/Walgreens pharmacy, Instacart

---

## Getting started

```bash
# Clone
git clone https://github.com/<you>/<repo>.git
cd <repo>

# Install dependencies
# (add real commands once stack is chosen)

# Configure environment
cp .env.example .env
# add your API keys

# Run
# (add run command)
```

---

## Privacy & security

This app handles sensitive personal health information. Principles:

- **Local-first:** data is stored on the user's device by default
- Encrypt data at rest and in transit
- Minimize data sent to third-party providers; prefer on-device processing where feasible
- User-controlled data retention and deletion
- Log every action Tara takes on the user's behalf for auditability

In the US, personal health data and provider/insurer integrations raise **HIPAA**
considerations. Design accordingly, even for personal use.

---

## License

**Proprietary — All Rights Reserved (for now).**

This started as a personal project and may become a product, so it is
intentionally *not* released under an open-source license yet. No permission is
granted to use, copy, modify, or distribute this code. A license may be chosen
later once the direction is clear. *(This is not legal advice.)*

---

## Disclaimer

TaRa Health provides **general information, not medical advice**. Tara is not a
diagnostic tool and does not replace a licensed healthcare professional. For any
emergency, contact your local emergency services immediately. Coverage and cost
estimates are derived from your uploaded documents and may be inaccurate — verify
with your insurer before relying on them.
