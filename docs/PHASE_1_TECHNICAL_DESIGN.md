# TaRa Health — Phase 1 Technical Design

**Phase 1 scope:** Grounded, read-only Q&A over the user's documents.
**Explicitly out of scope for Phase 1:** any agentic *action* (no calendar, email,
pharmacy, delivery). Phase 1 builds the foundation — ingestion, retrieval,
grounded answering, citations, and the safety layer — that every later phase
depends on.

**Status:** Draft v0.1
**Last updated:** [Date]

---

## 1. Goals

1. User uploads health/insurance documents; TaRa parses and indexes them locally.
2. User asks natural-language questions; **Tara** answers using *only* what the
   documents support, and **cites the source** (document + page).
3. When a document doesn't contain the answer, Tara says so rather than guessing.
4. The **safety layer** runs on every health query (emergency detection + framing).
5. Everything is **local-first** and **single-profile**.

Success bar: a coverage question ("what's my specialist copay?") returns the
correct number with a citation to the right page, and a missing-info question
returns an honest "I don't see that in your documents."

---

## 2. High-level architecture

```
                 ┌─────────────────────────────────────────────┐
   Upload  ─────▶│              INGESTION PIPELINE              │
                 │  detect type → extract text (PDF/OCR) →      │
                 │  classify doc → chunk → embed → index        │
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │           LOCAL STORAGE (on device)          │
                 │  • file blob store (original docs)           │
                 │  • metadata DB (docs, chunks, pages)         │
                 │  • vector index (chunk embeddings)           │
                 └───────────────┬─────────────────────────────┘
                                 ▲
   Question ──▶ ┌────────────────┴──────────────┐
                │   SAFETY / TRIAGE (pre-check)  │ ── emergency? ──▶ escalate, stop
                └────────────────┬──────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  RETRIEVAL: embed query → vector search +    │
                 │  metadata filter → (rerank) → assemble ctx   │
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  ANSWERING LLM (grounding + citation prompt) │
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  SAFETY (post-check framing) → cited answer  │
                 └─────────────────────────────────────────────┘
```

---

## 3. Components

### 3.1 Ingestion pipeline

**a. File-type detection.** Accept PDF and image formats. Branch on whether the
PDF has a real text layer vs. is a scan.

**b. Text extraction.**
- Native-text PDFs: extract text + per-character/word bounding boxes and page numbers (e.g., PyMuPDF / pdfplumber).
- Scanned PDFs and images: OCR. *Local-first preference:* on-device OCR (Tesseract) or a local vision model, so PHI doesn't leave the device. Keep a cloud-OCR option behind an explicit opt-in for hard cases.
- Preserve **page number** and **character span** for every extracted piece — this is what makes citations possible later.

**c. Document classification.** Tag each document: `insurance_policy`,
`benefits_summary`, `eob`, `bill`, `lab_report`, `prescription`,
`after_visit_summary`, `other`. A small LLM call or a lightweight classifier is
fine. Classification powers metadata-filtered retrieval (e.g., a cost question
should prefer insurance docs).

**d. Chunking.** Split text into retrievable chunks (e.g., ~500–1000 tokens with
overlap), but chunk *structurally* where possible — insurance docs have tables
and sections; lab reports have result tables. Each chunk stores
`{chunk_id, doc_id, page, char_span, text}`.

**e. Embedding + indexing.** Embed each chunk and store the vector in a local
index. *Local-first preference:* on-device embedding model so document text never
leaves the device during indexing.

### 3.2 Local storage

Three stores, all on device:
- **Blob store:** the original uploaded files (for display + re-processing).
- **Metadata DB:** documents, chunks, page map, classification, timestamps.
- **Vector index:** chunk embeddings for similarity search.

A single embedded DB can cover the last two — e.g., **SQLite + a vector
extension (sqlite-vec)**, **LanceDB**, or **Chroma** in local mode. SQLite-based
options keep the whole thing in one portable file, which fits local-first and
makes backup/migration trivial.

### 3.3 Safety / triage layer

Runs **before** the answering LLM on any health-related query.

- **Emergency detection (pre-check):** a fast classifier (rules list of red-flag
  patterns — chest pain, stroke signs, anaphylaxis, suicidal ideation, etc. —
  backed by a lightweight LLM check). If triggered, Tara **short-circuits**: it
  does not give self-care advice; it directs the user to emergency services and
  stops.
- **Framing (post-check):** ensure the final answer is framed as general
  information, includes a professional-care nudge for anything serious or
  persistent, and avoids guaranteed outcomes/timelines.

