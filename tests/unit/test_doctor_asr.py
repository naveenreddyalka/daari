"""Doctor warns when local ASR is unreachable or frontier fallback has no key (#740)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_asr, run_doctor


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_unconfigured_asr_is_quiet(settings):
    result = _check_asr(settings, None)
    assert result.name == "asr"
    assert result.ok
    assert result.optional
    assert "not configured" in result.detail
    down = _client(lambda request: httpx.Response(500))
    row = next(item for item in run_doctor(settings, httpx_client=down) if item.name == "asr")
    assert row.ok


def test_reachable_local_asr(settings):
    settings.asr.base_url = "http://asr.local/v1/"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://asr.local/v1/models"
        return httpx.Response(200, json={"data": []})

    result = _check_asr(settings, _client(handler))
    assert result.ok
    assert "reachable" in result.detail


def test_unreachable_local_asr_warns(settings):
    settings.asr.base_url = "http://asr.local/v1"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result = _check_asr(settings, _client(handler))
    assert not result.ok
    assert result.optional
    assert "unreachable" in result.detail
    assert "asr.local" in result.detail


def test_http_error_is_unreachable(settings):
    settings.asr.base_url = "http://asr.local/v1"
    result = _check_asr(settings, _client(lambda request: httpx.Response(503)))
    assert not result.ok
    assert "503" in result.detail


def test_fallback_without_frontier_warns(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = False
    result = _check_asr(settings, None)
    assert not result.ok
    assert "frontier" in result.detail


def test_fallback_without_key_warns(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    result = _check_asr(settings, None)
    assert not result.ok
    assert "key" in result.detail


def test_fallback_with_key_is_quiet(settings, monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-frontier-test")
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://frontier.example/v1"
    result = _check_asr(settings, None)
    assert result.ok
    assert "fallback" in result.detail
