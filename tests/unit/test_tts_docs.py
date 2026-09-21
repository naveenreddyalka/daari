"""TTS backend guide is linked from configuration overview (#890)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERVIEW = ROOT / "docs/developer/guides/configuration/overview.md"
CLIENTS = ROOT / "docs/developer/concepts/clients-and-gateways.md"
TTS_GUIDE = ROOT / "docs/developer/guides/backends/tts.md"
MKDOCS = ROOT / "mkdocs.yml"


def test_tts_backend_guide_exists_and_covers_speech() -> None:
    text = TTS_GUIDE.read_text(encoding="utf-8")
    assert "/v1/audio/speech" in text
    assert "tts.base_url" in text
    assert "daari doctor" in text


def test_mkdocs_nav_lists_tts_guide() -> None:
    nav = MKDOCS.read_text(encoding="utf-8")
    assert "developer/guides/backends/tts.md" in nav
    asr = nav.find("developer/guides/backends/asr.md")
    tts = nav.find("developer/guides/backends/tts.md")
    assert asr != -1 and tts > asr


def test_overview_and_clients_link_tts_guide() -> None:
    overview = OVERVIEW.read_text(encoding="utf-8")
    clients = CLIENTS.read_text(encoding="utf-8")
    assert "tts.md" in overview
    assert "/v1/audio/speech" in overview or "/v1/audio/speech" in clients
    assert "tts.md" in clients or "backends/tts.md" in clients
    assert "/v1/audio/speech" in clients
