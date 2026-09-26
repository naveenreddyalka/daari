"""Doctor dry-checks OpenAPI for moderations and rerank when frontier is on (#1110)."""

from __future__ import annotations

from daari.config.settings import FrontierProviderConfig
from daari.setup.doctor import _check_moderations, _check_rerank, run_doctor


def _enable_frontier_with_provider_key(settings) -> None:
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            keys=["sk-test"],
        )
    ]


def test_moderations_frontier_disabled_skips(settings):
    settings.frontier.enabled = False
    result = _check_moderations(settings)
    assert result.name == "moderations"
    assert result.ok
    assert result.optional
    assert "skipped" in result.detail
    assert "501" in result.detail


def test_rerank_frontier_disabled_skips(settings):
    settings.frontier.enabled = False
    result = _check_rerank(settings)
    assert result.name == "rerank"
    assert result.ok
    assert result.optional
    assert "skipped" in result.detail
    assert "501" in result.detail


def test_moderations_frontier_on_without_key_warns(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.frontier.enabled = True
    settings.frontier.providers = []
    result = _check_moderations(settings)
    assert not result.ok
    assert result.optional
    assert "501" in result.detail
    assert "/v1/moderations" in result.detail


def test_rerank_frontier_on_without_key_warns(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.frontier.enabled = True
    settings.frontier.providers = []
    result = _check_rerank(settings)
    assert not result.ok
    assert result.optional
    assert "501" in result.detail
    assert "/v1/rerank" in result.detail


def test_moderations_frontier_on_with_key_openapi_ok(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    result = _check_moderations(settings)
    assert result.ok
    assert result.optional
    assert "/v1/moderations" in result.detail


def test_rerank_frontier_on_with_key_openapi_ok(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    result = _check_rerank(settings)
    assert result.ok
    assert result.optional
    assert "/v1/rerank" in result.detail


def test_moderations_provider_key_openapi_ok(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    _enable_frontier_with_provider_key(settings)
    result = _check_moderations(settings)
    assert result.ok
    assert "/v1/moderations" in result.detail


def test_rerank_provider_key_openapi_ok(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    _enable_frontier_with_provider_key(settings)
    result = _check_rerank(settings)
    assert result.ok
    assert "/v1/rerank" in result.detail


def test_moderations_missing_openapi_path_warns(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    result = _check_moderations(settings, openapi_paths={})
    assert not result.ok
    assert result.optional
    assert "/v1/moderations" in result.detail


def test_rerank_missing_openapi_path_warns(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    result = _check_rerank(settings, openapi_paths={})
    assert not result.ok
    assert result.optional
    assert "/v1/rerank" in result.detail


def test_run_doctor_includes_moderations_and_rerank(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    rows = {item.name: item for item in run_doctor(settings, httpx_client=None)}
    assert rows["moderations"].ok
    assert "/v1/moderations" in rows["moderations"].detail
    assert rows["rerank"].ok
    assert "/v1/rerank" in rows["rerank"].detail
