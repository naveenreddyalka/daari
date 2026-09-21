"""Doctor warns when otlp_logs is on without OTEL endpoint (#878)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_otlp_logs, run_doctor


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_quiet_when_otlp_logs_off(settings, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    settings.observability.otlp_logs = False
    result = _check_otlp_logs(settings)
    assert result.name == "otlp_logs"
    assert result.ok is True
    assert result.optional is True


def test_warns_when_logs_on_without_endpoint(settings, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    settings.observability.otlp_logs = True
    result = _check_otlp_logs(settings)
    assert result.ok is False
    assert result.optional is True
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in result.detail


def test_passes_when_logs_on_with_endpoint(settings, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    settings.observability.otlp_logs = True
    result = _check_otlp_logs(settings)
    assert result.ok is True
    assert "4318" in result.detail or "endpoint" in result.detail.lower()


def test_run_doctor_includes_check(settings, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    settings.observability.otlp_logs = True
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "otlp_logs" in by_name
    assert by_name["otlp_logs"].ok is False
