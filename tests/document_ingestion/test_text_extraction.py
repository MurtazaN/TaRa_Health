"""Text extraction preserves page + char-span provenance (the citation invariant)."""
from __future__ import annotations

import pytest

from tara.document_ingestion.text_extraction import extract_text_spans, page_canonical_text


@pytest.mark.unit
def test_extract_preserves_page_and_span_invariant(make_pdf, tmp_path):
    import pymupdf

    data = make_pdf([
        ["Specialist copay is $40 per visit.", "Deductible is $1500 annually."],
        ["Glucose result is 95 mg/dL."],
    ])
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)

    spans = extract_text_spans(path)
    assert [span.page for span in spans] == [1, 2]  # one span per page, in order

    # The core citation invariant: a span's char range indexes its page text.
    with pymupdf.open(path) as pdf_document:
        for span in spans:
            page_text = page_canonical_text(pdf_document[span.page - 1])
            assert page_text[span.char_start:span.char_end] == span.text
    assert "$40" in spans[0].text
    assert "95" in spans[1].text
