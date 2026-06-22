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

> Phase 1 (current) — read-only grounded Q&A. The action/integration rows below
> are the Phase 2+ vision and are **not** implemented yet.

- **Model / orchestration:** local-first via Ollama (`qwen3:8b`), with a `local` / `hosted` / `hybrid` config switch; hosted path uses Anthropic (`claude-sonnet-4-6`)
- **Document parsing:** PyMuPDF / pdfplumber for native-text PDFs (page + char spans preserved for citations); Tesseract OCR for scans *(Phase 1 build step 5)*
- **Vector store / retrieval:** SQLite + sqlite-vec in one portable, on-device file; local `BAAI/bge-small-en-v1.5` embeddings
- **Backend:** Python 3.11+ / FastAPI (`tara` console script)
- **Frontend:** minimal local web UI served by FastAPI
- **Integrations (Phase 2+, not yet built):** Google Calendar, Gmail, Reminders, Epic on FHIR (MyChart), CVS/Walgreens pharmacy, Instacart

---

## Getting started

```bash
# Clone
git clone https://github.com/<you>/<repo>.git
cd <repo>

# Install (dev tools: pytest, ruff, mypy)
pip install -e ".[dev]"

# Pull the local model named in .env (TARA_LOCAL_MODEL)
ollama pull qwen3:8b

# Configure environment (model mode, paths, models)
cp .env.example .env

# Create the SQLite schema + sqlite-vec table (run once)
python scripts/init_db.py

# Run the local server at http://127.0.0.1:8000
tara
```

> Optional encrypted-at-rest storage: `pip install -e ".[encryption]"` (pulls
> SQLCipher; kept optional so the default install works out of the box).

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
