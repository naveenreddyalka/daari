"""Request deadline appears in headers + config reference (#799)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_headers_document_deadline_ms() -> None:
    headers = (ROOT / "docs/developer/reference/headers.md").read_text(encoding="utf-8")
    assert "X-Daari-Deadline-Ms" in headers
    assert "request_deadline_exceeded" in headers
    assert "time-to-first-token" in headers


def test_config_documents_request_deadline_seconds() -> None:
    config = (ROOT / "docs/developer/reference/config.md").read_text(encoding="utf-8")
    assert "upstream.request_deadline_seconds" in config
    assert "X-Daari-Deadline-Ms" in config
