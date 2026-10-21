"""CLI events list and lockout inventory (#1738)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.key_lockout import KeyLockout
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.gateway.postgres_request_log import PostgresRequestLogStore
from daari.router.router import AppContext
from daari.server.app import create_app


def test_events_list_filters_kind_team_and_cursor(monkeypatch):
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    dsn = f"memory:cli-events-{uuid.uuid4().hex}"
    settings = Settings()
    settings.observability.request_log.backend = "postgres"
    settings.observability.postgres_url = dsn
    store = PostgresRequestLogStore(dsn)
    store.append("chat", {"team_id": "eng", "n": 1})
    store.append("chat", {"team_id": "eng", "n": 2})
    store.append("embed", {"team_id": "ops", "n": 3})
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    runner = CliRunner()
    page = runner.invoke(
        cli_app,
        ["events", "list", "--team", "eng", "--kind", "CHAT", "--limit", "1"],
    )
    assert page.exit_code == 0, page.output
    lines = [line for line in page.output.splitlines() if line.strip()]
    assert lines[0].split("\t")[2] == "chat"
    assert "\teng" in lines[0]
    assert lines[-1].startswith("next_cursor: ")
    cursor = lines[-1].split(": ", 1)[1]
    assert cursor != "-"

    older = runner.invoke(
        cli_app,
        ["events", "list", "--team", "eng", "--kind", "chat", "--cursor", cursor],
    )
    assert older.exit_code == 0, older.output
    assert "No events." not in older.output
    assert "next_cursor: -" in older.output
    assert older.output.splitlines()[0].split("\t")[2] == "chat"


def test_events_list_requires_postgres_backend(monkeypatch):
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    result = CliRunner().invoke(cli_app, ["events", "list"])
    assert result.exit_code == 1
    assert "postgres" in result.output


def test_events_list_key_since_until(monkeypatch):
    """CLI --key/--since/--until match the HTTP events filters (#1824)."""
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    dsn = f"memory:cli-events-window-{uuid.uuid4().hex}"
    settings = Settings()
    settings.observability.request_log.backend = "postgres"
    settings.observability.postgres_url = dsn
    store = PostgresRequestLogStore(dsn)
    store.append("chat", {"team_id": "eng", "key_id": "k-a"}, ts="2026-10-20T13:00:00+00:00")
    store.append("chat", {"team_id": "eng", "key_id": "k-b"}, ts="2026-10-20T14:05:00+00:00")
    store.append("embed", {"team_id": "eng", "key_id": "k-b"}, ts="2026-10-20T14:15:00+00:00")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    runner = CliRunner()
    page = runner.invoke(
        cli_app,
        [
            "events",
            "list",
            "--key",
            "k-b",
            "--since",
            "2026-10-20T14:00:00Z",
            "--until",
            "2026-10-20T14:10:00Z",
        ],
    )
    assert page.exit_code == 0, page.output
    lines = [line for line in page.output.splitlines() if line.strip() and not line.startswith("next_cursor")]
    assert len(lines) == 1
    assert lines[0].split("\t")[2] == "chat"

    bad = runner.invoke(cli_app, ["events", "list", "--since", "bogus"])
    assert bad.exit_code == 1
    assert "invalid since" in bad.output


def test_keys_lockouts_prints_expiry(monkeypatch):
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    lock = KeyLockout(max_failures=1, lockout_seconds=30, exempt_loopback=False)
    lock.record_failure("abcdefghijXXXX", client_ip="203.0.113.9", now=1000.0)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: Settings())
    monkeypatch.setattr("daari.auth.key_lockout.build_key_lockout", lambda _settings: lock)
    monkeypatch.setattr(
        lock,
        "locked_inventory",
        lambda **_kwargs: KeyLockout.locked_inventory(lock, now=1010.0),
    )

    result = CliRunner().invoke(cli_app, ["keys", "lockouts"])
    assert result.exit_code == 0, result.output
    assert "abcdefghij\t20" in result.output


@pytest.mark.asyncio
async def test_lockouts_list_audited_and_requires_auth(settings):
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    settings.auth.key_lockout.max_failures = 1
    settings.auth.key_lockout.lockout_seconds = 40
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    lockout = app.state.key_lockout
    lockout.exempt_loopback = False
    lockout.record_failure("abcdefghijXXXX", client_ip="203.0.113.8", now=500.0)
    lockout.max_failures = 0
    lockout.locked_inventory = lambda **_kwargs: lockout.__class__.locked_inventory(
        lockout, now=510.0
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/v1/daari/lockouts")
        assert missing.status_code == 401
        listed = await client.get(
            "/v1/daari/lockouts",
            headers={
                "Authorization": "Bearer master-sekret",
                "X-Daari-Actor": "ops",
            },
        )
    assert listed.status_code == 200
    body = listed.json()
    assert body["lockouts"] == [{"prefix": "abcdefghij", "expires_in_seconds": 30}]
    rows = [
        row
        for row in audit_log_from_settings(settings).list(limit=20)
        if row["action"] == "admin.lockouts.list"
    ]
    assert len(rows) == 1
    assert rows[0]["actor"] == "ops"
    assert rows[0]["detail"]["returned"] == 1
    assert rows[0]["detail"]["prefixes"] == ["abcdefghij"]
