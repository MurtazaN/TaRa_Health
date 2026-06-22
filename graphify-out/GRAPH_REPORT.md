# Graph Report - .  (2026-06-21)

## Corpus Check
- Corpus is ~7,607 words - fits in a single context window. You may not need a graph.

## Summary
- 214 nodes · 234 edges · 24 communities detected
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.8)
- Token cost: 0 input · 70,419 output

## Community Hubs (Navigation)
- [[_COMMUNITY_App Wiring & Config|App Wiring & Config]]
- [[_COMMUNITY_Query Flow & Answering|Query Flow & Answering]]
- [[_COMMUNITY_Embeddings & Retrieval|Embeddings & Retrieval]]
- [[_COMMUNITY_LLM Client Abstraction|LLM Client Abstraction]]
- [[_COMMUNITY_Storage & Vector Index|Storage & Vector Index]]
- [[_COMMUNITY_Ingestion & App Endpoints|Ingestion & App Endpoints]]
- [[_COMMUNITY_Text Extraction & OCR Routing|Text Extraction & OCR Routing]]
- [[_COMMUNITY_Answerer & Prompts|Answerer & Prompts]]
- [[_COMMUNITY_Chunking & Provenance|Chunking & Provenance]]
- [[_COMMUNITY_Design Decisions & Docs|Design Decisions & Docs]]
- [[_COMMUNITY_Safety Triage (Emergency)|Safety Triage (Emergency)]]
- [[_COMMUNITY_Core Data Models|Core Data Models]]
- [[_COMMUNITY_Evaluation Harness|Evaluation Harness]]
- [[_COMMUNITY_Chunking|Chunking]]
- [[_COMMUNITY_Agentic Vision (Phase 2+)|Agentic Vision (Phase 2+)]]
- [[_COMMUNITY_Test Fixtures|Test Fixtures]]
- [[_COMMUNITY_Retrieval Tests|Retrieval Tests]]
- [[_COMMUNITY_Ingestion Tests|Ingestion Tests]]
- [[_COMMUNITY_Package Root|Package Root]]
- [[_COMMUNITY_Index Endpoint|Index Endpoint]]
- [[_COMMUNITY_Ask Endpoint|Ask Endpoint]]
- [[_COMMUNITY_Vector Add|Vector Add]]
- [[_COMMUNITY_Blob Load|Blob Load]]
- [[_COMMUNITY_Ingestion Pipeline|Ingestion Pipeline]]

## God Nodes (most connected - your core abstractions)
1. `ask (query flow)` - 11 edges
2. `get_settings()` - 9 edges
3. `ask()` - 9 edges
4. `get_settings` - 8 edges
5. `ingest` - 7 edges
6. `screen (emergency pre-check)` - 7 edges
7. `get_client()` - 6 edges
8. `ingest()` - 5 edges
9. `extract()` - 5 edges
10. `LLMClient` - 5 edges

## Surprising Connections (you probably didn't know these)
- `screen (emergency pre-check)` --implements--> `Safety layer (emergency detection + framing)`  [INFERRED]
  src/tara/safety/triage.py → docs/PRD.md
- `apply_framing (framing post-check)` --implements--> `Safety layer (emergency detection + framing)`  [INFERRED]
  src/tara/safety/framing.py → docs/PRD.md
- `retrieve` --implements--> `Retrieval (embed query + vector search + filter)`  [INFERRED]
  src/tara/retrieval/retriever.py → docs/PHASE_1_TECHNICAL_DESIGN.md
- `ANSWER_SYSTEM prompt` --implements--> `Answering LLM (grounding + citation)`  [INFERRED]
  src/tara/answering/prompts.py → docs/PHASE_1_TECHNICAL_DESIGN.md
- `Provenance-based citations` --conceptually_related_to--> `build_user_prompt`  [INFERRED]
  docs/PHASE_1_TECHNICAL_DESIGN.md → src/tara/answering/prompts.py

