"""capacity-helm documents tts.baseUrl / DAARI_TTS__BASE_URL (#880)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/guides/operations/capacity-helm.md"


def test_capacity_helm_documents_tts_base_url() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "tts.baseUrl" in text
    assert "DAARI_TTS__BASE_URL" in text
