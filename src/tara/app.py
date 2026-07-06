"""FastAPI local web app. Phase 1 surface: upload documents, ask questions.
Read-only — there are no action endpoints yet (that's Phase 2+).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from tara.answering.answerer import ask
from tara.ingestion.pipeline import ingest

app = FastAPI(title="TaRa Health", version="0.1.0")


class AskRequest(BaseModel):
    """Question travels in the request BODY, not the URL, so PHI never lands in
    access logs or browser history (design §7)."""

    question: str
    prefer_hosted: bool = False

_web = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(_web / "templates"))
app.mount("/static", StaticFiles(directory=str(_web / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # Starlette's current signature takes the request first.
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    doc = ingest(file.filename, await file.read())
    return {"doc_id": doc.doc_id, "filename": doc.filename, "doc_type": doc.doc_type}


@app.post("/ask")
def ask_endpoint(payload: AskRequest):
    answer = ask(payload.question, prefer_hosted=payload.prefer_hosted)
    return {
        "answer": answer.text,
        "safety_flag": answer.safety_flag,
        "citations": [c.__dict__ for c in answer.citations],
    }


def main() -> None:
    """`tara` entry point — runs the local server."""
    import uvicorn

    from tara.storage.db import init_schema
    init_schema()
    uvicorn.run("tara.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