## Hyperedges (group relationships)
- **Document ingestion pipeline flow** — pipeline_ingest, blobs_save, extract_extract, classify_classify, chunk_chunk, embedder_embed_texts [EXTRACTED 1.00]
- **LLM provider abstraction** — base_llmclient, base_get_client, hosted_hostedclient, local_ollama_localollamaclient [EXTRACTED 1.00]
- **Citation provenance chain** — extract_extractedspan, chunk_chunk, models_chunk, models_citation [INFERRED 0.85]
- **Phase 1 query flow: safety pre-check, retrieve, answer, framing** — answerer_ask, triage_screen, retriever_retrieve, prompts_build_user_prompt, framing_apply_framing, answerer__extract_citations [EXTRACTED 0.90]
- **Separated safety layer (pre-check + post-check framing)** — triage_screen, framing_apply_framing, prd_safety_layer [INFERRED 0.85]
- **Phase 1 eval metrics battery** — eval_harness_main, test_safety_test_emergencies_are_caught, test_retrieval_test_topk_hit_rate, test_ingestion_test_extract_preserves_provenance [INFERRED 0.75]

## Communities (27 total, 10 thin omitted)

### Community 0 - "App Wiring & Config"
Cohesion: 0.09
Nodes (27): main entry point, upload endpoint, get_client, LLMClient protocol, Provider selection as config not code, blobs save, classify, Document-type-filtered retrieval (+19 more)

### Community 1 - "Query Flow & Answering"
Cohesion: 0.11
Nodes (23): _extract_citations, Answer, ask (query flow), web client app.js, fixtures_dir fixture, eval_harness main, apply_framing (framing post-check), index.html placeholder UI (+15 more)

### Community 2 - "Embeddings & Retrieval"
Cohesion: 0.11
Nodes (14): BaseSettings, embed_query(), embed_texts(), _model(), Local, on-device embeddings via sentence-transformers. No data leaves the device, Retrieve the chunks most relevant to a question, optionally filtered by the docu, # TODO: vector.search(_qvec, k, doc_ids filtered by doc_type_hint),, retrieve() (+6 more)

### Community 3 - "LLM Client Abstraction"
Cohesion: 0.13
Nodes (11): get_client(), LLMClient, LLM client interface. The rest of the app depends only on this protocol, so loca, Return the model's text response., Pick a client based on config.model_mode.      - local  -> always LocalOllamaCli, HostedClient, Hosted frontier model. Only used in hosted mode, or hybrid mode when the user ex, # TODO: call the hosted provider with settings.hosted_model. (+3 more)

### Community 4 - "Storage & Vector Index"
Cohesion: 0.15
Nodes (13): main(), Initialize the local database + vector table. Run once before first use:      py, connect(), init_schema(), SQLite connection + schema. Uses SQLCipher for at-rest encryption when a db_key, # TODO: when settings.db_key is set, open via pysqlcipher3 and run, add(), init_vector_table() (+5 more)

