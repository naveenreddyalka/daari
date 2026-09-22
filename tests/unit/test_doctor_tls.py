"""Doctor warns when auth + non-loopback host lack TLS (#932)."""

from __future__ import annotations

import httpx

from daari.config.settings import Settings
from daari.setup.doctor import _check_tls_exposure, run_doctor


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_warns_when_auth_non_loopback_without_tls(settings: Settings) -> None:
    settings.server.host = "0.0.0.0"
    settings.server.api_key = "master-secret"
    settings.server.tls.cert_file = ""
    settings.server.tls.key_file = ""
    result = _check_tls_exposure(settings)
    assert result.name == "tls_exposure"
    assert result.ok is False
    assert result.optional is True
    assert "tls" in result.detail.lower() or "plaintext" in result.detail.lower()


def test_ok_on_loopback_without_tls(settings: Settings) -> None:
    settings.server.host = "127.0.0.1"
    settings.server.api_key = "master-secret"
    result = _check_tls_exposure(settings)
    assert result.ok is True


def test_ok_when_tls_configured(settings: Settings) -> None:
    settings.server.host = "0.0.0.0"
    settings.server.api_key = "master-secret"
    settings.server.tls.cert_file = "/certs/tls.crt"
    settings.server.tls.key_file = "/certs/tls.key"
    result = _check_tls_exposure(settings)
    assert result.ok is True


def test_ok_when_auth_disabled(settings: Settings) -> None:
    settings.server.host = "0.0.0.0"
    settings.server.api_key = ""
    result = _check_tls_exposure(settings)
    assert result.ok is True


def test_run_doctor_includes_check(settings: Settings) -> None:
    settings.server.host = "0.0.0.0"
    settings.server.api_key = "master-secret"
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "tls_exposure" in by_name
    assert by_name["tls_exposure"].ok is False
