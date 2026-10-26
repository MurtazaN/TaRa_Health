"""Web API surface: upload/ask endpoints, domain-error -> HTTP status mapping,
and the question-in-request-body contract (PHI never in the URL)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tara.app_errors import IndexMismatchError, IngestionError
from tara.data_models import Citation
from tara.web_app import app


@pytest.fixture
def api_client(offline_ingest_env):
    return TestClient(app)


@pytest.mark.integration
def test_upload_ingests_pdf_and_returns_document_facts(api_client, make_pdf):
    response = api_client.post(
        "/upload",
        files={"file": ("policy.pdf", make_pdf([["Specialist copay is $40."]]),
                        "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "policy.pdf"
    assert body["doc_type"] == "other"
    assert body["doc_id"]


@pytest.mark.integration
def test_upload_rejects_unsupported_extension_with_400(api_client):
    response = api_client.post("/upload", files={"file": ("notes.exe", b"x", "text/plain")})
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


@pytest.mark.integration
def test_ask_sends_question_in_body_and_returns_answer_shape(api_client, monkeypatch):
    from tara.question_answering.question_answerer import Answer

    seen_questions: list[str] = []

    def fake_answer_question(question: str, prefer_agent_platform: bool = False) -> Answer:
        seen_questions.append(question)
        return Answer(
            text="Your copay is $40 [c1].",
            citations=[Citation(chunk_id="c1", filename="policy.pdf", page=1)],
            safety_flag="none",
        )

    monkeypatch.setattr("tara.web_app.answer_question", fake_answer_question)
    response = api_client.post("/ask", json={"question": "what is my copay?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Your copay is $40 [c1]."
    assert body["safety_flag"] == "none"
    assert body["citations"][0]["chunk_id"] == "c1"
    assert seen_questions == ["what is my copay?"]  # question travelled in the body


@pytest.mark.integration
def test_stale_index_maps_to_409(api_client, monkeypatch):
    def raise_index_mismatch(question: str, prefer_agent_platform: bool = False):
        raise IndexMismatchError("re-index required")

    monkeypatch.setattr("tara.web_app.answer_question", raise_index_mismatch)
    response = api_client.post("/ask", json={"question": "anything"})
    assert response.status_code == 409


@pytest.mark.integration
def test_ingestion_error_maps_to_400(api_client, monkeypatch):
    def raise_ingestion_error(filename: str, file_bytes: bytes):
        raise IngestionError("no extractable text")

    monkeypatch.setattr("tara.web_app.ingest_document", raise_ingestion_error)
    response = api_client.post(
        "/upload", files={"file": ("empty.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 400
    assert "no extractable text" in response.json()["detail"]


@pytest.mark.unit
def test_agent_platform_config_error_maps_to_500(api_client, monkeypatch):
    from tara import web_app
    from tara.app_errors import AgentPlatformConfigError

    def raise_config_error(question: str, prefer_agent_platform: bool = False):
        raise AgentPlatformConfigError("provider=gemini project=test-project")

    monkeypatch.setattr(web_app, "answer_question", raise_config_error)
    response = api_client.post("/ask", json={"question": "what is my deductible?"})
    assert response.status_code == 500
    assert "test-project" in response.json()["detail"]


@pytest.mark.unit
def test_agent_platform_unavailable_maps_to_503(api_client, monkeypatch):
    from tara import web_app
    from tara.app_errors import AgentPlatformUnavailableError

    def raise_unavailable(question: str, prefer_agent_platform: bool = False):
        raise AgentPlatformUnavailableError("transient")

    monkeypatch.setattr(web_app, "answer_question", raise_unavailable)
    response = api_client.post("/ask", json={"question": "what is my deductible?"})
    assert response.status_code == 503


@pytest.mark.unit
def test_emergency_answer_is_shaped_into_a_200_response(api_client, monkeypatch):
    """RESPONSE SHAPING ONLY: an emergency Answer becomes 200 + safety_flag.

    Deliberately NOT a claim about M5 §4.3. `answer_question` is stubbed here, so
    nothing about the real triage path — or about Agent Platform being down —
    is exercised. The §4.3 guarantee is pinned by the xfail test below, which
    runs the real path; this one only proves the endpoint does not mangle an
    emergency Answer on its way out.
    """
    from tara.question_answering.question_answerer import Answer
    from tara import web_app

    def emergency(question: str, prefer_agent_platform: bool = False) -> Answer:
        return Answer(text="Call 911.", citations=[], safety_flag="emergency")

    monkeypatch.setattr(web_app, "answer_question", emergency)
    response = api_client.post("/ask", json={"question": "crushing chest pain"})
    assert response.status_code == 200
    assert response.json()["safety_flag"] == "emergency"


@pytest.mark.integration
def test_real_answer_path_triages_emergency_while_agent_platform_is_down(
    offline_ingest_env, monkeypatch
):
    """Spec assertion 9 / M5 §4.3, against the REAL answer_question path.

    Generation is set to egress and EVERY Agent Platform construction raises, so
    the only way this returns 200 is the emergency pre-check short-circuiting
    before retrieval and generation — which is precisely the property §4.3
    claims. Stubbing answer_question, as the shaping test above does, can never
    show that.
    """
    from tara import config
    from tara.llm_clients import agent_platform_client

    monkeypatch.setenv("TARA_GENERATION_MODE", "agent_platform")
    monkeypatch.setenv("TARA_GCP_PROJECT", "test-project")
    monkeypatch.setenv("TARA_PHI_EGRESS_ACKNOWLEDGED", "true")
    monkeypatch.setenv("TARA_EMBED_DIM", "256")   # match offline_ingest_env's fake vectors
    config.get_settings.cache_clear()

    def refuse_every_agent_platform_call():
        raise AssertionError("Agent Platform must not be reached for an emergency")

    monkeypatch.setattr(agent_platform_client, "_chat_model", refuse_every_agent_platform_call)

    response = TestClient(app).post("/ask", json={"question": "crushing chest pain"})
    assert response.status_code == 200
    assert response.json()["safety_flag"] == "emergency"


@pytest.mark.integration
def test_local_ingest_and_retrieval_resolve_no_hostname(offline_ingest_env, monkeypatch, make_pdf):
    """Spec assertion 12. Ingestion and retrieval must resolve no hostname — any
    outbound call needs DNS first.

    Scope is deliberate. It stops at retrieve_chunks() rather than
    answer_question(), because emergency_triage.screen_for_emergency() is still
    an Epic 1 stub that raises NotImplementedError; generation in local mode
    reaches LM Studio over the network BY DESIGN, so it was never in scope.

    What this proves: the ingest+retrieve path holds no hidden HTTP client. What
    it does NOT prove: that the real embedding model is local, because
    offline_ingest_env fakes the embedder. Task 6 Step 5 covers that with real
    weights in a container with --network none.

    Guards getaddrinfo rather than socket.socket, so pytest's own machinery and
    SQLite (file-based, socket-free) are unaffected.

    Proves the embed_query() step actually ran by spying on it directly, rather
    than by asserting retrieve_chunks() returns a non-empty list. Those are NOT
    equivalent: with offline_ingest_env's crude bag-of-words fake embedder, the
    single shared token between the question and the fixture PDF text scores
    0.177 cosine similarity, under the real abstain_threshold of 0.25 — so
    retrieve_chunks() legitimately returns [] via its abstention guard AFTER
    calling embed_query(). Asserting non-emptiness would therefore either fail
    on correct behaviour (abstention) or require fixture text tuned to dodge the
    threshold, which is fragile against a threshold or fake-embedder change.
    Spying on embed_query() isolates exactly the thing this test must prove —
    that the query-embedding step was reached under the getaddrinfo guard — from
    the abstention guard's unrelated relevance judgment.
    """
    import socket

    from tara.document_ingestion.ingestion_pipeline import ingest_document
    from tara.semantic_search import text_embedder
    from tara.semantic_search.chunk_retriever import retrieve_chunks

    def _refuse(*args, **kwargs):
        raise AssertionError(f"local mode attempted to resolve {args[:1]}")

    monkeypatch.setattr(socket, "getaddrinfo", _refuse)

    embed_query_calls: list[str] = []
    fake_embed_query = text_embedder.embed_query  # offline_ingest_env's deterministic fake

    def _spy_embed_query(text: str) -> list[float]:
        embed_query_calls.append(text)
        return fake_embed_query(text)

    monkeypatch.setattr(text_embedder, "embed_query", _spy_embed_query)

    pdf_bytes = make_pdf([["Annual Deductible: $2,500 individual / $5,000 family"]])
    ingest_document("benefits.pdf", pdf_bytes)
    retrieve_chunks("what is my deductible?")
    # This is the assertion that matters: it fails if a future regression makes
    # retrieve_chunks() return early (e.g. _is_index_ready() misbehaving) without
    # ever reaching embed_query() — the exact failure mode a non-None or
    # non-empty check on the return value would silently let through.
    assert embed_query_calls == ["what is my deductible?"]


# ---- Startup warning: the local backend host is an unvalidated URL ----


@pytest.fixture
def local_backend_hosts(monkeypatch):
    """Set the two local-backend hosts hermetically and reset cached settings."""
    from tara import config

    def _set(local_llm_backend: str, lmstudio_host: str, ollama_host: str) -> None:
        monkeypatch.setenv("TARA_GENERATION_MODE", "local")
        monkeypatch.setenv("TARA_LOCAL_LLM_BACKEND", local_llm_backend)
        monkeypatch.setenv("TARA_LMSTUDIO_HOST", lmstudio_host)
        monkeypatch.setenv("TARA_OLLAMA_HOST", ollama_host)
        config.get_settings.cache_clear()

    yield _set
    config.get_settings.cache_clear()


@pytest.mark.unit
@pytest.mark.parametrize(
    "local_llm_backend, lmstudio_host, ollama_host",
    [
        ("openai_compatible", "https://api.openai.com", "http://localhost:11434"),
        ("ollama", "http://localhost:1234", "http://ollama.example.com:11434"),
    ],
)
def test_startup_warns_when_the_active_local_backend_host_is_not_loopback(
    local_backend_hosts, local_llm_backend, lmstudio_host, ollama_host
):
    """generation_mode 'local' promises nothing leaves the device, but the backend
    host is a free-form URL. A non-loopback value sends assembled excerpts off the
    machine with no egress gate, so it is surfaced rather than silently honoured.
    """
    from tara.web_app import warn_if_local_model_host_is_not_loopback

    local_backend_hosts(local_llm_backend, lmstudio_host, ollama_host)
    with pytest.warns(UserWarning, match="not loopback"):
        warn_if_local_model_host_is_not_loopback()


@pytest.mark.unit
@pytest.mark.parametrize("local_llm_backend", ["openai_compatible", "ollama"])
def test_startup_is_silent_when_the_active_local_backend_host_is_loopback(
    local_backend_hosts, local_llm_backend, recwarn
):
    from tara.web_app import warn_if_local_model_host_is_not_loopback

    local_backend_hosts(local_llm_backend, "http://127.0.0.1:1234", "http://localhost:11434")
    warn_if_local_model_host_is_not_loopback()
    assert [w for w in recwarn.list if "not loopback" in str(w.message)] == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "local_llm_backend, lmstudio_host, ollama_host",
    [
        ("openai_compatible", "http://localhost:1234", "https://api.openai.com"),
        ("ollama", "https://api.openai.com", "http://localhost:11434"),
    ],
)
def test_startup_ignores_the_host_of_the_backend_not_in_use(
    local_backend_hosts, local_llm_backend, lmstudio_host, ollama_host, recwarn
):
    """Only the backend `local_llm_backend` selects can egress anything; warning
    about the other one would train the operator to ignore the warning."""
    from tara.web_app import warn_if_local_model_host_is_not_loopback

    local_backend_hosts(local_llm_backend, lmstudio_host, ollama_host)
    warn_if_local_model_host_is_not_loopback()
    assert [w for w in recwarn.list if "not loopback" in str(w.message)] == []
