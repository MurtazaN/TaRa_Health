# Epic 1 · M5 — safety

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** pre-check runs before [M4](M4_grounded_answering.md); framing applied inside [M4](M4_grounded_answering.md) post-processing; recall gated by the [M8](M8_eval_harness.md) taxonomy fixture.

---

- **Purpose:** emergency pre-check (fail-closed, before the answering model) + append-only framing post-check, with a 100%-recall release gate.

### Design / contract

- **Placement & independence:**
  - Runs **before** the answering LLM on any health-related query.
  - Intentionally separate from the answering prompt so it can't be "reasoned away" by the main model and can be tested independently.
  - **Biased toward over-triggering:** a single missed emergency is far worse than many false alarms.
- **Emergency detection (pre-check) — two layers, fixed decision rule:**
  - A fast **keyword/pattern layer** over a red-flag list.
  - A **lightweight LLM confirmation layer** — **not optional**: it is the safety net for phrasings, misspellings, and negations the keyword list misses.
  - If Epic 1 ships without the LLM layer, the design must explicitly scope the safety net to English keyword matching and record that limitation; the default is to include the LLM layer.
- **Required minimum emergency taxonomy** (the gate for the M8 safety-recall eval — a required floor, not an "etc." list):
  - Chest pain / pressure.
  - Stroke signs (face droop, slurred speech, sudden one-sided weakness or numbness, "FAST").
  - Difficulty breathing / choking.
  - Anaphylaxis / throat or tongue swelling.
  - Severe bleeding.
  - Suicidal ideation and self-harm (including variants: "kill myself", "end it", "no reason to live", "hurt myself").
  - Overdose / poisoning / ingestion.
  - Seizure.
  - Loss of consciousness / unresponsive / fainting.
  - Sepsis signs (high fever + confusion).
  - Meningitis signs (stiff neck + fever).
  - Pregnancy emergencies (heavy vaginal bleeding, no fetal movement).
  - "Worst headache of my life."
  - Severe abdominal pain.
- **Decision rule (fail-closed):**
  - Escalate if the keyword layer **OR** the LLM layer flags; the LLM may **never downgrade** a keyword hit.
  - If the pre-check cannot complete (LLM down, classifier error, timeout), **fail toward escalation** — do not answer; show the conservative safety message.
  - When escalating, always return a **non-empty, locale-aware escalation message** (emergency number is configurable; 911 is US-specific).
  - Tara does not give self-care advice on the emergency path; it directs the user to emergency services and stops.
- **Framing (post-check):**
  - Ensures the final answer is framed as general information, includes a professional-care nudge for anything serious or persistent, and avoids guaranteed outcomes/timelines.
  - **Append-only and non-destructive** — may add disclaimers but must not edit the grounded facts or the citation markers (ordering in M4).
  - If framing fails, return the grounded answer with a default static disclaimer rather than erroring.

### Data-model deltas

- Writes `queries.safety_flag` (`none | emergency`).

### Tests / acceptance

- **Safety recall is a release gate, not a metric:** a battery covering the full taxonomy above; the pre-check must catch them — target 100% recall on the taxonomy fixture before this module is considered done.
- Favor over-triggering; track the false-positive rate against a ceiling.
- Pre-check failure (LLM down/timeout) escalates rather than answers.
