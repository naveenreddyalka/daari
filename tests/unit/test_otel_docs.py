"""OTel guide documents otlp_logs beside traces/metrics (#881)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_otel_genai_documents_otlp_logs() -> None:
    text = (ROOT / "docs/developer/guides/observability/otel-genai.md").read_text(
        encoding="utf-8"
    )
    assert "otlp_logs" in text
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in text
    assert "traces" in text.lower() and "metrics" in text.lower()


def test_otel_genai_documents_conversation_id_from_session() -> None:
    text = (ROOT / "docs/developer/guides/observability/otel-genai.md").read_text(
        encoding="utf-8"
    )
    assert "gen_ai.conversation.id" in text
    assert "X-Daari-Session" in text
