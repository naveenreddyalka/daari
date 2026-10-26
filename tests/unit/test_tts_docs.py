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


def test_tts_guide_mentions_ollama_phonon() -> None:
    text = TTS_GUIDE.read_text(encoding="utf-8")
    assert "Ollama" in text
    assert "0.40.9" in text or "Phonon" in text
    assert "stream" in text.lower()


def test_tts_guide_documents_voice_catalog_and_list() -> None:
    text = TTS_GUIDE.read_text(encoding="utf-8")
    assert "0.40.11" in text
    assert "/v1/audio/voices" in text
    assert "alloy" in text


def test_tts_guide_documents_phonon_response_format_coerce() -> None:
    """Phonon accepts wav/pcm; daari coerces OpenAI mp3 defaults (#1952)."""
    text = TTS_GUIDE.read_text(encoding="utf-8")
    assert "response_format" in text
    assert "wav" in text
    assert "pcm" in text
    assert "coerce" in text.lower() or "coerces" in text.lower()


def test_tts_guide_documents_phonon_language_tags_and_license() -> None:
    """Phonon 40M language tags + CC BY-NC vs Apache-2.0 31M (#1936)."""
    text = TTS_GUIDE.read_text(encoding="utf-8")
    for tag in (
        "phonon:40m-fr",
        "phonon:40m-de",
        "phonon:40m-es",
        "phonon:40m-pt",
        "phonon:40m-multilingual",
    ):
        assert tag in text
    assert "CC BY-NC" in text or "BY-NC" in text
    assert "Apache" in text
    assert "ollama pull phonon" in text
