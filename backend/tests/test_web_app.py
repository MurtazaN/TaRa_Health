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

    def fake_answer_question(question: str, prefer_hosted: bool = False) -> Answer:
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
    def raise_index_mismatch(question: str, prefer_hosted: bool = False):
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
