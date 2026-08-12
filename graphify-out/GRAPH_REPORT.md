# Graph Report - tara_health  (2026-08-12)

## Corpus Check
- 62 files · ~26,798 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 348 nodes · 515 edges · 23 communities detected
- Extraction: 67% EXTRACTED · 33% INFERRED · 0% AMBIGUOUS · INFERRED: 172 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e9eb2e2a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]

## God Nodes (most connected - your core abstractions)
1. `connect_db()` - 34 edges
2. `make_pdf()` - 19 edges
3. `get_settings()` - 19 edges
4. `ingest_document()` - 19 edges
5. `retrieve_chunks()` - 12 edges
6. `get_llm_client()` - 11 edges
7. `validate_upload()` - 10 edges
8. `answer_question()` - 9 edges
9. `init_db_schema()` - 9 edges
10. `_settings()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `test_find_nearest_chunks_returns_empty_for_nonpositive_max_results()` --calls--> `connect_db()`  [INFERRED]
  tests/local_data_stores/test_vector_index.py → src/tara/local_data_stores/db_connection.py
- `test_validate_upload_rejects_bad_extension()` --calls--> `validate_upload()`  [INFERRED]
  tests/test_upload_validation.py → src/tara/upload_validation.py
- `test_validate_upload_rejects_oversize()` --calls--> `validate_upload()`  [INFERRED]
  tests/test_upload_validation.py → src/tara/upload_validation.py
- `test_validate_upload_rejects_empty()` --calls--> `validate_upload()`  [INFERRED]
  tests/test_upload_validation.py → src/tara/upload_validation.py
- `test_validate_upload_accepts_good()` --calls--> `validate_upload()`  [INFERRED]
  tests/test_upload_validation.py → src/tara/upload_validation.py

## Communities (26 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (36): _clean_up_failed_ingest(), ingest_document(), Ingests one uploaded document: bytes in -> stored, chunked, embedded, and indexe, Best-effort recovery so a failed ingest leaves no inconsistent state (§3.1g)., Ingestion pipeline orchestration: transactional writes, content-hash dedup, repl, test_failed_document_is_invisible_to_retrieval(), test_failed_extraction_cleans_up_blob_and_leaves_no_indexed_doc(), test_ingest_indexes_document_with_chunks_and_vectors() (+28 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (33): connect_db(), Opens connections to the on-device metadata database.  Every relational read/wri, Open a connection to the on-device metadata database, ready for use     (row acc, # TODO: when settings.db_key is set, open via pysqlcipher3 and run, init_db_schema(), Defines and creates the metadata database's relational schema (documents, chunks, Create all relational tables and indexes. Idempotent; run once at startup., Deletes a document completely: its vectors, chunk rows, document row, and the or (+25 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (21): HostedLLMClient, Calls the hosted (remote) frontier model — the only code path where document tex, LLMClient backed by a remote provider (wired up in Slice 2)., get_llm_client(), LLMClient, Defines how the app calls a text-generation model.  `LLMClient` is the protocol, A text-generation backend: takes prompts, returns the model's text., Return the model's text response for one system+user prompt pair. (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (22): Chunking: page-bounded, deterministic ids, exact-offset slices, and overlap., test_chunk_is_page_bounded_and_deterministic(), test_chunk_splits_large_pages(), test_consecutive_chunks_overlap_when_overlap_tokens_positive(), Text extraction preserves page + char-span provenance (the citation invariant)., test_extract_preserves_page_and_span_invariant(), _approximate_token_count(), _chunk_single_span() (+14 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (19): BaseModel, detect_source_kind(), Decide how to extract: native-text PDF vs scanned PDF vs image (design §3.1a/b)., Classify how to extract. Assumes the upload already passed validate_upload., SourceKind, Source-kind detection: native-text PDF vs scan vs image, and the page cap., test_detect_image_routes_to_ocr(), test_detect_native_text_pdf() (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (17): BaseSettings, _embed_dim_is_positive(), ensure_data_dirs(), Application configuration, loaded from environment / .env.  All paths and model, Create the on-device storage directories, owner-only (PHI on disk). Call     onc, _require_hosted_key_when_egressing(), Settings, Config contracts (design §3.2, §3.5): egress-requires-credential validator, embe (+9 more)

### Community 6 - "Community 6"
Cohesion: 0.1
Nodes (17): all_doc_ids(), delete_document_row(), document_from_row(), find_indexed_document_by_hash(), insert_document_row(), mark_document_status(), Row-level operations on the `documents` table — the only module that writes or r, Build a Document dataclass from a `documents` table row. (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.1
Nodes (17): build_user_prompt(), Prompt templates for grounded, citable answering., Assemble the user-role prompt: tagged document excerpts, then the question., Answer, answer_question(), _map_cited_chunks_to_citations(), Answers a user's question from their documents — the full Phase 1 query flow.  `, Parse the [chunk_id] markers the model emitted and map each to a Citation. (+9 more)

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (16): delete_blob(), Original uploaded files ("blobs"), stored on disk under config.blob_dir.  The bl, Remove the blob for a document (any suffix). Idempotent., save_blob(), embed_query(), embed_texts(), _embedding_api_client(), _normalize_to_unit_length() (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (14): chunk_ids_for_document(), ChunkWithSource, fetch_chunk_with_filename(), insert_chunk_rows(), Row-level operations on the `chunks` table — the only module that writes or read, A stored chunk joined with its owning document's display facts., Insert all chunk rows for a document in one batch., Return the chunk_ids belonging to one document (used to delete their     vec_chu (+6 more)

### Community 10 - "Community 10"
Cohesion: 0.19
Nodes (13): An upload failed boundary validation (extension, size, or page count).     Raise, UploadError, Upload boundary validation (design §3.1a), shared across layers.  Lives at the p, Return the file's lower-cased suffix, or raise UploadError if not whitelisted., Fail fast on a malformed/oversized upload before any processing (§3.1a).      Va, validate_upload(), validated_file_suffix(), Upload boundary validation: extension whitelist, size ceiling, empty check. (+5 more)

### Community 11 - "Community 11"
Cohesion: 0.19
Nodes (10): _index_one_chunk(), sqlite-vec KNN wrapper: nearest-chunk search, doc_id post-filtering, and explici, test_delete_embeddings_removes_vector_rows(), test_find_nearest_chunks_post_filters_by_doc_id(), test_find_nearest_chunks_returns_empty_for_nonpositive_max_results(), fake_embed_one(), isolated_env(), Shared fixtures. Put sample documents (a benefits summary, a lab report, an EOB, (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.2
Nodes (5): fake_embedding_client(), _FakeClient, _FakeEmbedding, _FakeEmbeddings, Embedder unit tests: OpenAI-compatible call shape, order preservation, unit-norm

### Community 13 - "Community 13"
Cohesion: 0.18
Nodes (9): add_embeddings(), delete_embeddings(), find_nearest_chunks(), load_vector_extension(), Vector index backed by sqlite-vec. One row per chunk, keyed by chunk_id.  Caller, Load the sqlite-vec extension on this connection (idempotent, per-connection)., Batch insert (chunk_id, embedding) pairs for ingestion throughput., Delete vector rows by chunk_id (no FK to chunks, so this is explicit; §3.2). (+1 more)

### Community 15 - "Community 15"
Cohesion: 0.32
Nodes (7): ensure_index_meta(), Reads and writes the index_meta singleton row — the record of which embedding mo, Return the (embed_model, embed_dim) the index was built with, or None., Persist the embedding model/dim as the singleton index-metadata row., First index creation records the model/dim; afterwards a config change is a, read_index_meta(), write_index_meta()

### Community 18 - "Community 18"
Cohesion: 0.5
Nodes (3): classify_doc_type(), Assigns a document-type label (DocType) to an extracted document's text.  `class, Return the DocType for a document given its full extracted text.      TODO (Slic

## Knowledge Gaps
- **114 isolated node(s):** `Web API surface: upload/ask endpoints, domain-error -> HTTP status mapping, and`, `Shared fixtures. Put sample documents (a benefits summary, a lab report, an EOB,`, `Point TaRa's storage at an isolated tmp dir and reset the cached settings.`, `Deterministic bag-of-words embedding hashed into `dim` buckets, unit-normalized.`, `Factory: build an in-memory text PDF from lines-per-page. Returns bytes.` (+109 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_settings()` connect `Community 8` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 10`?**
  _High betweenness centrality (0.329) - this node is a cross-community bridge._
- **Why does `connect_db()` connect `Community 1` to `Community 0`, `Community 9`, `Community 11`, `Community 8`?**
  _High betweenness centrality (0.230) - this node is a cross-community bridge._
- **Why does `ingest_document()` connect `Community 0` to `Community 1`, `Community 3`, `Community 4`, `Community 6`, `Community 8`, `Community 10`?**
  _High betweenness centrality (0.203) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `connect_db()` (e.g. with `offline_ingest_env()` and `test_purge_removes_rows_vectors_and_blob()`) actually correct?**
  _`connect_db()` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `make_pdf()` (e.g. with `test_upload_ingests_pdf_and_returns_document_facts()` and `test_purge_removes_rows_vectors_and_blob()`) actually correct?**
  _`make_pdf()` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `get_settings()` (e.g. with `validate_upload()` and `init_vector_table()`) actually correct?**
  _`get_settings()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ingest_document()` (e.g. with `test_purge_removes_rows_vectors_and_blob()` and `test_reconcile_removes_orphan_blobs_only()`) actually correct?**
  _`ingest_document()` has 17 INFERRED edges - model-reasoned connections that need verification._