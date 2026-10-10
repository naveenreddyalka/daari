"""Doctor tip for POST /v1/decisions local + gpt-6-luna paths (#1501)."""

from __future__ import annotations

from daari.setup.doctor import _check_decisions, run_doctor


def test_decisions_ok_when_systemone_enabled(settings):
    settings.systemone.enabled = True
    settings.frontier.enabled = False
    result = _check_decisions(settings)
    assert result.name == "decisions"
    assert result.ok is True
    assert "/v1/decisions" in result.detail
    assert "systemone" in result.detail


def test_decisions_tip_when_systemone_off_and_frontier_off(settings):
    settings.systemone.enabled = False
    settings.frontier.enabled = False
    result = _check_decisions(settings)
    assert result.ok is False
    assert "systemone.enabled=false" in result.detail
    assert "/v1/decisions" in result.detail
    assert "gpt-6-luna" in result.detail


def test_decisions_tip_when_frontier_on_without_key(settings, monkeypatch):
    settings.systemone.enabled = True
    settings.frontier.enabled = True
    monkeypatch.delenv("DAARI_FRONTIER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert settings.resolve_frontier_api_key() is None
    result = _check_decisions(settings)
    assert result.ok is False
    assert "no API key" in result.detail
    assert "gpt-6-luna" in result.detail


def test_run_doctor_includes_decisions(settings):
    settings.systemone.enabled = False
    settings.frontier.enabled = False
    row = next(
        item for item in run_doctor(settings, httpx_client=None) if item.name == "decisions"
    )
    assert row.ok is False
    assert "/v1/decisions" in row.detail
