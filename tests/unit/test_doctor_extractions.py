"""Doctor tip for POST /v1/extractions local + frontier paths (#2271)."""

from __future__ import annotations

from daari.setup.doctor import _check_extractions, run_doctor


def test_extractions_ok_when_systemone_enabled(settings):
    settings.systemone.enabled = True
    settings.frontier.enabled = False
    result = _check_extractions(settings)
    assert result.name == "extractions"
    assert result.ok is True
    assert "/v1/extractions" in result.detail
    assert "systemone" in result.detail


def test_extractions_tip_when_systemone_off_and_frontier_off(settings):
    settings.systemone.enabled = False
    settings.frontier.enabled = False
    result = _check_extractions(settings)
    assert result.ok is False
    assert "systemone.enabled=false" in result.detail
    assert "/v1/extractions" in result.detail


def test_extractions_tip_when_frontier_on_without_key(settings, monkeypatch):
    settings.systemone.enabled = True
    settings.frontier.enabled = True
    monkeypatch.delenv("DAARI_FRONTIER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert settings.resolve_frontier_api_key() is None
    result = _check_extractions(settings)
    assert result.ok is False
    assert "no API key" in result.detail


def test_run_doctor_includes_extractions(settings):
    settings.systemone.enabled = False
    settings.frontier.enabled = False
    row = next(
        item for item in run_doctor(settings, httpx_client=None) if item.name == "extractions"
    )
    assert row.ok is False
    assert "/v1/extractions" in row.detail