### Community 5 - "Ingestion & App Endpoints"
Cohesion: 0.13
Nodes (11): classify(), Tag each document with a DocType. Drives document-type-filtered retrieval (e.g.,, TODO: lightweight classifier — keyword heuristics first, optional small     LLM, ingest(), End-to-end ingestion: upload bytes -> stored, classified, chunked, embedded, and, # TODO: persist Document + chunks (storage.db) and embeddings (storage.vector),, ask_endpoint(), main() (+3 more)

### Community 6 - "Text Extraction & OCR Routing"
Cohesion: 0.17
Nodes (13): Enum, detect(), Decide how to extract: native-text PDF vs scanned PDF vs image. The branch matte, TODO: inspect the file. Heuristic: if a PDF yields little/no extractable     tex, SourceKind, extract(), _extract_docling(), _extract_pymupdf() (+5 more)

### Community 7 - "Answerer & Prompts"
Cohesion: 0.16
Nodes (11): Answer, ask(), _extract_citations(), Top-level query flow — the heart of Phase 1:      SAFETY pre-check -> (emergency, TODO: parse [chunk_id] markers from the model output and map each to a     Citat, build_user_prompt(), Prompt templates for grounded, citable answering., excerpts: [{chunk_id, filename, page, text}, ...] (+3 more)

### Community 8 - "Chunking & Provenance"
Cohesion: 0.2
Nodes (12): chunk, Structural chunking with provenance, detect, OCR vs native-text extraction routing, SourceKind, _extract_docling, _extract_pymupdf, extract (+4 more)

### Community 9 - "Design Decisions & Docs"
Cohesion: 0.25
Nodes (9): CLAUDE.md repo guidance, init_db main, Local-first storage decision, Model/provider choice (local vs hosted vs hybrid), Single-profile decision, Local storage (SQLite + sqlite-vec), Phase 1 Technical Design, TaRa Health PRD (+1 more)

### Community 10 - "Safety Triage (Emergency)"
Cohesion: 0.25
Nodes (6): Emergency PRE-check. Runs BEFORE the answering model on any health query. Kept s, TODO: fast keyword pass + optional lightweight LLM confirmation.     On emergenc, screen(), TriageResult, Safety is the highest-stakes layer — test it hardest. TODO: a battery of emergen, test_emergencies_are_caught()

### Community 11 - "Core Data Models"
Cohesion: 0.33
Nodes (5): Chunk, Citation, Document, Core data models. A Chunk always carries enough provenance (doc + page + char sp, What the UI shows: maps a used chunk back to its source location.

### Community 13 - "Chunking"
Cohesion: 0.5
Nodes (3): chunk(), Chunk extracted text for retrieval while carrying page + char span through. Pref, TODO: merge/split spans into ~target_tokens chunks with overlap,     preserving

### Community 14 - "Agentic Vision (Phase 2+)"
Cohesion: 0.5
Nodes (4): Agentic application, Confirmation gate, Tool layer / integration landscape, TaRa Health README

## Knowledge Gaps
- **80 isolated node(s):** `Shared fixtures. Put sample documents (a benefits summary, a lab report, an EOB,`, `TODO: curated question -> expected-chunk pairs; measure top-k hit rate and that`, `Phase 1 evaluation harness (see PHASE_1_TECHNICAL_DESIGN.md §8):    - retrieval`, `# TODO: load labeled cases from tests/fixtures, run each metric, print a report.`, `Safety is the highest-stakes layer — test it hardest. TODO: a battery of emergen` (+75 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_settings()` connect `Embeddings & Retrieval` to `LLM Client Abstraction`, `Storage & Vector Index`?**
  _High betweenness centrality (0.125) - this node is a cross-community bridge._
- **Why does `ask()` connect `Answerer & Prompts` to `LLM Client Abstraction`, `Safety Triage (Emergency)`, `Embeddings & Retrieval`, `Ingestion & App Endpoints`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Why does `ingest()` connect `Ingestion & App Endpoints` to `Embeddings & Retrieval`, `Text Extraction & OCR Routing`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `ask (query flow)` (e.g. with `RetrievedChunk` and `TriageResult`) actually correct?**
  _`ask (query flow)` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `get_settings()` (e.g. with `.complete()` and `get_client()`) actually correct?**
  _`get_settings()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `ask()` (e.g. with `ask_endpoint()` and `screen()`) actually correct?**
  _`ask()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Shared fixtures. Put sample documents (a benefits summary, a lab report, an EOB,`, `TODO: curated question -> expected-chunk pairs; measure top-k hit rate and that`, `Phase 1 evaluation harness (see PHASE_1_TECHNICAL_DESIGN.md §8):    - retrieval` to the rest of the system?**
  _80 weakly-connected nodes found - possible documentation gaps or missing edges._