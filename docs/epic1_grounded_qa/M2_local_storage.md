# Epic 1 · M2 — local_storage

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** written by [M1](M1_ingestion_pipeline.md); read by [M3](M3_retrieval.md); `index_meta` guards embeddings for [M1](M1_ingestion_pipeline.md)/[M3](M3_retrieval.md); purge serves [M1](M1_ingestion_pipeline.md) replace + the Privacy delete guarantee ([README](README.md)).

---

- **Purpose:** the on-device state plane — SQLite + sqlite-vec, schema, purge, encryption, and embedding-index integrity.

### Design / contract

- **Three stores, all on device:**
  - **Blob store:** the original uploaded files (for display + re-processing).
  - **Metadata DB:** documents, chunks, page map, classification, timestamps, the query/audit log, and an index-metadata row (embedding model + dimension).
  - **Vector index:** chunk embeddings for similarity search.
- **Decision — SQLite + sqlite-vec for both metadata DB and vector index:**
  - One portable file under `TARA_DATA_DIR`, with the original blobs alongside.
  - LanceDB and Chroma were considered; SQLite won for keeping everything in a single portable file — backup/migration is "copy the file" — which best fits local-first.
  - The vector table is created separately from the relational schema because it needs the sqlite-vec extension loaded; it is created on a separate connection against the same db file (not the same connection object).
  - Connections opened for request handlers use `check_same_thread=False` because FastAPI runs sync handlers in a threadpool.
  - `connect_db()` sets `PRAGMA foreign_keys = ON` so declared cascades actually fire.
- **Embedding model/dimension integrity:**
  - `TARA_EMBED_DIM` must match `TARA_EMBED_MODEL`; the `vec0` table bakes the dimension in at creation, so a later model change silently corrupts search. Therefore:
    1. At startup, validate `embed_dim == model.get_sentence_embedding_dimension()`; fail loudly on mismatch.
    2. Persist the embedding model name + dimension as an index-metadata row when the store is first created.
    3. If `TARA_EMBED_MODEL` changes after indexing, that is a **re-index migration**: drop and rebuild the vector table and re-embed all chunks.
  - The mismatch is detected by comparing config against the stored index-metadata row; the app refuses to serve queries against a stale index rather than returning garbage distances.
- **Document purge (buildable delete):**
  - The `vec_chunks` virtual table has no foreign-key relationship to `chunks`, so deletion is **not** automatic.
  - `purge_document(doc_id)`, in one transaction, must:
    1. Delete the `vec_chunks` rows for the document's `chunk_id`s explicitly.
    2. Delete `chunks` (the `documents`→`chunks` cascade fires now that `foreign_keys` is ON).
    3. Delete the `documents` row.
    4. Delete the blob file.
    5. Delete or redact related `queries` rows per the retention policy (see Privacy).
  - Order steps so a failure leaves no "document gone but vectors remain" state.
- **Encryption at rest:**
  - SQLCipher (optional `[encryption]` extra) encrypts the DB file when `TARA_DB_KEY` is set.
  - **Blobs are the richest PHI and are not covered by SQLCipher** — when `TARA_DB_KEY` is set, blob files are encrypted with the same key (AES-GCM).
  - Default install (no key) stores both DB and blobs **unencrypted** — see the Privacy section for the reconciled posture and residual-risk statement.

### Data-model (base sketch for the epic)

```
documents
  doc_id          (pk)
  filename
  doc_type        (insurance_policy | lab_report | eob | bill | ...)
  content_hash    (for re-ingest dedup; M1)
  status          (indexing | indexed | indexing_failed; M1)
  uploaded_at     (ISO-8601 UTC string; use datetime.now(timezone.utc))
  page_count

chunks
  chunk_id        (pk)  -- deterministic: "{doc_id}:{page}:{char_start}"
  doc_id          (fk -> documents, ON DELETE CASCADE)
  page
  char_start
  char_end
  text
  embedding       (vector; stored in the vec_chunks vec0 table, keyed by chunk_id)

index_meta                       -- guards model/dim integrity (M2)
  embed_model
  embed_dim
  created_at

queries            (audit/eval; written on every answered query)
  query_id        (pk)
  question
  retrieved_chunk_ids            -- needed by the M8 retrieval eval
  answer
  citations                      -- chunk_id + page + char span
  safety_flag     (none | emergency)
  model_route     (local | hosted)   -- so PHI egress is auditable (Privacy)
  created_at
```

- A runtime **`Citation`** maps a cited `chunk_id` to `{filename, page, char_start, char_end, snippet}` for display (M4).

### Tests / acceptance

- Schema builds; FK cascade fires on document delete.
- Embed model/dim mismatch vs `index_meta` refuses to serve queries.
- `purge_document` leaves no rows, vectors, or blob behind, in any failure order.
