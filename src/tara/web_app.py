"""FastAPI local web app. Phase 1 surface: upload documents, ask questions.
Read-only — there are no action endpoints yet (that's Phase 2+).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from tara.app_errors import IndexMismatchError, IngestionError, UploadError
from tara.document_ingestion.ingestion_pipeline import ingest_document
from tara.question_answering.question_answerer import answer_question

app = FastAPI(title="TaRa Health", version="0.1.0")


@app.exception_handler(UploadError)
def _handle_upload_error(request: Request, exc: UploadError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(IngestionError)
def _handle_ingestion_error(request: Request, exc: IngestionError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(IndexMismatchError)
def _handle_index_mismatch(request: Request, exc: IndexMismatchError) -> JSONResponse:
    # 409: the on-disk index is incompatible with the configured model (re-index).
    return JSONResponse(status_code=409, content={"detail": str(exc)})


class AskRequest(BaseModel):
    """Question travels in the request BODY, not the URL, so PHI never lands in
    access logs or browser history (design §7)."""

    question: str
    prefer_hosted: bool = False

_web_dir = Path(__file__).parent / "web_ui"
templates = Jinja2Templates(directory=str(_web_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(_web_dir / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_home_page(request: Request):
    # Starlette's current signature takes the request first.
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    ingested_document = ingest_document(file.filename, await file.read())
    return {
        "doc_id": ingested_document.doc_id,
        "filename": ingested_document.filename,
        "doc_type": ingested_document.doc_type,
    }


@app.post("/ask")
def ask_question(payload: AskRequest):
    answer = answer_question(payload.question, prefer_hosted=payload.prefer_hosted)
    return {
        "answer": answer.text,
        "safety_flag": answer.safety_flag,
        "citations": [c.__dict__ for c in answer.citations],
    }


def main() -> None:
    """`tara` entry point — runs the local server."""
    import uvicorn

    from tara.config import ensure_data_dirs
    from tara.local_data_stores.metadata_db import connect_db, init_db_schema
    from tara.local_data_stores.document_purge import reconcile_orphan_blobs
    from tara.local_data_stores.vector_index import init_vector_table

    ensure_data_dirs()
    init_db_schema()
    conn = connect_db()
    try:
        init_vector_table(conn)
    finally:
        conn.close()
    reconcile_orphan_blobs()  # sweep PHI blobs orphaned by an interrupted delete (§7)
    uvicorn.run("tara.web_app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
