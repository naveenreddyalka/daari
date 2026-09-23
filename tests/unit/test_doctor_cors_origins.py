"""Doctor advises when web-ui origin is missing from cors_origins (#999)."""

from __future__ import annotations

from daari.setup.doctor import _check_cors_origins, run_doctor


def test_empty_cors_origins_is_quiet_advisory(settings):
    settings.server.cors_origins = []
    result = _check_cors_origins(settings)
    assert result.name == "cors_origins"
    assert result.ok
    assert result.optional
    assert "empty" in result.detail
    assert "11437" in result.detail


def test_cors_allowlist_with_web_ui_origin_ok(settings):
    settings.server.cors_origins = ["http://127.0.0.1:11437"]
    result = _check_cors_origins(settings)
    assert result.ok
    assert "includes web-ui" in result.detail


def test_cors_allowlist_missing_web_ui_warns(settings):
    settings.server.cors_origins = ["https://app.example.com"]
    result = _check_cors_origins(settings)
    assert not result.ok
    assert result.optional
    assert "missing web-ui origin" in result.detail


def test_daari_web_ui_origin_env_override(settings, monkeypatch):
    monkeypatch.setenv("DAARI_WEB_UI_ORIGIN", "http://127.0.0.1:9999")
    settings.server.cors_origins = ["http://127.0.0.1:9999"]
    assert _check_cors_origins(settings).ok
    settings.server.cors_origins = ["http://127.0.0.1:11437"]
    missing = _check_cors_origins(settings)
    assert not missing.ok
    assert "9999" in missing.detail


def test_run_doctor_includes_cors_origins(settings):
    settings.server.cors_origins = []
    names = [item.name for item in run_doctor(settings, httpx_client=None)]
    assert "cors_origins" in names
