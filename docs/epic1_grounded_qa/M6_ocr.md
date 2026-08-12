# Epic 1 · M6 — ocr

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** branch of [M1](M1_ingestion_pipeline.md) detection; page-level citations surface in [M4](M4_grounded_answering.md); fidelity measured in [M8](M8_eval_harness.md).

---

- **Purpose:** the scanned-document / image extraction path — OCR with page-granularity citations.

### Design / contract

- Scanned PDFs and images: OCR instead of native extraction (branch decided in M1 detection).
- *Local-first preference:* on-device OCR (Tesseract) or a local vision model, so PHI doesn't leave the device.
- Keep a cloud-OCR option behind an explicit opt-in for hard cases.
- **OCR caveat:** OCR char offsets do not map to pixel coordinates, so citations on scanned docs resolve to **page granularity only** (no in-page highlight) — see M4.
- Downstream (chunking, embedding, indexing, retrieval, answering) is unchanged from M1/M3/M4.

### Data-model deltas

- None (same `documents`/`chunks` rows; spans are OCR-text offsets).

### Tests / acceptance

- **OCR fidelity:** spot-check extracted numbers on scanned lab reports / EOBs — a misread digit in a copay or result is a real harm (measured in M8).
- Citations on OCR'd docs resolve to the correct page.
