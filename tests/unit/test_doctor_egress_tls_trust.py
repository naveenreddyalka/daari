"""Doctor tip for eMudhra/emSign still trusted on egress (#1907)."""

from __future__ import annotations

import httpx

from daari.config.settings import Settings
from daari.setup.doctor import _check_egress_tls_trust, run_doctor


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tip_when_distrust_disabled(settings: Settings) -> None:
    settings.upstream.distrust_emudhra_ca = False
    result = _check_egress_tls_trust(settings)
    assert result.name == "egress_tls_trust"
    assert result.ok is False
    assert result.optional is True
    detail = result.detail.lower()
    assert "emudhra" in detail or "emsign" in detail
    assert "litellm" in detail or "1.106.3" in result.detail


def test_ok_when_distrust_enabled(settings: Settings) -> None:
    settings.upstream.distrust_emudhra_ca = True
    result = _check_egress_tls_trust(settings)
    assert result.name == "egress_tls_trust"
    assert result.ok is True
    assert "distrust" in result.detail.lower() or "excluded" in result.detail.lower()


def test_run_doctor_includes_check(settings: Settings) -> None:
    settings.upstream.distrust_emudhra_ca = False
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "egress_tls_trust" in by_name
    assert by_name["egress_tls_trust"].ok is False
