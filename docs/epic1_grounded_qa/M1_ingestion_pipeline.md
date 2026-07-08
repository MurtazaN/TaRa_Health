# Epic 1 · M1 — ingestion_pipeline

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** feeds [M2](M2_local_storage.md) (rows · vectors · blobs); span provenance consumed by [M4](M4_grounded_answering.md) citations; OCR branch → [M6](M6_ocr.md); classification step → [M7](M7_classification.md); replace-flow uses the [M2](M2_local_storage.md) purge contract.

---

- **Purpose:** turn an uploaded file into indexed, citable chunks — detect → extract(+spans) → chunk → embed → index, as one transactional unit.

### Design / contract

- **File-type detection + upload validation (boundary):**
  - Accept PDF and image formats; branch on whether the PDF has a real text layer vs. is a scan.
  - Validate at this boundary: enforce a maximum upload size (`TARA_MAX_UPLOAD_BYTES`, default 50 MB) and an allowed-extension whitelist (`.pdf, .png, .jpg, .jpeg, .tiff`) **before any processing** — a malformed or oversized upload fails fast rather than OOM-ing the process.
- **Text extraction (native-text PDFs):**
  - Extract text + per-word/character positions and page numbers.
  - **Char spans must index into a single canonical text representation** (the exact string stored on the chunk), not a reflowed/markdown rendering.
  - Practically: use a raw-position API (e.g. PyMuPDF `get_text("words"/"rawdict")`), not a markdown exporter — a markdown layer rearranges characters (headers, table wrapping) and breaks the offset↔source mapping citations depend on.
  - Preserve **page number** and **character span** for every extracted piece — this is what makes citations possible later.
  - Scanned PDFs and images take the OCR path — see **M6**.
  - Document classification happens in this pipeline but is specified in **M7**.
- **Chunking:**
  - Split text into retrievable chunks (e.g., ~500–1000 tokens with overlap).
  - Chunk *structurally* where possible — insurance docs have tables and sections; lab reports have result tables.
  - Each chunk stores `{chunk_id, doc_id, page, char_start, char_end, text}`.
  - **Chunk IDs are deterministic:** `chunk_id = f"{doc_id}:{page}:{char_start}"` — stable IDs keep historical citations in the audit log valid and make re-ingest idempotent.
  - **A chunk never crosses a page boundary:** `Chunk.page` is a single page, so any chunk that would span pages is split at the boundary — `(page, char_start, char_end)` stays well-defined and citable.
- **Embedding + indexing:**
  - Embed each chunk and store the vector in the local index.
  - *Local-first preference:* on-device embedding model, so document text never leaves the device during indexing.
  - **Embeddings stay local in every `TARA_MODEL_MODE`, including `hosted`** — only the answering step may egress (M4).
  - The embedding dimension is validated against the model at startup (M2).
- **Idempotency & re-ingest:**
  - On upload, compute a content hash of the file bytes; store it on the document row.
  - If a document with the same hash already exists, do **not** create a duplicate — default is **reject-as-duplicate** (report "already indexed").
  - `replace=true` upload: delete the prior document (via the purge contract, M2) and re-index in a single transaction.
  - Prevents duplicate documents/chunks/vectors and dangling citations.
- **Failure handling & transactionality:** ingestion writes to three stores; a crash mid-way must not leave them inconsistent. Ordering and rules:
  1. Write the blob to disk first; record its path.
  2. Insert the `documents` row and all `chunks` rows in **one DB transaction** (`status='indexing'`).
  3. Insert vectors keyed by `chunk_id`.
  4. On success, set `status='indexed'` and confirm "Indexed N pages from <filename>".
  - On any exception: roll back the DB transaction, delete the orphan blob, and — if the doc row was already committed — mark `status='indexing_failed'` rather than leaving an unknown state.
  - A document not in `status='indexed'` is invisible to retrieval.

### Data-model deltas

- Owns the `documents.content_hash` (dedup) and `documents.status` (`indexing | indexed | indexing_failed`) semantics; schema lives in M2.

### Tests / acceptance

- Fixture PDF ingests end to end; chunks carry correct `(page, char_start, char_end)` into the canonical text.
- Re-ingest of the same file is rejected as duplicate; `replace=true` swaps atomically.
- Induced failure mid-pipeline leaves no orphan blob, no partial rows, and the document invisible to retrieval.
