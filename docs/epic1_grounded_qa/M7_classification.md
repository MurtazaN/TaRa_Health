# Epic 1 · M7 — classification

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** runs inside the [M1](M1_ingestion_pipeline.md) pipeline; tags feed the [M3](M3_retrieval.md) post-filter (that contract lives in [M3](M3_retrieval.md)).

---

- **Purpose:** tag each document with a type and use inferred types to filter retrieval.

### Design / contract

- **Document classification (at ingest, M1 pipeline step):**
  - Tag each document: `insurance_policy`, `benefits_summary`, `eob`, `bill`, `lab_report`, `prescription`, `after_visit_summary`, `other`.
  - A small LLM call or a lightweight classifier is fine.
- **Powers metadata-filtered retrieval:** question-side type inference and the post-filter contract are specified in M3 (steps 2–3); this module supplies the document-side tags.
- Falls back gracefully: untyped/low-confidence docs remain retrievable via M3's unfiltered fallback.

### Data-model deltas

- Populates `documents.doc_type` (closed set above).

### Tests / acceptance

- Each fixture doc type classifies correctly.
- Type-filtered retrieval returns only chunks from allowed `doc_id`s; unfiltered fallback engages on low confidence.
