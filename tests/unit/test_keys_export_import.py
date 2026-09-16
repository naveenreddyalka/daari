"""Keys/teams export/import for backup and DR (issue #548)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.auth.virtual_keys import KEYS_EXPORT_SCHEMA, VirtualKeyStore
from daari.cli.app import app as cli_app

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def test_export_contains_hashes_not_plaintext(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("alice", rpm=10, tpm=1000, team="eng")
    doc = store.export_document()
    assert doc["schema"] == KEYS_EXPORT_SCHEMA
    blob = json.dumps(doc)
    assert created.plaintext not in blob
    assert "key_hash" in doc["keys"][0]
    assert doc["keys"][0]["key_hash"] == VirtualKeyStore._hash(created.plaintext)
    assert doc["teams"][0]["name"] == "eng"
    assert doc["keys"][0]["rpm"] == 10
    assert doc["keys"][0]["tpm"] == 1000


def test_round_trip_preserves_rotated_grace_and_budgets(tmp_path):
    src = VirtualKeyStore(tmp_path / "src.sqlite3")
    created = src.create(
        "alice",
        daily_budget_usd=5.0,
        rpm=10,
        tpm=1000,
        tier_cap="L3",
        team="eng",
        metadata={"mcp": {"deny": ["secret_*"]}},
        region_pin="eu",
    )
    team = src.get_team(name="eng")
    assert team is not None
    src.update_team(team.team_id, rpm=40, tpm=8000, region_pin="eu")
    rotated = src.rotate(created.key.key_id, grace="24h", now=NOW)
    doc = src.export_document()

    dst = VirtualKeyStore(tmp_path / "dst.sqlite3")
    summary = dst.import_document(doc)
    assert summary["keys"]["created"] == 1
    assert summary["teams"]["created"] == 1

    old = dst.resolve(created.plaintext, now=NOW)
    new = dst.resolve(rotated.plaintext, now=NOW)
    assert old is not None and new is not None
    assert old.key_id == new.key_id == created.key.key_id
    assert old.status(now=NOW) == "active"
    assert new.status(now=NOW) == "active"
    assert new.daily_budget_usd == 5.0
    assert new.rpm == 10
    assert new.tpm == 1000
    assert new.tier_cap == "L3"
    assert new.team_name == "eng"
    assert new.metadata["mcp"] == {"deny": ["secret_*"]}
    assert new.region_pin == "eu"
    team = dst.get_team(name="eng")
    assert team is not None
    assert team.rpm == 40
    assert team.tpm == 8000
    assert team.region_pin == "eu"


def test_import_idempotent_second_pass_is_noop(tmp_path):
    src = VirtualKeyStore(tmp_path / "src.sqlite3")
    src.create("alice", rpm=5, team="eng")
    doc = src.export_document()
    dst = VirtualKeyStore(tmp_path / "dst.sqlite3")
    first = dst.import_document(doc)
    assert first["keys"]["created"] == 1
    assert first["teams"]["created"] == 1
    second = dst.import_document(doc)
    assert second["keys"] == {"created": 0, "updated": 0, "skipped": 1}
    assert second["teams"] == {"created": 0, "updated": 0, "skipped": 1}


def test_import_refuses_unknown_schema(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    with pytest.raises(ValueError, match="schema"):
        store.import_document({"schema": 99, "teams": [], "keys": []})


def test_dry_run_does_not_write(tmp_path):
    src = VirtualKeyStore(tmp_path / "src.sqlite3")
    src.create("alice", team="eng")
    doc = src.export_document()
    dst = VirtualKeyStore(tmp_path / "dst.sqlite3")
    summary = dst.import_document(doc, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["keys"]["created"] == 1
    assert dst.list() == []
    assert dst.get_team(name="eng") is None


def test_cli_export_import_round_trip(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    src_path = tmp_path / "src.sqlite3"
    dst_path = tmp_path / "dst.sqlite3"
    settings = Settings()
    settings.server.virtual_keys.path = str(src_path)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    store = VirtualKeyStore(src_path)
    created = store.create("alice", rpm=7, team="ops")
    rotated = store.rotate(created.key.key_id, grace="24h", now=NOW)

    out = tmp_path / "backup.json"
    runner = CliRunner()
    exported = runner.invoke(cli_app, ["keys", "export", "--json", "--out", str(out)])
    assert exported.exit_code == 0, exported.output
    payload = json.loads(out.read_text())
    assert created.plaintext not in out.read_text()
    assert payload["schema"] == KEYS_EXPORT_SCHEMA

    settings.server.virtual_keys.path = str(dst_path)
    dry = runner.invoke(cli_app, ["keys", "import", str(out), "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "create" in dry.output.lower() or "created" in dry.output.lower()
    assert VirtualKeyStore(dst_path).list() == []

    imported = runner.invoke(cli_app, ["keys", "import", str(out)])
    assert imported.exit_code == 0, imported.output
    dst = VirtualKeyStore(dst_path)
    assert dst.resolve(created.plaintext, now=NOW) is not None
    assert dst.resolve(rotated.plaintext, now=NOW) is not None

    bad = runner.invoke(
        cli_app,
        ["keys", "import", str(tmp_path / "nope.json")],
    )
    # missing file
    assert bad.exit_code != 0


def test_cli_import_unknown_schema(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": 99, "teams": [], "keys": []}))
    result = CliRunner().invoke(cli_app, ["keys", "import", str(bad)])
    assert result.exit_code != 0
    assert "schema" in result.output.lower()


def test_postgres_memory_round_trip():
    from daari.auth.postgres_virtual_keys import PostgresVirtualKeyStore

    src = PostgresVirtualKeyStore("memory:export-src")
    created = src.create("bot", rpm=3, team="eng")
    rotated = src.rotate(created.key.key_id, grace="1h", now=NOW)
    doc = src.export_document()
    dst = PostgresVirtualKeyStore("memory:export-dst")
    dst.import_document(doc)
    assert dst.resolve(created.plaintext, now=NOW) is not None
    assert dst.resolve(rotated.plaintext, now=NOW) is not None
