"""Doctor warns when local TTS is unreachable (#869)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_tts, run_doctor


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_unconfigured_tts_is_quiet(settings):
    result = _check_tts(settings, None)
    assert result.name == "tts"
    assert result.ok
    assert result.optional
    assert "not configured" in result.detail
    down = _client(lambda request: httpx.Response(500))
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