This layer is intentionally separate from the answering prompt so it can't be
"reasoned away" by the main model and can be tested independently.

### 3.4 Retrieval

1. Embed the query (same on-device model as indexing).
2. Vector search over chunks, optionally **filtered by document type** inferred
   from the question (cost/coverage → insurance docs; "my results" → lab reports).
3. Optional rerank for precision.
4. Assemble the top-k chunks into context, each tagged with its `chunk_id` and
   source (doc name + page).

### 3.5 Answering LLM

Given the assembled context, the model must:
- Answer **only** from the provided chunks.
- **Cite** the chunk(s) it used (the app maps `chunk_id → document + page` for display).
- Say **"I don't see that in your documents"** when the context doesn't support an answer — never fabricate coverage numbers or results.

> **Privacy seam:** this is the main point where data may leave the device (if
> using a hosted model). The hosted-vs-local model choice is tracked in
> OPEN_QUESTIONS.md (#1). Retrieval and indexing stay local regardless; only the
> minimal assembled context + question need go to the model.

---

## 4. Data model (sketch)

```
documents
  doc_id          (pk)
  filename
  doc_type        (insurance_policy | lab_report | eob | bill | ...)
  uploaded_at
  page_count

chunks
  chunk_id        (pk)
  doc_id          (fk -> documents)
  page
  char_start
  char_end
  text
  embedding       (vector)

queries            (optional, for audit/eval)
  query_id        (pk)
  question
  retrieved_chunk_ids
  answer
  citations
  safety_flag     (none | emergency)
  created_at
```

---

## 5. Key flows

### 5.1 Ingestion (sequence)
```
upload → detect type → extract text (+page/char spans)
       → classify doc → chunk → embed → write to blob/metadata/vector stores
       → confirm "Indexed N pages from <filename>"
```

### 5.2 Query (sequence)
```
question → SAFETY pre-check
            ├─ emergency? → escalate message, STOP
            └─ otherwise ↓
         → embed query → retrieve (filtered) → assemble context
         → answering LLM (grounded + cite) → SAFETY framing post-check
         → return cited answer (+ "open source page" links to local docs)
```

---

## 6. Answering prompt (sketch)

> You are Tara, a personal health & insurance assistant. Answer the user's
> question using ONLY the document excerpts provided below. Each excerpt has an
> ID. When you state a fact, cite the excerpt ID(s) it came from. If the excerpts
> do not contain the answer, say you don't see it in their documents — do not
> guess or invent coverage amounts, results, or policy terms. Frame any health
> information as general information, not a diagnosis, and suggest professional
> care for anything serious or persistent.
>
> [excerpts: {chunk_id, source, page, text} ...]
> [question]

Keep the safety pre-check as a *separate* call/stage — do not rely on this prompt
alone for emergency handling.

---

## 7. Privacy & security (Phase 1)

- All three stores on device; encrypt at rest.
- On-device OCR + embeddings by default; cloud OCR only behind explicit opt-in.
- Send the **minimum** to any hosted model: assembled context + question, not the
  whole corpus.
- Audit log of queries (local), so the user can see what was asked/answered.
- Simple delete: removing a document purges its blob, chunks, and vectors.

---

## 8. Testing & evaluation

- **Retrieval accuracy:** curated Q→expected-chunk pairs across each doc type; measure top-k hit rate.
- **Citation correctness:** does the cited page actually contain the stated fact?
- **Hallucination / honesty:** ask questions the docs *can't* answer; the system must decline, not invent.
- **Safety recall:** a battery of emergency-phrased inputs; the pre-check must catch them (favor over-triggering over under-triggering here).
- **OCR fidelity:** spot-check extracted numbers on scanned lab reports / EOBs, since a misread digit in a copay or result is a real harm.

---

## 9. What Phase 1 deliberately excludes

- No actions of any kind (calendar, email, reminders, pharmacy, delivery).
- No external integrations / MCP servers yet.
- No proactive behavior — Tara only responds when asked.

These arrive in Phase 2+ (see PRD §11), building on the retrieval + safety
foundation established here.

---

## 10. Suggested build order within Phase 1

1. Ingestion for native-text PDFs → chunk → local index. (Get retrieval working first.)
2. Answering LLM with grounding + "decline if unsupported."
3. Citations (chunk → page mapping surfaced in the UI).
4. Safety pre-check (emergency detection) + post-check framing.
5. OCR path for scanned docs + images.
6. Document classification + filtered retrieval.
7. Eval harness (§8) running against a fixture set of sample documents.
