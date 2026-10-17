"""Doctor warns when Ollama is older than the q2_0 GGUF floor (#1734)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from daari.setup.doctor import _check_ollama


def _response(status: int, payload: object) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json.return_value = payload
    return response


def _client(version_body: object | None, *, version_status: int = 200) -> MagicMock:
    tags = _response(200, {"models": [{"name": "llama3.2:3b"}]})
    client = MagicMock(spec=httpx.Client)

    def get(url: str, **_kwargs: object) -> MagicMock:
        if url.endswith("/api/version"):
            if version_body is None and version_status == 200:
                raise httpx.ConnectError("no version")
            return _response(version_status, version_body)
        return tags

    client.get.side_effect = get
    return client


def test_old_ollama_warns_q2_0_needs_0_40_6(settings):
    settings.models.l3 = "llama3.2:3b"
    results = _check_ollama(settings, _client({"version": "0.40.5"}))
    warning = next(result for result in results if result.name == "ollama_q2_0")
    assert warning.optional is True
    assert warning.ok is False
    assert "0.40.5" in warning.detail
    assert "q2_0" in warning.detail
    assert "0.40.6" in warning.detail
    model = next(result for result in results if result.name == "model")
    assert model.ok is True
    assert model.detail == "llama3.2:3b found"


def test_floor_and_newer_skip_q2_0_warning(settings):
    for version in ("0.40.6", "0.41.0", "1.0.0"):
        results = _check_ollama(settings, _client({"version": version}))
        assert all(result.name != "ollama_q2_0" for result in results)


def test_missing_or_unparseable_version_skips_check(settings):
    cases = (
        _client(None),
        _client({"version": "latest"}),
        _client("not-json", version_status=200),
        _client({"nope": "1"}, version_status=200),
        _client({"version": "0.40.5"}, version_status=404),
    )
    for client in cases:
        results = _check_ollama(settings, client)
        assert all(result.name != "ollama_q2_0" for result in results)
        assert any(result.name == "ollama" and result.ok for result in results)
