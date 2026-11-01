"""security.offline_mode fail-closed off-box egress (#2034)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import httpx
import pytest

from daari.config.settings import Settings
from daari.config.validate import config_findings, offline_mode_findings
from daari.router.http_pool import build_async_client
from daari.security.offline_mode import (
    OfflineEgressBlocked,
    assert_offline_url_allowed,
    configure_offline_mode,
    offline_mode_enabled,
)
from daari.setup.doctor import _check_offline_mode, run_doctor


@pytest.fixture(autouse=True)
def _reset_offline_mode():
    configure_offline_mode(enabled=False, allow_hosts=())
    yield
    configure_offline_mode(enabled=False, allow_hosts=())


def test_settings_defaults_and_env(monkeypatch):
    s = Settings()
    assert s.security.offline_mode is False
    assert s.security.offline_allow_hosts == []

    monkeypatch.setenv("DAARI_SECURITY__OFFLINE_MODE", "true")
    monkeypatch.setenv("DAARI_SECURITY__OFFLINE_ALLOW_HOSTS", '["corp.example"]')
    loaded = Settings()
    assert loaded.security.offline_mode is True
    assert loaded.security.offline_allow_hosts == ["corp.example"]


def test_public_host_refused_when_offline():
    configure_offline_mode(enabled=True)
    with pytest.raises(OfflineEgressBlocked, match="offline_mode"):
        assert_offline_url_allowed(
            "https://api.openai.com/v1/chat/completions",
            resolver=lambda _h: ["93.184.216.34"],
        )


def test_allowlist_pass_through():
    configure_offline_mode(enabled=True, allow_hosts=["api.openai.com"])
    assert_offline_url_allowed(
        "https://api.openai.com/v1",
        resolver=lambda _h: ["93.184.216.34"],
    )


def test_loopback_and_rfc1918_untouched():
    configure_offline_mode(enabled=True)
    assert_offline_url_allowed("http://127.0.0.1:11434/api/tags")
    assert_offline_url_allowed("http://10.0.0.5:8080/v1")
    assert_offline_url_allowed(
        "http://ollama.local/api/tags",
        resolver=lambda _h: ["192.168.1.10"],
    )


def test_offline_disabled_allows_public():
    configure_offline_mode(enabled=False)
    assert_offline_url_allowed(
        "https://api.openai.com/v1",
        resolver=lambda _h: ["93.184.216.34"],
    )
    assert offline_mode_enabled() is False


@pytest.mark.asyncio
async def test_shared_httpx_client_refuses_public_host(monkeypatch):
    configure_offline_mode(enabled=True)
    monkeypatch.setattr(
        "daari.security.offline_mode._default_resolve",
        lambda _h: ["93.184.216.34"],
    )
    client = build_async_client(httpx)
    try:
        with pytest.raises(OfflineEgressBlocked, match="offline_mode"):
            await client.get("https://example.com/")
    finally:
        await client.aclose()


def test_refused_egress_logs_gateway_event(monkeypatch):
    events: list[tuple[str, dict]] = []

    def fake_log(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        fake_log,
    )
    configure_offline_mode(enabled=True)
    with pytest.raises(OfflineEgressBlocked):
        assert_offline_url_allowed(
            "https://hooks.example/alert",
            resolver=lambda _h: ["93.184.216.34"],
            surface="webhook",
        )
    assert events
    assert events[0][0] == "security.offline_egress_refused"
    assert events[0][1]["host"] == "hooks.example"
    assert events[0][1]["surface"] == "webhook"


def test_validate_warns_on_offbox_surfaces():
    settings = Settings(
        security={"offline_mode": True},
        frontier={"enabled": True, "base_url": "https://api.openai.com/v1"},
        alerts={"budget_webhook_url": "https://hooks.example/budget"},
        anthropic={"enforcement_webhook_url": "https://hooks.example/enforce"},
    )
    findings = offline_mode_findings(settings)
    joined = "\n".join(findings)
    assert "frontier.base_url" in joined
    assert "alerts.budget_webhook_url" in joined
    assert "anthropic.enforcement_webhook_url" in joined

    monkeypatch_env = {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example:4318"}
    old = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    try:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = monkeypatch_env[
            "OTEL_EXPORTER_OTLP_ENDPOINT"
        ]
        settings2 = Settings(
            security={"offline_mode": True},
            observability={"otel": True},
        )
        otel_findings = offline_mode_findings(settings2)
        assert any("otel" in f.lower() or "OTLP" in f for f in otel_findings)
    finally:
        if old is None:
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        else:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = old


def test_validate_quiet_when_offline_off_or_local_only():
    assert offline_mode_findings(Settings()) == []
    settings = Settings(
        security={"offline_mode": True},
        ollama={"base_url": "http://127.0.0.1:11434"},
        frontier={"enabled": False},
    )
    assert offline_mode_findings(settings) == []


def test_config_findings_includes_offline_warnings():
    user = {
        "security": {"offline_mode": True},
        "frontier": {"enabled": True, "base_url": "https://api.openai.com/v1"},
    }
    merged = Settings().model_dump()
    merged["security"] = {"offline_mode": True, "offline_allow_hosts": [], "at_rest_key": "", "at_rest_key_previous": ""}
    merged["frontier"] = {
        **merged["frontier"],
        "enabled": True,
        "base_url": "https://api.openai.com/v1",
    }
    findings = config_findings(user, merged, Settings)
    assert any("frontier.base_url" in f for f in findings)


def test_doctor_reports_offline_state():
    off = Settings()
    row = _check_offline_mode(off)
    assert row.name == "offline_mode"
    assert row.ok is True
    assert "off" in row.detail.lower()

    on = Settings(
        security={
            "offline_mode": True,
            "offline_allow_hosts": ["corp.internal"],
        }
    )
    row_on = _check_offline_mode(on)
    assert row_on.ok is True
    assert "on" in row_on.detail.lower()
    assert "corp.internal" in row_on.detail

    rows = run_doctor(on, httpx_client=MagicMock())
    assert any(r.name == "offline_mode" for r in rows)
