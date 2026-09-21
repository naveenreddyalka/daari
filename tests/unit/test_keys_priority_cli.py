"""CLI and store surfaces for virtual-key admission priority (#868)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.auth.postgres_virtual_keys import PostgresVirtualKeyStore
from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from tests.unit.test_postgres_virtual_keys import _dsn


def test_cli_create_and_list_priority(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    created = runner.invoke(
        cli_app, ["keys", "create", "ide", "--priority", "high"]
    )
    assert created.exit_code == 0, created.output
    assert "priority: high" in created.output
    listed = runner.invoke(cli_app, ["keys", "list"])
    assert listed.exit_code == 0, listed.output
    header = listed.output.splitlines()[0]
    assert "prio" in header.split() or "priority" in header.lower()
    assert "high" in listed.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    assert store.list()[0].priority == "high"


def test_cli_team_create_priority(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    team = runner.invoke(
        cli_app, ["keys", "team-create", "batch", "--priority", "low"]
    )
    assert team.exit_code == 0, team.output
    assert "priority: low" in team.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    assert store.get_team(name="batch").priority == "low"


def test_cli_help_documents_priority():
    runner = CliRunner()
    create_help = runner.invoke(cli_app, ["keys", "create", "--help"])
    assert create_help.exit_code == 0
    assert "--priority" in create_help.output
    team_help = runner.invoke(cli_app, ["keys", "team-create", "--help"])
    assert team_help.exit_code == 0
    assert "--priority" in team_help.output


def test_cli_md_documents_priority():
    from pathlib import Path

    text = Path("docs/developer/reference/cli.md").read_text(encoding="utf-8")
    assert "--priority" in text
    assert "high" in text and "normal" in text and "low" in text


def test_postgres_memory_round_trip_priority():
    store = PostgresVirtualKeyStore(_dsn())
    team = store.create_team("eng", priority="high")
    assert team.priority == "high"
    assert store.get_team(name="eng").priority == "high"
    created = store.create("bot", priority="low", team="eng")
    assert created.key.priority == "low"
    listed = store.list()
    assert listed[0].priority == "low"
    resolved = store.resolve(created.plaintext)
    assert resolved is not None
    assert resolved.priority == "low"
