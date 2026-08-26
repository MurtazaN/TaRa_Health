"""FastAPI local web app. Phase 1 surface: upload documents, ask questions.
Read-only — there are no action endpoints yet (that's Phase 2+).
"""
from __future__ import annotations

import warnings

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from tara.app_errors import (
    AgentPlatformConfigError,
    AgentPlatformUnavailableError,
    IndexMismatchError,
    IngestionError,
    UploadError,
)
from tara.config import get_settings
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


@app.exception_handler(AgentPlatformConfigError)
def _handle_agent_platform_config_error(request: Request, exc: AgentPlatformConfigError) -> JSONResponse:
    # 500: the operator must fix credentials, permissions, the model id, or the
    # region. Retrying will not help. The message carries no user content.
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(AgentPlatformUnavailableError)
def _handle_agent_platform_unavailable(request: Request, exc: AgentPlatformUnavailableError) -> JSONResponse:
    # 503: transient — quota or availability. The same request may succeed later.
    return JSONResponse(status_code=503, content={"detail": str(exc)})


class AskRequest(BaseModel):
    """Question travels in the request BODY, not the URL, so PHI never lands in
    access logs or browser history (design §7)."""

    question: str
    prefer_agent_platform: bool = False

# Templates and static assets share one directory in the monorepo layout;
# index.html references "/static/app.js", so the mount keeps that URL working.
_frontend_dir = get_settings().frontend_dir
templates = Jinja2Templates(directory=str(_frontend_dir))
app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")


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
    answer = answer_question(payload.question, prefer_agent_platform=payload.prefer_agent_platform)
    return {
        "answer": answer.text,
        "safety_flag": answer.safety_flag,
        "citations": [c.__dict__ for c in answer.citations],
    }


# Hostnames that keep traffic on the machine. A local backend pointed anywhere
# else is a network destination, whatever the setting is called.
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def warn_if_local_model_host_is_not_loopback() -> None:
    """Warn at startup when the ACTIVE local backend points off-machine.

    `generation_mode: "local"` is the promise that nothing leaves the device, but
    the backend host is a free-form URL: `TARA_LMSTUDIO_HOST=https://api.openai.com`
    would send assembled excerpts to a third party with no egress gate in front of
    it. A hard loopback requirement is not imposed here — LM Studio on another
    machine on a LAN is a legitimate setup — so this surfaces the choice instead
    of silently honouring it. Only the backend `local_llm_backend` actually
    selects is checked; the other host is inert.
    """
    from urllib.parse import urlparse

    settings = get_settings()
    model_host = settings.active_local_model_host
    hostname = urlparse(model_host).hostname
    if hostname is not None and hostname.lower() in _LOOPBACK_HOSTNAMES:
        return
    warnings.warn(
        f"Local generation backend '{settings.local_llm_backend}' points at "
        f"'{model_host}', which is not loopback. In generation_mode 'local' the "
        f"assembled excerpts from your documents are sent there, off this "
        f"machine, with no egress acknowledgement in front of it.",
        stacklevel=2,
    )


def main() -> None:
    """`tara` entry point — runs the local server."""
    import uvicorn

    from tara.config import ensure_data_dirs
    from tara.execution_tracing.tracer_setup import configure_tracing
    from tara.local_data_stores.db_connection import connect_db
    from tara.local_data_stores.db_schema import init_db_schema
    from tara.local_data_stores.document_purge import reconcile_orphan_blobs
    from tara.local_data_stores.vector_index import init_vector_table

    configure_tracing()  # before anything else, so startup work is traced too
    ensure_data_dirs()
    init_db_schema()
    conn = connect_db()
    try:
        init_vector_table(conn)
    finally:
        conn.close()
    reconcile_orphan_blobs()  # sweep PHI blobs orphaned by an interrupted delete (§7)

    # Startup validation (M5 §7.3). All three are deterministic and offline, so
    # all three fail hard: a typo'd model or an oversized chunk should never be
    # discovered by a user mid-question.
    from tara.llm_clients.agent_platform_client import verify_generation_model
    from tara.semantic_search.text_embedder import (
        verify_chunk_size_fits_model,
        verify_embedding_dimension,
    )

    if get_settings().generation_mode in ("agent_platform", "hybrid"):
        verify_generation_model()
    verify_chunk_size_fits_model()
    verify_embedding_dimension()
    warn_if_local_model_host_is_not_loopback()

    bind_host = get_settings().server_host
    if bind_host != "127.0.0.1":
        # The one setting that widens PHI exposure gets its own guard, since a
        # code comment in config.py can only warn passively. This is a bare
        # host process, not the container - Docker is not here to mediate.
        warnings.warn(
            f"TARA_SERVER_HOST is '{bind_host}', not the loopback default. "
            "This app has no authentication and serves PHI; binding beyond "
            "127.0.0.1 exposes it to the network.",
            stacklevel=2,
        )

    uvicorn.run("tara.web_app:app", host=bind_host, port=8000, reload=False)


if __name__ == "__main__":
    main()
