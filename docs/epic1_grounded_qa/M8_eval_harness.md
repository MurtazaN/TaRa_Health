# Epic 1 · M8 — eval_harness

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** measures [M1](M1_ingestion_pipeline.md) / [M3](M3_retrieval.md) / [M4](M4_grounded_answering.md) / [M6](M6_ocr.md); safety recall gates [M5](M5_safety.md); settles [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) #1.

---

- **Purpose:** measurable Epic-1 quality — retrieval, citation, value accuracy, honesty, safety recall, OCR fidelity — against a fixture set of sample documents.

### Design / contract (metrics)

- **Retrieval accuracy:** curated Q→expected-chunk pairs across each doc type; measure top-k hit rate (uses `queries.retrieved_chunk_ids`).
- **Citation correctness:** does the cited page actually contain the stated fact?
- **Value/numeric accuracy:** for answerable cost/coverage/lab questions, does the stated **number** match ground truth — not just the citation page? A wrong-but-cited figure is a higher-harm failure than a refusal.
- **Hallucination / honesty:** ask questions the docs *can't* answer; the system must decline (prompt rule + the M3 abstention guard), not invent.
- **Safety recall (release gate):** the full M5 emergency taxonomy battery — gates M5, not deferred to this module's build step.
- **OCR fidelity:** spot-check extracted numbers on scanned lab reports / EOBs (M6).

### Data-model deltas

- None (reads the `queries` audit log).

### Tests / acceptance

- Harness runs over the fixture set and reports all six metric groups.
- Also settles OPEN_QUESTIONS.md #1: measure citation correctness and honesty for `local` vs `hosted` and pick the default with evidence.
