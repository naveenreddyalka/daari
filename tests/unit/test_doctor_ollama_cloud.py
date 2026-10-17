"""Doctor must not tell operators to ollama pull :cloud model ids (#1731)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from daari.setup.doctor import _check_decisions_local_models, _check_ollama


def _tags(models: list[str]) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"models": [{"name": name} for name in models]}
    return response


def _client(models: list[str]) -> MagicMock:
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _tags(models)
    return client


def test_cloud_tier_and_embedding_ids_skip_tags_and_pull(settings):
    settings.models.l3 = "clef:cloud"
    settings.models.l4 = "clef-flash:cloud"
    settings.models.l5 = "some-large:cloud"
    settings.cache.l1.embedding_model = "embed:cloud"
    settings.cache.l1.enabled = True

    results = _check_ollama(settings, _client([]))
    by_name = {result.name: result for result in results}
    for name in ("model", "model_l4", "model_l5", "embedding_model"):
        assert by_name[name].ok is True
        assert "ollama pull" not in by_name[name].detail
        assert "Ollama cloud (ollama.com)" in by_name[name].detail
        assert "not a local blob" in by_name[name].detail


def test_missing_local_model_still_suggests_ollama_pull(settings):
    settings.models.l3 = "llama3.2:3b"
    results = _check_ollama(settings, _client(["other:7b"]))
    model = next(result for result in results if result.name == "model")
    assert model.ok is False
    assert "ollama pull llama3.2:3b" in model.detail


def test_cloud_only_decisions_catalog_is_not_a_local_pull(settings, monkeypatch):
    monkeypatch.setattr(
        "daari.gateway.decisions.local_decisions_models",
        lambda _settings=None: frozenset({"clef:cloud"}),
    )
    result = _check_decisions_local_models(settings, _client([]))
    assert result is not None
    assert result.ok is True
    assert "clef:cloud" in result.detail
    assert "ollama pull" not in result.detail
    assert "Ollama cloud (ollama.com)" in result.detail
    assert "not a local blob" in result.detail


def test_mixed_decisions_catalog_pull_hint_skips_cloud_ids(settings, monkeypatch):
    monkeypatch.setattr(
        "daari.gateway.decisions.local_decisions_models",
        lambda _settings=None: frozenset({"nimble", "clef:cloud"}),
    )
    result = _check_decisions_local_models(settings, _client([]))
    assert result is not None
    assert result.ok is False
    assert "ollama pull" in result.detail
    assert "clef:cloud" not in result.detail
    assert "nimble" in result.detail
