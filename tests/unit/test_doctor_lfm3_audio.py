"""Doctor recognizes Ollama lfm3-audio as a local ASR/TTS backend (#1986)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_asr, _check_tts


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _tags_and_version(
    names: list[str], version: str = "0.40.12"
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/tags"):
            return httpx.Response(
                200, json={"models": [{"name": n} for n in names]}
            )
        if path.endswith("/api/version"):
            return httpx.Response(200, json={"version": version})
        if str(request.url).rstrip("/").endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    return _client(handler)


def test_unconfigured_tts_tips_lfm3_audio_when_tag_present(settings):
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = ""

    result = _check_tts(settings, _tags_and_version(["lfm3-audio", "llama3.2:3b"]))
    assert result.name == "tts"
    assert result.ok
    assert result.optional
    assert "lfm3-audio" in result.detail
    assert "tts.base_url" in result.detail
    assert "11434/v1" in result.detail


def test_unconfigured_tts_quiet_when_lfm3_audio_absent(settings):
    """No lfm3-audio tip when tags lack it (Phonon version tip may still fire)."""
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = ""

    result = _check_tts(
        settings, _tags_and_version(["llama3.2:3b"], version="0.40.5")
    )
    assert result.ok
    assert "lfm3-audio" not in result.detail


def test_unconfigured_asr_tips_lfm3_audio_when_tag_present(settings):
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.asr.base_url = ""

    result = _check_asr(settings, _tags_and_version(["lfm3-audio"]))
    assert result.name == "asr"
    assert result.ok
    assert result.optional
    assert "lfm3-audio" in result.detail
    assert "asr.base_url" in result.detail
    assert "11434/v1" in result.detail


def test_unconfigured_asr_quiet_when_lfm3_audio_absent(settings):
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.asr.base_url = ""

    result = _check_asr(settings, _tags_and_version(["phonon", "llama3.2:3b"]))
    assert result.ok
    assert "not configured" in result.detail
    assert "lfm3-audio" not in result.detail


def test_configured_tts_lfm3_audio_notes_backend_not_phonon_license(settings):
    """Configured lfm3-audio must not inherit Phonon CC BY-NC / voice-catalog tips."""
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = "http://127.0.0.1:11434/v1"
    settings.tts.model = "lfm3-audio"

    result = _check_tts(
        settings, _tags_and_version(["lfm3-audio"], version="0.40.9")
    )
    assert result.ok
    assert "reachable" in result.detail
    assert "lfm3-audio" in result.detail
    assert "CC BY-NC" not in result.detail
    assert "BY-NC" not in result.detail
    # Must not tip Phonon upgrade / Gradium catalog — only the honesty note.
    assert "upgrade to ≥0.40.11" not in result.detail
    assert "phonon:40m" not in result.detail.casefold()


def test_configured_asr_lfm3_audio_notes_backend(settings):
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.asr.base_url = "http://127.0.0.1:11434/v1"
    settings.asr.model = "lfm3-audio"

    result = _check_asr(settings, _tags_and_version(["lfm3-audio"]))
    assert result.ok
    assert "reachable" in result.detail
    assert "lfm3-audio" in result.detail
    assert "CC BY-NC" not in result.detail
