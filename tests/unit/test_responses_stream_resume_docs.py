"""http-api.md pins for Responses stream resume query params (#1155, #1162)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTTP_API = ROOT / "docs/developer/reference/http-api.md"


def test_http_api_documents_responses_stream_resume_query_params() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/responses/{response_id}" in text or "/v1/responses/{id}" in text
    assert "stream" in text
    assert "starting_after" in text
    assert "409" in text


def test_http_api_documents_last_event_id_and_sequence_number() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "Last-Event-ID" in text
    assert "sequence_number" in text
