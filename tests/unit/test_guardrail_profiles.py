"""Named guardrail profiles bound per key / team (#1548)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from daari.auth.virtual_keys import Team, VirtualKey
from daari.config.settings import GuardrailSettings, Settings
from daari.gateway.guardrails import (
    PROFILE_METADATA_FIELD,
    engine_for_request,
    profile_engines_from_settings,
    resolve_profile_name,
    validate_profile_name,
)
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.server.auth import AuthClaims, apply_auth_claims_to_meta, apply_selected_team


def _settings(**guardrails) -> Settings:
    return Settings.model_validate({"guardrails": guardrails})


def _profiles() -> dict:
    return {
        "strict": {
            "output_rules": [
                {"name": "ssn", "pattern": r"\d{3}-\d{2}-\d{4}", "action": "redact"}
            ]
        },
        "lenient": {"output_rules": [{"name": "noop", "pattern": "never-matches-zzz"}]},
        "off": {"enabled": False},
    }


class TestSettings:
    def test_profiles_reuse_guardrail_shape_and_default_enabled(self):
        settings = _settings(enabled=False, profiles=_profiles())
        strict = settings.guardrails.profiles["strict"]
        assert isinstance(strict, GuardrailSettings)
        assert strict.enabled is True
        assert strict.output_rules[0].action == "redact"
        assert settings.guardrails.profiles["off"].enabled is False

    def test_profiles_cannot_nest(self):
        with pytest.raises(ValidationError, match="cannot nest"):
            _settings(profiles={"a": {"profiles": {"b": {}}}})

    def test_blank_profile_name_rejected(self):
        with pytest.raises(ValidationError, match="profile name"):
            _settings(profiles={"  ": {}})

    def test_sso_key_mapping_unknown_profile_fails_at_config_validation(self):
        with pytest.raises(ValidationError, match="unknown guardrail profile 'nope'"):
            Settings.model_validate(
                {
                    "guardrails": {"profiles": {"strict": {}}},
                    "enterprise": {
                        "sso": {"key_mappings": {"eng": {"guardrail_profile": "nope"}}}
                    },
                }
            )

    def test_sso_key_mapping_known_profile_ok(self):
        settings = Settings.model_validate(
            {
                "guardrails": {"profiles": {"strict": {}}},
                "enterprise": {
                    "sso": {
                        "key_mappings": {"eng": {"guardrail_profile": "strict"}},
                        "default_policy": {"guardrail_profile": "strict"},
                    }
                },
            }
        )
        assert settings.enterprise.sso.key_mappings["eng"].guardrail_profile == "strict"


class TestEngines:
    def test_profile_engines_built_even_when_global_disabled(self):
        settings = _settings(enabled=False, profiles=_profiles())
        engines = profile_engines_from_settings(settings)
        assert set(engines) == {"strict", "lenient", "off"}
        assert engines["strict"] is not None and engines["strict"].enabled
        assert engines["lenient"] is not None
        # Explicit enabled=false is an opt-out for bound tenants.
        assert engines["off"] is None

    def test_engine_for_request_precedence(self):
        settings = _settings(enabled=True, profiles=_profiles())
        engines = profile_engines_from_settings(settings)
        base = object()

        def req(name: str | None) -> InternalRequest:
            return InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                meta=RequestMeta(guardrail_profile=name),
            )

        assert engine_for_request(base, engines, req(None)) is base
        assert engine_for_request(base, engines, req("strict")) is engines["strict"]
        assert engine_for_request(base, engines, req("off")) is None
        # Unknown name falls back to the global engine rather than dropping coverage.
        assert engine_for_request(base, engines, req("ghost")) is base

    def test_validate_profile_name(self):
        settings = _settings(profiles=_profiles())
        assert validate_profile_name("strict", settings) == "strict"
        assert validate_profile_name("", settings) is None
        assert validate_profile_name(None, settings) is None
        with pytest.raises(ValueError, match="unknown guardrail profile 'ghost'"):
            validate_profile_name("ghost", settings)


class TestBinding:
    def test_resolve_profile_name_key_beats_team(self):
        assert (
            resolve_profile_name(
                {PROFILE_METADATA_FIELD: "strict"}, {PROFILE_METADATA_FIELD: "lenient"}
            )
            == "strict"
        )
        assert resolve_profile_name({}, {PROFILE_METADATA_FIELD: "lenient"}) == "lenient"
        assert resolve_profile_name({}, {}) is None
        assert resolve_profile_name(None, None) is None

    def test_claims_carry_profile_into_request_meta(self):
        key = VirtualKey(
            key_id="k1",
            name="k1",
            prefix="dk_",
            metadata={PROFILE_METADATA_FIELD: "strict"},
        )
        claims = AuthClaims(kind="virtual", key_id="k1", virtual_key=key, guardrail_profile="strict")
        meta = RequestMeta()
        apply_auth_claims_to_meta(meta, claims)
        assert meta.guardrail_profile == "strict"

    def test_selected_team_profile_applies_when_key_unbound(self):
        class Store:
            def get_team(self, team_id):
                return Team(
                    team_id=team_id, name="t", metadata={PROFILE_METADATA_FIELD: "lenient"}
                )

        key = VirtualKey(key_id="k1", name="k1", prefix="dk_")
        claims = AuthClaims(kind="virtual", key_id="k1", virtual_key=key)
        apply_selected_team(claims, "t1", Store())  # type: ignore[arg-type]
        assert claims.guardrail_profile == "lenient"

        bound = VirtualKey(
            key_id="k2", name="k2", prefix="dk_", metadata={PROFILE_METADATA_FIELD: "strict"}
        )
        claims2 = AuthClaims(
            kind="virtual", key_id="k2", virtual_key=bound, guardrail_profile="strict"
        )
        apply_selected_team(claims2, "t1", Store())  # type: ignore[arg-type]
        assert claims2.guardrail_profile == "strict"


class TestStores:
    def test_sqlite_store_binds_key_and_team(self, tmp_path):
        from daari.auth.virtual_keys import VirtualKeyStore

        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("a", client_id="a")
        assert store.update_guardrail_profile(created.key.key_id, "strict")
        key = store.resolve(created.plaintext)
        assert key is not None and key.metadata[PROFILE_METADATA_FIELD] == "strict"
        assert store.update_guardrail_profile(created.key.key_id, None)
        key = store.resolve(created.plaintext)
        assert key is not None and PROFILE_METADATA_FIELD not in key.metadata
        assert not store.update_guardrail_profile("missing", "strict")

        team = store.create_team("eng")
        assert store.update_team_guardrail_profile(team.team_id, "lenient")
        loaded = store.get_team(team.team_id)
        assert loaded is not None and loaded.metadata[PROFILE_METADATA_FIELD] == "lenient"
        assert not store.update_team_guardrail_profile("missing", "lenient")


class TestPolicySync:
    def test_apply_policy_distributes_profiles(self, tmp_path):
        from daari.enterprise.policy_sync import apply_policy_to_runtime
        from daari.router.router import AppContext

        settings = Settings.model_validate(
            {
                "guardrails": {"enabled": False},
                "cache": {
                    "l0": {"enabled": False, "path": str(tmp_path / "l0")},
                    "l1": {"enabled": False, "path": str(tmp_path / "l1")},
                },
                "trace": {"path": str(tmp_path / "t.sqlite3")},
            }
        )
        router = AppContext.from_settings(settings).router
        assert router.guardrail_profiles == {}
        applied = apply_policy_to_runtime(
            settings, router, {"guardrails": {"profiles": _profiles()}}
        )
        assert applied["guardrails.profiles"] == ["lenient", "off", "strict"]
        assert set(settings.guardrails.profiles) == {"strict", "lenient", "off"}
        assert router.guardrail_profiles["strict"].enabled

    def test_apply_policy_rejects_invalid_profiles(self, tmp_path):
        from daari.enterprise.policy_sync import apply_policy_to_runtime
        from daari.router.router import AppContext

        settings = Settings.model_validate(
            {
                "cache": {
                    "l0": {"enabled": False, "path": str(tmp_path / "l0")},
                    "l1": {"enabled": False, "path": str(tmp_path / "l1")},
                },
                "trace": {"path": str(tmp_path / "t.sqlite3")},
            }
        )
        router = AppContext.from_settings(settings).router
        applied = apply_policy_to_runtime(
            settings, router, {"guardrails": {"profiles": {"bad": {"profiles": {"x": {}}}}}}
        )
        assert "guardrails.profiles" not in applied
        assert settings.guardrails.profiles == {}

    def test_apply_org_config_persists_profiles(self, tmp_path):
        import yaml

        from daari.enterprise.bootstrap import apply_org_config

        path = tmp_path / "config.yaml"
        apply_org_config(
            {"org": {"org_id": "acme"}, "guardrails": {"profiles": _profiles()}},
            config_path=path,
        )
        loaded = yaml.safe_load(path.read_text())
        assert "strict" in loaded["guardrails"]["profiles"]


class TestCli:
    def test_keys_create_rejects_unknown_profile(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli import app as cli_app

        settings = Settings.model_validate(
            {
                "guardrails": {"profiles": {"strict": {}}},
                "server": {"virtual_keys": {"path": str(tmp_path / "vk.sqlite3")}},
            }
        )
        monkeypatch.setattr(cli_app, "get_settings", lambda: settings)
        runner = CliRunner()
        bad = runner.invoke(cli_app.app, ["keys", "create", "a", "--guardrail-profile", "ghost"])
        assert bad.exit_code == 1
        assert "unknown guardrail profile 'ghost'" in bad.output
        good = runner.invoke(
            cli_app.app, ["keys", "create", "b", "--guardrail-profile", "strict"]
        )
        assert good.exit_code == 0, good.output
        assert "guardrail_profile: strict" in good.output

    def test_team_create_and_update_profile(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.auth.virtual_keys import VirtualKeyStore
        from daari.cli import app as cli_app

        settings = Settings.model_validate(
            {
                "guardrails": {"profiles": {"strict": {}, "lenient": {}}},
                "server": {"virtual_keys": {"path": str(tmp_path / "vk.sqlite3")}},
            }
        )
        monkeypatch.setattr(cli_app, "get_settings", lambda: settings)
        runner = CliRunner()
        res = runner.invoke(
            cli_app.app, ["keys", "team-create", "eng", "--guardrail-profile", "strict"]
        )
        assert res.exit_code == 0, res.output
        store = VirtualKeyStore(settings.virtual_keys_path)
        team = store.get_team(name="eng")
        assert team is not None and team.metadata[PROFILE_METADATA_FIELD] == "strict"
        res = runner.invoke(
            cli_app.app,
            ["keys", "team-update", team.team_id, "--guardrail-profile", "lenient"],
        )
        assert res.exit_code == 0, res.output
        team = store.get_team(team.team_id)
        assert team is not None and team.metadata[PROFILE_METADATA_FIELD] == "lenient"
        res = runner.invoke(
            cli_app.app,
            ["keys", "team-update", team.team_id, "--guardrail-profile", "ghost"],
        )
        assert res.exit_code == 1
