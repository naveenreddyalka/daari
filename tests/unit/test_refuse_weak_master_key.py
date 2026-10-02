"""Refuse weak or unset master key at serve startup (#1320)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.config.settings import Settings
from daari.server.master_key_gate import (
    WEAK_MASTER_KEYS,
    master_key_gate_error,
    require_strong_master_key,
)
from daari.setup.doctor import _check_weak_or_unset_master_key, run_doctor


def test_empty_key_refused_by_default():
    settings = Settings.model_validate({"server": {"api_key": ""}})
    err = master_key_gate_error(settings)
    assert err is not None
    assert "unset" in err.lower() or "empty" in err.lower()
    assert "server.api_key" in err


def test_whitespace_key_refused():
    settings = Settings.model_validate({"server": {"api_key": "   "}})
    err = master_key_gate_error(settings)
    assert err is not None


@pytest.mark.parametrize("weak", sorted(WEAK_MASTER_KEYS))
def test_denylist_keys_refused(weak: str):
    settings = Settings.model_validate({"server": {"api_key": weak}})
    err = master_key_gate_error(settings)
    assert err is not None
    assert weak.lower() in err.lower() or "weak" in err.lower()


def test_strong_key_allowed():
    settings = Settings.model_validate(
        {"server": {"api_key": "sk-prod-not-a-demo-key-9f3a"}}
    )
    assert master_key_gate_error(settings) is None


def test_escape_hatch_restores_empty_and_weak():
    settings = Settings.model_validate(
        {
            "server": {
                "api_key": "sk-1234",
                "dangerously_permit_weak_or_unset_api_key": True,
            }
        }
    )
    assert master_key_gate_error(settings) is None
    empty = Settings.model_validate(
        {
            "server": {
                "api_key": "",
                "dangerously_permit_weak_or_unset_api_key": True,
            }
        }
    )
    assert master_key_gate_error(empty) is None


def test_require_strong_raises_system_exit():
    settings = Settings.model_validate({"server": {"api_key": "changeme"}})
    with pytest.raises(SystemExit) as excinfo:
        require_strong_master_key(settings)
    assert excinfo.value.code == 1


def test_serve_exits_nonzero_on_weak_key(monkeypatch):
    def fake_load(*, strict: bool = False):
        return Settings.model_validate(
            {"server": {"host": "127.0.0.1", "port": 11435, "api_key": "sk-1234"}}
        )

    monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
    monkeypatch.setattr("daari.cli.app.create_app", lambda settings: object())
    monkeypatch.setattr(
        "daari.cli.app.uvicorn.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not bind")),
    )
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 1
    assert "sk-1234" in result.output.lower() or "weak" in result.output.lower()
    assert "uvicorn" not in result.output.lower() or "serving" not in result.output.lower() or result.exit_code == 1


def test_serve_escape_hatch_allows_unset(monkeypatch):
    captured: dict = {}

    def fake_load(*, strict: bool = False):
        return Settings.model_validate(
            {
                "server": {
                    "host": "127.0.0.1",
                    "port": 11435,
                    "api_key": "",
                    "dangerously_permit_weak_or_unset_api_key": True,
                }
            }
        )

    monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
    monkeypatch.setattr("daari.cli.app.create_app", lambda settings: object())
    monkeypatch.setattr(
        "daari.cli.app.uvicorn.run",
        lambda _app, **kwargs: captured.update(kwargs),
    )
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 0, result.output
    assert captured.get("host") == "127.0.0.1"


def test_doctor_warns_when_escape_hatch_on(settings):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.server.api_key = ""
    row = _check_weak_or_unset_master_key(settings)
    assert row is not None
    assert row.optional is True
    assert row.ok is False or "dangerously" in row.detail.lower() or "escape" in row.detail.lower() or "permit" in row.detail.lower()


def test_doctor_warns_when_unset_but_virtual_keys_or_local_as_imply_auth(settings):
    settings.server.api_key = ""
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.integrations.mcp_oauth.local_as = True
    row = _check_weak_or_unset_master_key(settings)
    assert row is not None
    detail = row.detail.lower()
    assert "unset" in detail or "empty" in detail or "local_as" in detail or "auth" in detail


def test_doctor_quiet_when_strong_key(settings):
    settings.server.api_key = "sk-prod-strong-enough-key"
    settings.server.dangerously_permit_weak_or_unset_api_key = False
    row = _check_weak_or_unset_master_key(settings)
    assert row is None or row.ok is True
    rows = run_doctor(settings, httpx_client=None)
    weak_rows = [r for r in rows if r.name == "master_key_strength"]
    assert not weak_rows or all(r.ok for r in weak_rows)


def test_docs_mention_escape_hatch():
    auth = Path("docs/developer/guides/configuration/auth-and-keys.md").read_text()
    assert "dangerously_permit_weak_or_unset_api_key" in auth
    config = Path("docs/developer/reference/config.md").read_text()
    assert "dangerously_permit_weak_or_unset_api_key" in config
