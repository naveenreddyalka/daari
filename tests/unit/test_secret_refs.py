"""secret:// config references (issue #288)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.gateway.request_log import configure_request_log, log_gateway_event
from daari.security.secret_refs import (
    REDACTED,
    SecretRefError,
    clear_resolved_secrets,
    collect_secret_refs,
    is_secret_ref,
    redact_secrets,
    register_resolved_secret,
    resolve_secret_ref,
    resolve_tree,
)
from daari.setup.doctor import run_doctor


@pytest.fixture(autouse=True)
def _clear_secrets():
    clear_resolved_secrets()
    yield
    clear_resolved_secrets()


def test_plain_strings_are_unchanged():
    assert resolve_tree({"api_key": "sk-plain"}) == {"api_key": "sk-plain"}


def test_env_file_scheme(tmp_path: Path):
    env_file = tmp_path / "secrets.env"
    env_file.write_text("OPENAI_API_KEY=sk-from-file\nOTHER=x\n", encoding="utf-8")
    uri = f"secret://env-file/{env_file}#OPENAI_API_KEY"
    assert resolve_secret_ref(uri) == "sk-from-file"


def test_env_file_missing_key(tmp_path: Path):
    env_file = tmp_path / "secrets.env"
    env_file.write_text("A=1\n", encoding="utf-8")
    uri = f"secret://env-file/{env_file}#MISSING"
    with pytest.raises(SecretRefError, match="MISSING"):
        resolve_secret_ref(uri)


def test_env_file_missing_file(tmp_path: Path):
    uri = f"secret://env-file/{tmp_path / 'nope.env'}#KEY"
    with pytest.raises(SecretRefError, match="not found"):
        resolve_secret_ref(uri)


def test_exec_scheme(monkeypatch):
    def fake_run(command, **kwargs):
        assert "printf" in command or "echo" in command
        return type(
            "R",
            (),
            {"returncode": 0, "stdout": "sk-from-exec\n", "stderr": ""},
        )()

    monkeypatch.setattr("daari.security.secret_refs.subprocess.run", fake_run)
    assert resolve_secret_ref("secret://exec/printf sk-from-exec") == "sk-from-exec"


def test_exec_nonzero_is_fatal(monkeypatch):
    monkeypatch.setattr(
        "daari.security.secret_refs.subprocess.run",
        lambda *a, **k: type("R", (), {"returncode": 2, "stdout": "", "stderr": "boom"})(),
    )
    with pytest.raises(SecretRefError, match="exited 2"):
        resolve_secret_ref("secret://exec/false")


def test_keychain_scheme_macos(monkeypatch):
    monkeypatch.setattr("daari.security.secret_refs.platform.system", lambda: "Darwin")
    seen: list[list[str]] = []

    def fake_run(command, **kwargs):
        seen.append(list(command))
        return type("R", (), {"returncode": 0, "stdout": "sk-keychain\n", "stderr": ""})()

    monkeypatch.setattr("daari.security.secret_refs.subprocess.run", fake_run)
    assert resolve_secret_ref("secret://keychain/daari/frontier") == "sk-keychain"
    assert seen[0][:2] == ["security", "find-generic-password"]


def test_keychain_scheme_linux(monkeypatch):
    monkeypatch.setattr("daari.security.secret_refs.platform.system", lambda: "Linux")
    seen: list[list[str]] = []

    def fake_run(command, **kwargs):
        seen.append(list(command))
        return type("R", (), {"returncode": 0, "stdout": "sk-linux\n", "stderr": ""})()

    monkeypatch.setattr("daari.security.secret_refs.subprocess.run", fake_run)
    assert resolve_secret_ref("secret://keychain/daari/frontier") == "sk-linux"
    assert seen[0][0] == "secret-tool"


def test_unknown_scheme_is_fatal():
    with pytest.raises(SecretRefError, match="unknown"):
        resolve_secret_ref("secret://vault/path")


def test_error_message_never_contains_secret_value(monkeypatch):
    monkeypatch.setattr(
        "daari.security.secret_refs.subprocess.run",
        lambda *a, **k: type(
            "R", (), {"returncode": 1, "stdout": "super-secret-value", "stderr": ""}
        )(),
    )
    with pytest.raises(SecretRefError) as exc:
        resolve_secret_ref("secret://exec/echo fail")
    assert "super-secret-value" not in str(exc.value)


def test_settings_load_resolves_refs(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "keys.env"
    env_file.write_text("API_KEY=sk-resolved\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"server:\n  api_key: secret://env-file/{env_file}#API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    # Point load at our file explicitly.
    settings = Settings.load(config_path=config, resolve_secrets=True)
    assert settings.server.api_key == "sk-resolved"


def test_settings_load_can_skip_resolve(tmp_path: Path):
    env_file = tmp_path / "keys.env"
    env_file.write_text("API_KEY=sk-resolved\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    uri = f"secret://env-file/{env_file}#API_KEY"
    config.write_text(f"server:\n  api_key: {uri}\n", encoding="utf-8")
    settings = Settings.load(config_path=config, resolve_secrets=False)
    assert settings.server.api_key == uri


def test_collect_and_doctor_secret_refs(tmp_path: Path):
    from unittest.mock import MagicMock

    import httpx

    env_file = tmp_path / "keys.env"
    env_file.write_text("API_KEY=sk-ok\n", encoding="utf-8")
    uri = f"secret://env-file/{env_file}#API_KEY"
    settings = Settings.model_validate({"server": {"api_key": uri}})
    refs = collect_secret_refs(settings.model_dump())
    assert refs and refs[0][1] == uri
    mock = MagicMock(spec=httpx.Client)
    tags = MagicMock(status_code=200)
    tags.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    mock.get.return_value = tags
    results = run_doctor(settings, httpx_client=mock)
    by_name = {r.name: r for r in results}
    assert by_name["secret_refs"].ok
    assert "1 secret://" in by_name["secret_refs"].detail


def test_doctor_fails_on_bad_ref(tmp_path: Path):
    from unittest.mock import MagicMock

    import httpx

    uri = f"secret://env-file/{tmp_path / 'missing.env'}#API_KEY"
    settings = Settings.model_validate({"server": {"api_key": uri}})
    mock = MagicMock(spec=httpx.Client)
    tags = MagicMock(status_code=200)
    tags.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    mock.get.return_value = tags
    results = run_doctor(settings, httpx_client=mock)
    by_name = {r.name: r for r in results}
    assert not by_name["secret_refs"].ok
    assert "sk-" not in by_name["secret_refs"].detail


def test_redaction_in_log_gateway_event(tmp_path: Path):
    register_resolved_secret("sk-should-not-appear")
    log_path = tmp_path / "events.log"
    configure_request_log(path=log_path, max_bytes=0)
    log_gateway_event("probe", {"token": "sk-should-not-appear", "ok": True})
    text = log_path.read_text(encoding="utf-8")
    assert "sk-should-not-appear" not in text
    assert REDACTED in text
    record = json.loads(text.strip())
    assert record["token"] == REDACTED


def test_redact_secrets_handles_uri():
    assert redact_secrets("secret://exec/op read") == REDACTED
    assert is_secret_ref("secret://env-file/x#Y")
