# Epic 1 · M3 — retrieval

- **Parent:** [Epic 1 — Grounded Q&A](README.md) — overview · build order · cross-cutting safety & privacy · repo layout.
- **Seams:** searches [M2](M2_local_storage.md) vectors; doc-type filter fed by [M7](M7_classification.md) tags; abstention guard complements the [M4](M4_grounded_answering.md) honesty rule.

---

- **Purpose:** embed the query, filter by inferred document type, post-filter KNN results, abstain when weak, and assemble token-budgeted context.

### Design / contract

1. Embed the query (same on-device model as indexing).
2. **Infer document type** from the question (a small rule/LLM step):
   - cost/coverage → `insurance_policy`/`benefits_summary`/`eob`/`bill`; "my results" → `lab_report`; medication → `prescription`; etc.
   - The inferred type(s) are translated to the matching `doc_id`s via a `documents` lookup.
   - Classification of documents themselves is M7.
3. **Vector search with a document-type filter:**
   - sqlite-vec `vec0` does **not** support an arbitrary `WHERE` on non-vector columns inside the KNN query.
   - Contract is therefore **post-filtering**: run KNN for `k * multiplier`, then keep the first `k` whose `doc_id` is in the allowed set (correct and cheap at single-user scale).
   - Falls back to unfiltered search if type inference is low-confidence.
4. Optional rerank for precision.
5. **Abstention guard:**
   - If the best retrieval score is below a configured threshold, treat the question as unsupported — the answerer should decline ("I don't see that in your documents") rather than stretch weak context.
   - Complements the prompt-level honesty rule (M4).
6. Assemble the top-k chunks into context, each tagged with its `chunk_id` and source (doc name + page):
   - **Cap the assembled context to a token budget** sized to the answering model's window (`qwen3:8b` is small).
   - Reduce `k` before overflowing rather than truncating mid-chunk.

### Data-model deltas

- None (reads `documents`/`chunks`/`vec_chunks`; writes nothing).

### Tests / acceptance

- Curated Q→expected-chunk pairs retrieve the right chunk (top-k hit rate; measured in M8 via `queries.retrieved_chunk_ids`).
- Below-threshold best score triggers abstention.
- Post-filter keeps only allowed `doc_id`s; low-confidence inference falls back to unfiltered.
