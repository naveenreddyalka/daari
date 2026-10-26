"""Doctor warns when local TTS is unreachable (#869)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_tts, run_doctor


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_unconfigured_tts_is_quiet(settings):
    # Empty tts.base_url stays quiet when Ollama is not speech-capable / unreachable.
    down = _client(lambda request: httpx.Response(500))
    result = _check_tts(settings, down)
    assert result.name == "tts"
    assert result.ok
    assert result.optional
    assert "not configured" in result.detail
    row = next(item for item in run_doctor(settings, httpx_client=down) if item.name == "tts")
    assert row.ok


def test_reachable_local_tts(settings):
    settings.tts.base_url = "http://tts.local/v1/"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://tts.local/v1/models"
        return httpx.Response(200, json={"data": []})

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "reachable" in result.detail


def test_unreachable_local_tts_warns(settings):
    settings.tts.base_url = "http://tts.local/v1"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result = _check_tts(settings, _client(handler))
    assert not result.ok
    assert result.optional
    assert "unreachable" in result.detail
    assert "tts.local" in result.detail


def test_http_error_is_unreachable(settings):
    settings.tts.base_url = "http://tts.local/v1"
    result = _check_tts(settings, _client(lambda request: httpx.Response(503)))
    assert not result.ok
    assert "503" in result.detail


def test_unconfigured_tts_tips_ollama_phonon_when_speech_capable(settings):
    """Ollama ≥0.40.9 + empty tts.base_url → tip to point at Ollama /v1 (#1888)."""
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.9"})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.name == "tts"
    assert result.ok
    assert result.optional
    assert "tts.base_url" in result.detail
    assert "11434/v1" in result.detail or "http://127.0.0.1:11434/v1" in result.detail
    assert "Phonon" in result.detail or "0.40.9" in result.detail


def test_unconfigured_tts_stays_quiet_when_ollama_old(settings):
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.5"})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "not configured" in result.detail
    assert "tts.base_url" not in result.detail or "set tts.base_url" not in result.detail.lower()


def test_unconfigured_tts_stays_quiet_when_ollama_unreachable(settings):
    settings.tts.base_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "not configured" in result.detail


def test_configured_tts_skips_phonon_tip(settings):
    settings.tts.base_url = "http://tts.local/v1"
    settings.ollama.base_url = "http://127.0.0.1:11434"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": []})
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.9"})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "reachable" in result.detail
    assert "Phonon" not in result.detail


def test_unconfigured_tts_tips_voice_catalog_on_0_40_11(settings):
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.11"})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "0.40.11" in result.detail or "voice catalog" in result.detail
    assert "/v1/audio/voices" in result.detail


def test_configured_phonon_tips_upgrade_below_0_40_11(settings):
    """Configured Phonon + Ollama <0.40.11 → tip voice catalog / language tags (#1936)."""
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = "http://127.0.0.1:11434/v1"
    settings.tts.model = "phonon"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.9"})
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "reachable" in result.detail
    assert "0.40.11" in result.detail
    assert "language" in result.detail.lower() or "voice catalog" in result.detail.lower()


def test_configured_phonon_40m_warns_cc_by_nc(settings):
    """phonon:40m-* / multilingual checkpoints are CC BY-NC 4.0 (#1936)."""
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = "http://127.0.0.1:11434/v1"
    settings.tts.model = "phonon:40m-fr"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.11"})
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "CC BY-NC" in result.detail or "BY-NC" in result.detail
    assert "Apache" in result.detail
    assert "40m" in result.detail.lower() or "noncommercial" in result.detail.lower()


def test_configured_phonon_31m_skips_cc_by_nc_warning(settings):
    """Default phonon 31M stays Apache-2.0 — no CC BY-NC tip (#1936)."""
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.tts.base_url = "http://127.0.0.1:11434/v1"
    settings.tts.model = "phonon"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.40.11"})
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    result = _check_tts(settings, _client(handler))
    assert result.ok
    assert "reachable" in result.detail
    assert "CC BY-NC" not in result.detail
    assert "BY-NC" not in result.detail
