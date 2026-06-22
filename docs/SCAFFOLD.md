# Phase 1 Scaffold — orientation

```
tara-health/
├── pyproject.toml          # deps wired to the chosen stack
├── .env.example            # config: model mode, paths, models
├── src/tara/
│   ├── config.py           # central settings (paths, model mode, embed model)
│   ├── app.py              # FastAPI: /upload, /ask, / (UI)
│   ├── ingestion/          # detect -> extract(+spans) -> classify -> chunk -> pipeline
│   ├── embeddings/         # local sentence-transformers
│   ├── storage/            # sqlite + sqlite-vec + blobs (SQLCipher-ready)
│   ├── retrieval/          # embed query -> vector search (+doc-type filter)
│   ├── llm/                # base + local_ollama + hosted  (hybrid switch)
│   ├── safety/             # triage (pre-check) + framing (post-check)
│   ├── answering/          # prompts + answerer (the full query flow)
│   └── web/                # placeholder UI
├── scripts/init_db.py      # create schema + vector table
└── tests/                  # ingestion/retrieval/safety + eval_harness
```

## Data flow (read-only Phase 1)
Ingest:  upload -> extract(+page/char spans) -> classify -> chunk -> embed -> index
Ask:     safety pre-check -> retrieve -> grounded+cited answer -> safety framing

## Quickstart (once you fill in the TODOs)
```
pip install -e ".[dev]"
ollama pull qwen3:8b            # or your chosen local model
cp .env.example .env
python scripts/init_db.py
tara                            # serves http://127.0.0.1:8000
```

Every stub marks its intent with a docstring and `TODO`. Build order is in
PHASE_1_TECHNICAL_DESIGN.md §10 (get retrieval working first, then answering,
then citations, then safety, then OCR, then classification, then the eval harness).
