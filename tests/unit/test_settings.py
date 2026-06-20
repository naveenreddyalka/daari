from __future__ import annotations

import pytest

from daari.config.settings import Settings


class TestSettings:
    def test_load_merges_user_config(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("models:\n  l3: custom:7b\n", encoding="utf-8")
        settings = Settings.load(config_path=config)
        assert settings.models.l3 == "custom:7b"
        assert settings.server.port == 11435

    def test_l0_cache_path_expands_user(self, tmp_path):
        settings = Settings.model_validate(
            {
                "cache": {"l0": {"path": str(tmp_path / "cache")}},
            }
        )
        assert settings.l0_cache_path == tmp_path / "cache"

    def test_l1_cache_path_expands_user(self, tmp_path):
        settings = Settings.model_validate(
            {
                "cache": {
                    "l1": {
                        "path": str(tmp_path / "l1"),
                        "similarity_threshold": 0.95,
                        "max_entries": 500,
                        "embedding_model": "custom-embed",
                    }
                },
            }
        )
        assert settings.l1_cache_path == tmp_path / "l1"
        assert settings.cache.l1.similarity_threshold == 0.95
        assert settings.cache.l1.max_entries == 500
        assert settings.cache.l1.embedding_model == "custom-embed"

    def test_l1_defaults(self):
        settings = Settings.model_validate({})
        assert settings.cache.l1.enabled is True
        assert settings.cache.l1.similarity_threshold == 0.92
        assert settings.cache.l1.embedding_model == "nomic-embed-text"

    def test_frontier_defaults(self):
        settings = Settings.model_validate({})
        assert settings.frontier.enabled is False
        assert settings.frontier.provider == "openai"
        assert settings.frontier.model == "gpt-4o-mini"
        assert settings.frontier.confidence_threshold == 0.7

    def test_resolve_frontier_api_key(self, monkeypatch):
        settings = Settings.model_validate({})
        monkeypatch.delenv("DAARI_FRONTIER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert settings.resolve_frontier_api_key() is None

        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        assert settings.resolve_frontier_api_key() == "sk-openai"

        monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-daari")
        assert settings.resolve_frontier_api_key() == "sk-daari"

    def test_invalid_config_rejected(self):
        with pytest.raises(Exception):
            Settings.model_validate({"server": {"port": "not-a-number"}})
