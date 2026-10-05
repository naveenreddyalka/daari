"""http-api.md pin for compact_to_fit tokens on traces (#1413)."""

from __future__ import annotations

from pathlib import Path

HTTP_API = (
    Path(__file__).resolve().parents[2] / "docs/developer/reference/http-api.md"
)


def test_http_api_pins_traces_compact_to_fit_token_fields() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/daari/traces" in text
    assert "/v1/daari/traces/{trace_id}" in text
    assert "compact_to_fit" in text
    assert "tokens_before" in text
    assert "tokens_after" in text
