from __future__ import annotations

import hashlib

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
        assert settings.cache.l1.similarity_threshold == 0.88
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

    def test_load_merges_project_profile_by_cwd_hash(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        profile_root = tmp_path / ".daari" / "profiles"
        profile_root.mkdir(parents=True)
        digest = hashlib.sha1(str(repo.resolve()).encode("utf-8")).hexdigest()[:12]
        (profile_root / f"{digest}.yaml").write_text("models:\n  l3: profile-hash:7b\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(repo)
        settings = Settings.load(config_path=tmp_path / "missing.yaml")
        assert settings.models.l3 == "profile-hash:7b"

    def test_load_merges_named_profile_from_env(self, tmp_path, monkeypatch):
        profile_root = tmp_path / ".daari" / "profiles"
        profile_root.mkdir(parents=True)
        (profile_root / "work.yaml").write_text("routing:\n  prefer: accuracy\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("DAARI_PROFILE", "work")
        settings = Settings.load(config_path=tmp_path / "missing.yaml")
        assert settings.routing.prefer == "accuracy"

    def test_load_skills_system_prefix(self, tmp_path, monkeypatch):
        skills = tmp_path / ".daari" / "skills"
        skills.mkdir(parents=True)
        (skills / "policy.md").write_text("Always prefer local execution.", encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        settings = Settings.load(config_path=tmp_path / "missing.yaml")
        assert "Local daari skills" in settings.skills_system_prefix
        assert "Always prefer local execution." in settings.skills_system_prefix

    def test_integrations_defaults_include_gitlab(self):
        settings = Settings.model_validate({})
        assert settings.integrations.gitlab.url == "https://gitlab.com/api/v4"
        assert "@gitlab" in settings.integrations.gitlab.triggers

    def test_load_org_id_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("DAARI_ORG_ID", "acme")
        settings = Settings.load(config_path=tmp_path / "missing.yaml")
        assert settings.enterprise.enabled is True
        assert settings.enterprise.org_id == "acme"
        assert settings.org_cache_root == tmp_path / ".daari" / "org" / "acme" / "cache"

    def test_org_settings_merge_with_shared_cache(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            (
                "enterprise:\n"
                "  enabled: true\n"
                "  org_id: eng\n"
                "  shared_cache_path: /tmp/daari-shared\n"
                "  policy_overrides:\n"
                "    tools.unknown: ask\n"
            ),
            encoding="utf-8",
        )
        settings = Settings.load(config_path=config)
        assert settings.enterprise.enabled is True
        assert settings.enterprise.org_id == "eng"
        assert settings.enterprise.policy_overrides["tools.unknown"] == "ask"
        assert str(settings.org_cache_root) == "/tmp/daari-shared"

    def test_org_alias_block_maps_to_enterprise(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            (
                "org:\n"
                "  id: acme\n"
                "  shared_cache_url: http://127.0.0.1:11436\n"
                "  shared_cache_timeout_seconds: 2.5\n"
                "  cache:\n"
                "    enabled: true\n"
            ),
            encoding="utf-8",
        )
        settings = Settings.load(config_path=config)
        assert settings.enterprise.resolved_org_id == "acme"
        assert settings.enterprise.shared_cache_url == "http://127.0.0.1:11436"
        assert settings.enterprise.shared_cache_timeout_seconds == 2.5
        assert settings.enterprise.cache.enabled is True

    def test_org_alias_learning_fields_map_to_enterprise(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            (
                "org:\n"
                "  id: acme\n"
                "  learning_enabled: true\n"
                "  learning_url: http://127.0.0.1:11436\n"
            ),
            encoding="utf-8",
        )
        settings = Settings.load(config_path=config)
        assert settings.enterprise.resolved_org_id == "acme"
        assert settings.enterprise.learning_enabled is True
        assert settings.enterprise.learning_url == "http://127.0.0.1:11436"
