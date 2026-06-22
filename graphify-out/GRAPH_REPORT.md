# Graph Report - tara_health  (2026-06-21)

## Corpus Check
- 36 files · ~7,607 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 214 nodes · 234 edges · 24 communities detected
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1b6fb17c`
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
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]

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

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (27): main entry point, upload endpoint, get_client, LLMClient protocol, Provider selection as config not code, blobs save, classify, Document-type-filtered retrieval (+19 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (23): _extract_citations, Answer, ask (query flow), web client app.js, fixtures_dir fixture, eval_harness main, apply_framing (framing post-check), index.html placeholder UI (+15 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (14): BaseSettings, embed_query(), embed_texts(), _model(), Local, on-device embeddings via sentence-transformers. No data leaves the device, Retrieve the chunks most relevant to a question, optionally filtered by the docu, # TODO: vector.search(_qvec, k, doc_ids filtered by doc_type_hint),, retrieve() (+6 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (11): get_client(), LLMClient, LLM client interface. The rest of the app depends only on this protocol, so loca, Return the model's text response., Pick a client based on config.model_mode.      - local  -> always LocalOllamaCli, HostedClient, Hosted frontier model. Only used in hosted mode, or hybrid mode when the user ex, # TODO: call the hosted provider with settings.hosted_model. (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.15
Nodes (13): main(), Initialize the local database + vector table. Run once before first use:      py, connect(), init_schema(), SQLite connection + schema. Uses SQLCipher for at-rest encryption when a db_key, # TODO: when settings.db_key is set, open via pysqlcipher3 and run, add(), init_vector_table() (+5 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (11): classify(), Tag each document with a DocType. Drives document-type-filtered retrieval (e.g.,, TODO: lightweight classifier — keyword heuristics first, optional small     LLM, ingest(), End-to-end ingestion: upload bytes -> stored, classified, chunked, embedded, and, # TODO: persist Document + chunks (storage.db) and embeddings (storage.vector),, ask_endpoint(), main() (+3 more)

### Community 6 - "Community 6"
Cohesion: 0.17
Nodes (13): Enum, detect(), Decide how to extract: native-text PDF vs scanned PDF vs image. The branch matte, TODO: inspect the file. Heuristic: if a PDF yields little/no extractable     tex, SourceKind, extract(), _extract_docling(), _extract_pymupdf() (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (11): Answer, ask(), _extract_citations(), Top-level query flow — the heart of Phase 1:      SAFETY pre-check -> (emergency, TODO: parse [chunk_id] markers from the model output and map each to a     Citat, build_user_prompt(), Prompt templates for grounded, citable answering., excerpts: [{chunk_id, filename, page, text}, ...] (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.2
Nodes (12): chunk, Structural chunking with provenance, detect, OCR vs native-text extraction routing, SourceKind, _extract_docling, _extract_pymupdf, extract (+4 more)

### Community 9 - "Community 9"
Cohesion: 0.25
Nodes (9): CLAUDE.md repo guidance, init_db main, Local-first storage decision, Model/provider choice (local vs hosted vs hybrid), Single-profile decision, Local storage (SQLite + sqlite-vec), Phase 1 Technical Design, TaRa Health PRD (+1 more)

### Community 10 - "Community 10"
Cohesion: 0.25
Nodes (6): Emergency PRE-check. Runs BEFORE the answering model on any health query. Kept s, TODO: fast keyword pass + optional lightweight LLM confirmation.     On emergenc, screen(), TriageResult, Safety is the highest-stakes layer — test it hardest. TODO: a battery of emergen, test_emergencies_are_caught()

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (5): Chunk, Citation, Document, Core data models. A Chunk always carries enough provenance (doc + page + char sp, What the UI shows: maps a used chunk back to its source location.

### Community 13 - "Community 13"
Cohesion: 0.5
Nodes (3): chunk(), Chunk extracted text for retrieval while carrying page + char span through. Pref, TODO: merge/split spans into ~target_tokens chunks with overlap,     preserving

### Community 14 - "Community 14"
Cohesion: 0.5
Nodes (4): Agentic application, Confirmation gate, Tool layer / integration landscape, TaRa Health README

## Knowledge Gaps
- **83 isolated node(s):** `Shared fixtures. Put sample documents (a benefits summary, a lab report, an EOB,`, `TODO: curated question -> expected-chunk pairs; measure top-k hit rate and that`, `Phase 1 evaluation harness (see PHASE_1_TECHNICAL_DESIGN.md §8):    - retrieval`, `# TODO: load labeled cases from tests/fixtures, run each metric, print a report.`, `Safety is the highest-stakes layer — test it hardest. TODO: a battery of emergen` (+78 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_settings()` connect `Community 2` to `Community 3`, `Community 4`?**
  _High betweenness centrality (0.125) - this node is a cross-community bridge._
- **Why does `ask()` connect `Community 7` to `Community 3`, `Community 10`, `Community 2`, `Community 5`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Why does `ingest()` connect `Community 5` to `Community 2`, `Community 6`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `ask (query flow)` (e.g. with `TriageResult` and `RetrievedChunk`) actually correct?**
  _`ask (query flow)` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `get_settings()` (e.g. with `.complete()` and `get_client()`) actually correct?**
  _`get_settings()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `ask()` (e.g. with `ask_endpoint()` and `screen()`) actually correct?**
  _`ask()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Shared fixtures. Put sample documents (a benefits summary, a lab report, an EOB,`, `TODO: curated question -> expected-chunk pairs; measure top-k hit rate and that`, `Phase 1 evaluation harness (see PHASE_1_TECHNICAL_DESIGN.md §8):    - retrieval` to the rest of the system?**
  _83 weakly-connected nodes found - possible documentation gaps or missing edges._