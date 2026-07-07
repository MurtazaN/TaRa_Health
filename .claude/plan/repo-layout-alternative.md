# Alternative repository layout (proposal vs design doc §11)

**Status:** partially superseded (2026-07-07) — the naming pass renamed all folders/files IN PLACE (document_ingestion/, chunk_retrieval/, text_embeddings/, question_answering/, safety_checks/, storage file renames, web_app.py). What remains open from this proposal is only the STRUCTURAL regroup: domain/ kernel, documents/+search/ feature merge, error consolidation.
**Scope:** the whole `src/tara/` tree, not just `storage/`.
**Prompted by:** naming/cohesion review after Slice 1 (see the rename pass already
applied: `tara/validation.py`, `vector.load_extension`/`add_embeddings`, `chunk_spans`).

## What's actually wrong with the current tree

The current layout (design §11) is *mostly* sound — small domain-grouped files, two
pipelines mirrored as packages. The real problems observed while implementing Slice 0/1:

1. **Mixed grouping scheme.** Top half is grouped by flow (`ingestion/`, `retrieval/`,
   `answering/`, `safety/`), bottom half by technical kind (`storage/`, `llm/`,
   `embeddings/`). The seams show: things that belong to a flow end up filed under a
   technology.
2. **Domain models live in the storage layer.** `storage/models.py` holds `Document`,
   `Chunk`, `Citation` — used by every layer, not storage artifacts. `Citation` is an
   answering/UI concept that currently forces answering code to import from `storage`.
3. **Errors are scattered.** `UploadError` (validation), `IngestionError` (pipeline),
   `IndexMismatchError` (db). `app.py`'s exception mapping imports from three modules.
4. **An orchestrator sits in the adapter layer.** `storage/purge.py` coordinates
   blobs + db + vectors — that's document-lifecycle *feature* logic, not a storage
   adapter. (Its `reconcile_orphan_blobs` likewise.)
5. **One-file packages.** `embeddings/` and `retrieval/` each hold a single module;
   both serve the same capability (semantic search: index-side + query-side).
6. **Verb-named modules** (`detect.py`, `extract.py`, `chunk.py`) collide with their
   own verb-named functions — the `chunk.chunk` aliasing bug we just fixed is the
   symptom; noun modules prevent the class of problem.

## Proposed tree

```
src/tara/
├── app.py                      # FastAPI surface + composition root (startup init)
├── config.py                   # settings (unchanged)
│
├── domain/                     # shared kernel — pure data, no I/O, imports nothing above it
│   ├── models.py               # Document, Chunk, Citation, DocType, DocStatus, Answer
│   └── errors.py               # UploadError, IngestionError, IndexMismatchError, ...
│
├── documents/                  # FEATURE: document lifecycle (in and out)
│   ├── validation.py           # upload boundary (§3.1a)          [from tara/validation.py]
│   ├── detection.py            # native vs scan vs image          [from ingestion/detect.py]
│   ├── extraction.py           # text + provenance spans (§3.1b)  [from ingestion/extract.py]
│   ├── chunking.py             # page-bounded chunks (§3.1d)      [from ingestion/chunk.py]
│   ├── classification.py       # doc-type tagging (Slice 6)       [from ingestion/classify.py]
│   ├── ingestion.py            # the pipeline (§3.1f/g)           [from ingestion/pipeline.py]
│   └── deletion.py             # purge + orphan sweep (§3.2/§7)   [from storage/purge.py]
│
├── search/                     # FEATURE: semantic index & query
│   ├── text_embedding.py       # text -> vectors (§3.1e)          [from embeddings/text_embedder.py]
│   └── chunk_retrieval.py      # question -> chunks + abstention (§3.4)  [from retrieval/chunk_retriever.py]
│
├── answering/                  # FEATURE: grounded answer (§3.5, §6)
│   ├── prompts.py
│   ├── citations.py            # chunk_id→Citation + numeric grounding (Slices 2–3, new)
│   └── answerer.py
│
├── safety/                     # FEATURE: pre/post checks (§3.3) — unchanged
│   ├── triage.py
│   └── framing.py
│
├── llm_clients/                # ADAPTER: text-generation backends (§3.5) — renamed 2026-07-06
│   ├── interface.py            # LLMClient protocol + get_llm_client routing
│   ├── ollama_client.py
│   ├── openai_compatible_client.py  # LM Studio (new, Slice 2)
│   └── hosted_client.py
│
├── storage/                    # ADAPTERS ONLY: dumb I/O, no orchestration
│   ├── database.py             # connection + schema + index_meta  [from db.py]
│   ├── vector_index.py         # sqlite-vec KNN                    [from vector.py]
│   └── blob_store.py           # original files on disk            [from blobs.py]
│
└── web/                        # templates/static (unchanged)
```

## The one rule that makes it hang together

Imports flow in a single direction:

```
app.py → features (documents, search, answering, safety) → adapters (storage, llm) → domain
                                    config and domain are importable from anywhere
```

- `domain/` imports nothing from `tara` (except possibly `config` — ideally not even that).
- `storage/` and `llm/` import only `domain` + `config`. Never a feature. (This is the
  rule `blobs.py` broke before the rename pass.)
- Features import adapters and domain; never each other **except** `answering → search`
  and `answering → safety`, which the design's query flow (§5.2) explicitly defines.
- `app.py` is the only module that imports everything; startup wiring
  (ensure_dirs / init_schema / init_vector_table / reconcile_orphan_blobs) lives there.

## What this deliberately does NOT do (YAGNI)

- No repository interfaces / DI container / abstract base classes per store — at
  single-user scale the concrete modules are the right altitude; `LLMClient` stays the
  only protocol because local-vs-hosted is a real, config-driven seam (§3.5).
- No `core/`/`utils/` dumping ground — `domain/` holds exactly models + errors.
- No migrations framework — the idempotent SCHEMA script is fine for Phase 1.

## Trade-offs (why you might keep the current tree)

- Design doc §11 and all four phase docs reference the current paths; adopting this
  means one §11 rewrite + link touch-ups.
- `storage/` = "the three stores of §3.2" is itself a defensible domain grouping; the
  current tree isn't *wrong*, it's just two organizing schemes at once.
- Git history churn on ~15 files (mitigated: `git mv` preserves blame with `-C`).

## Cost & timing

Pure file moves + import rewrites; zero behavior change; the 40-test suite is the
safety net. Estimate: one focused pass (~all-mechanical). **If adopting, do it before
Slice 2** — answering/llm code lands next and would double the move surface.

## Migration map (condensed)

| From | To |
|---|---|
| `storage/models.py` | `domain/models.py` |
| `UploadError`/`IngestionError`/`IndexMismatchError` | `domain/errors.py` |
| `validation.py` (root) | `documents/validation.py` |
| `ingestion/{detect,extract,chunk,classify,pipeline}.py` | `documents/{detection,extraction,chunking,classification,ingestion}.py` |
| `storage/purge.py` | `documents/deletion.py` |
| `embeddings/text_embedder.py` | `search/text_embedding.py` |
| `retrieval/chunk_retriever.py` | `search/chunk_retrieval.py` |
| `storage/{db,vector,blobs}.py` | `storage/{database,vector_index,blob_store}.py` |
| `llm_clients/` | already renamed in place (2026-07-06); only `openai_compatible_client.py` is new in Slice 2 |

Plus: update design doc §11, CLAUDE.md architecture pointers, and `scripts/init_db.py` imports.
