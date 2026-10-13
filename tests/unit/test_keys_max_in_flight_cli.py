"""CLI surfaces for per-key/team max_in_flight concurrency caps (#1612)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app


def test_cli_create_and_list_max_in_flight(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    created = runner.invoke(cli_app, ["keys", "create", "agent", "--max-in-flight", "3"])
    assert created.exit_code == 0, created.output
    assert "max_in_flight: 3" in created.output
    listed = runner.invoke(cli_app, ["keys", "list"])
    assert listed.exit_code == 0, listed.output
    header = listed.output.splitlines()[0].lower()
    assert "mif" in header or "max_in_flight" in header or "inflight" in header
    assert "3" in listed.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    assert store.list()[0].max_in_flight == 3


def test_cli_team_create_max_in_flight(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    team = runner.invoke(cli_app, ["keys", "team-create", "fleet", "--max-in-flight", "2"])
    assert team.exit_code == 0, team.output
    assert "max_in_flight: 2" in team.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    assert store.get_team(name="fleet").max_in_flight == 2


def test_cli_help_documents_max_in_flight():
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"})
    create_help = runner.invoke(cli_app, ["keys", "create", "--help"])
    assert create_help.exit_code == 0
    assert "--max-in-flight" in create_help.output
    team_help = runner.invoke(cli_app, ["keys", "team-create", "--help"])
    assert team_help.exit_code == 0
    assert "--max-in-flight" in team_help.output


def test_keys_export_json_includes_max_in_flight(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("fleet", max_in_flight=4)
    store.create("bot", max_in_flight=2, team="fleet")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["keys", "export", "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert doc["keys"][0]["metadata"].get("max_in_flight") == 2
    assert doc["teams"][0]["metadata"].get("max_in_flight") == 4
