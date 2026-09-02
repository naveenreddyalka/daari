"""secret:// reference resolution (issue #288).

Keys stop living as plaintext in config: values may be `secret://` URIs
resolved once at startup from an env file, an operator command (op/vault/aws
CLIs), or the OS keychain — no new runtime dependency, everything shells out.
Failures are fatal and name the ref; the resolved value must never appear in
errors or gateway logs.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from daari.config.settings import Settings
from daari.security.secret_refs import (
    SecretRefError,
    clear_registered_secrets,
    is_secret_ref,
    iter_secret_refs,
    redact_secrets,
    resolve_secret_ref,
    resolve_settings_secrets,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    clear_registered_secrets()
    yield
    clear_registered_secrets()


def test_plain_strings_are_not_refs():
    assert not is_secret_ref("sk-plain-key")
    assert not is_secret_ref("")
    assert not is_secret_ref(None)
    assert is_secret_ref("secret://env-file/x#K")


class TestEnvFileScheme:
    def test_resolves_key_from_env_file(self, tmp_path):
        env = tmp_path / "daari.env"
        env.write_text("OTHER=1\nAPI_KEY=abc123\n", encoding="utf-8")
        assert resolve_secret_ref(f"secret://env-file/{env}#API_KEY") == "abc123"

    def test_strips_quotes_and_export_prefix(self, tmp_path):
        env = tmp_path / "daari.env"
        env.write_text('export API_KEY="quoted value"\n', encoding="utf-8")
        assert resolve_secret_ref(f"secret://env-file/{env}#API_KEY") == "quoted value"

    def test_missing_key_is_fatal_and_names_the_ref(self, tmp_path):
        env = tmp_path / "daari.env"
        env.write_text("OTHER=topsecret\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#MISSING"
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(ref)
        assert ref in str(excinfo.value)
        assert "topsecret" not in str(excinfo.value)

    def test_missing_file_is_fatal(self, tmp_path):
        ref = f"secret://env-file/{tmp_path}/absent.env#KEY"
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(ref)
        assert ref in str(excinfo.value)


class TestExecScheme:
    def test_runs_command_and_strips_output(self):
        seen: list[list[str]] = []

        def runner(argv):
            seen.append(argv)
            return "tok-from-vault\n"

        value = resolve_secret_ref(
            "secret://exec/op read op://vault/item/key", runner=runner
        )
        assert value == "tok-from-vault"
        assert seen == [["op", "read", "op://vault/item/key"]]

    def test_command_failure_is_fatal_and_never_leaks_output(self):
        def runner(argv):
            raise subprocess.CalledProcessError(1, argv, output="partial-secret")

        ref = "secret://exec/vault kv get -field=key secret/daari"
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(ref, runner=runner)
        assert ref in str(excinfo.value)
        assert "partial-secret" not in str(excinfo.value)

    def test_empty_output_is_fatal(self):
        with pytest.raises(SecretRefError):
            resolve_secret_ref("secret://exec/true", runner=lambda argv: "\n")


class TestKeychainScheme:
    def test_macos_uses_security_cli(self):
        seen: list[list[str]] = []

        def runner(argv):
            seen.append(argv)
            return "chain-secret\n"

        value = resolve_secret_ref(
            "secret://keychain/daari-frontier/naveen", runner=runner, platform="darwin"
        )
        assert value == "chain-secret"
        assert seen == [
            ["security", "find-generic-password", "-s", "daari-frontier", "-a", "naveen", "-w"]
        ]

    def test_linux_uses_secret_tool(self):
        seen: list[list[str]] = []

        def runner(argv):
            seen.append(argv)
            return "linux-secret"

        value = resolve_secret_ref(
            "secret://keychain/daari-frontier/naveen", runner=runner, platform="linux"
        )
        assert value == "linux-secret"
        assert seen == [
            ["secret-tool", "lookup", "service", "daari-frontier", "account", "naveen"]
        ]

    def test_malformed_ref_is_fatal(self):
        with pytest.raises(SecretRefError):
            resolve_secret_ref("secret://keychain/only-service", runner=lambda a: "x")


def test_unknown_scheme_is_fatal():
    with pytest.raises(SecretRefError) as excinfo:
        resolve_secret_ref("secret://vault-sdk/whatever")
    assert "secret://vault-sdk/whatever" in str(excinfo.value)


class TestSettingsResolution:
    def _settings(self, ref: str) -> Settings:
        return Settings.model_validate(
            {
                "frontier": {"providers": [{"id": "openai", "keys": [ref]}]},
                "enterprise": {"shared_cache_token": ref},
                "cache": {"redis_url": ref},
                "server": {"api_key": "plain-master-key"},
            }
        )

    def test_resolves_nested_fields_in_place(self, tmp_path):
        env = tmp_path / "daari.env"
        env.write_text("K=resolved-value\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#K"
        settings = self._settings(ref)
        resolved = resolve_settings_secrets(settings)
        assert settings.frontier.providers[0].keys == ["resolved-value"]
        assert settings.enterprise.shared_cache_token == "resolved-value"
        assert settings.cache.redis_url == "resolved-value"
        assert settings.server.api_key == "plain-master-key"
        assert len(resolved) == 3

    def test_iter_secret_refs_reports_dotted_paths(self, tmp_path):
        ref = "secret://env-file/x.env#K"
        settings = self._settings(ref)
        paths = dict(iter_secret_refs(settings))
        assert paths["frontier.providers[0].keys[0]"] == ref
        assert paths["enterprise.shared_cache_token"] == ref
        assert paths["cache.redis_url"] == ref

    def test_failure_names_config_path_and_ref(self, tmp_path):
        ref = f"secret://env-file/{tmp_path}/absent.env#K"
        settings = Settings.model_validate(
            {"frontier": {"providers": [{"id": "openai", "keys": [ref]}]}}
        )
        with pytest.raises(SecretRefError) as excinfo:
            resolve_settings_secrets(settings)
        message = str(excinfo.value)
        assert ref in message
        assert "frontier.providers[0].keys[0]" in message

    def test_plain_settings_resolve_to_noop(self, settings):
        assert resolve_settings_secrets(settings) == []


class TestRedaction:
    def test_redact_secrets_scrubs_registered_values(self, tmp_path):
        env = tmp_path / "daari.env"
        env.write_text("K=super-sensitive\n", encoding="utf-8")
        settings = Settings.model_validate(
            {"enterprise": {"shared_cache_token": f"secret://env-file/{env}#K"}}
        )
        resolve_settings_secrets(settings)
        assert "super-sensitive" not in redact_secrets("token is super-sensitive here")
        assert "[redacted]" in redact_secrets("token is super-sensitive here")

    def test_log_gateway_event_redacts_resolved_secrets(self, tmp_path, monkeypatch):
        from daari.gateway import request_log

        env = tmp_path / "daari.env"
        env.write_text("K=leaky-token-value\n", encoding="utf-8")
        settings = Settings.model_validate(
            {"enterprise": {"shared_cache_token": f"secret://env-file/{env}#K"}}
        )
        resolve_settings_secrets(settings)
        log_path = tmp_path / "gateway.log"
        monkeypatch.setattr(request_log, "LOG_PATH", log_path)
        request_log.log_gateway_event("debug", {"detail": "auth leaky-token-value used"})
        content = log_path.read_text(encoding="utf-8")
        assert "leaky-token-value" not in content
        assert "[redacted]" in content
        assert json.loads(content.splitlines()[0])["event"] == "debug"
