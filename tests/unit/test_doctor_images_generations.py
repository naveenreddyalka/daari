"""Doctor dry-checks OpenAPI for images/generations when frontier is on (#1092)."""

from __future__ import annotations

from daari.config.settings import FrontierProviderConfig
from daari.setup.doctor import _check_images_generations, run_doctor


def _enable_frontier_with_provider_key(settings) -> None:
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="dall-e-3",
            keys=["sk-test"],
        )
    ]


def test_frontier_disabled_skips_probe(settings):
    settings.frontier.enabled = False
    result = _check_images_generations(settings)
    assert result.name == "images_generations"
    assert result.ok
    assert result.optional
    assert "skipped" in result.detail


def test_frontier_on_without_key_warns(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.frontier.enabled = True
    settings.frontier.providers = []
    result = _check_images_generations(settings)
    assert not result.ok
    assert result.optional
    assert "501" in result.detail
    assert "/v1/images/generations" in result.detail


def test_frontier_on_with_key_openapi_ok(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    result = _check_images_generations(settings)
    assert result.ok
    assert result.optional
    assert "/v1/images/generations" in result.detail


def test_frontier_on_with_provider_key_openapi_ok(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    _enable_frontier_with_provider_key(settings)
    result = _check_images_generations(settings)
    assert result.ok
    assert "/v1/images/generations" in result.detail


def test_missing_openapi_path_warns(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    result = _check_images_generations(settings, openapi_paths={})
    assert not result.ok
    assert result.optional
    assert "/v1/images/generations" in result.detail


def test_run_doctor_includes_images_generations(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-test")
    settings.frontier.enabled = True
    row = next(
        item for item in run_doctor(settings, httpx_client=None) if item.name == "images_generations"
    )
    assert row.ok
    assert "/v1/images/generations" in row.detail
