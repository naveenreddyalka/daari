"""TTS backend guide is linked from configuration overview (#890)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERVIEW = ROOT / "docs/developer/guides/configuration/overview.md"
CLIENTS = ROOT / "docs/developer/concepts/clients-and-gateways.md"
TTS_GUIDE = ROOT / "docs/developer/guides/backends/tts.md"


def test_tts_backend_guide_exists_and_covers_speech() -> None:
    text = TTS_GUIDE.read_text(encoding="utf-8")
    assert "/v1/audio/speech" in text
    assert "tts.base_url" in text
    assert "daari doctor" in text


def test_tts_guide_documents_helm_model_and_voice() -> None:
    text = TTS_GUIDE.read_text(encoding="utf-8")
    assert "tts.model" in text
    assert "tts.voice" in text
    assert "DAARI_TTS__MODEL" in text
    assert "DAARI_TTS__VOICE" in text


def test_overview_and_clients_link_tts_guide() -> None:
    overview = OVERVIEW.read_text(encoding="utf-8")
    clients = CLIENTS.read_text(encoding="utf-8")
    assert "tts.md" in overview
    assert "/v1/audio/speech" in overview or "/v1/audio/speech" in clients
    assert "tts.md" in clients or "backends/tts.md" in clients
    assert "/v1/audio/speech" in clients
