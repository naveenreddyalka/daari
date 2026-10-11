"""Virtual-key last_used_at + status/idle filters (#1545)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.postgres_virtual_keys import PostgresVirtualKeyStore
from daari.auth.virtual_keys import VirtualKeyStore, filter_virtual_keys
from daari.cli.app import app as cli_app
from daari.router.router import AppContext
from daari.server.app import create_app


def test_sqlite_migration_adds_last_used_at(tmp_path):
    db = tmp_path / "vk.sqlite3"
    store = VirtualKeyStore(db)
    created = store.create("alice")
    assert created.key.last_used_at is None
    with store._connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(virtual_keys)").fetchall()}
    assert "last_used_at" in cols


def test_touch_last_used_throttled(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("alice")
    t0 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    assert store.touch_last_used(created.key.key_id, now=t0, min_interval_s=60) is True
    again = store.get_key(created.key.key_id)
    assert again is not None
    assert again.last_used_at == t0.isoformat()
    # Within throttle window — no write.
    t1 = t0 + timedelta(seconds=30)
    assert store.touch_last_used(created.key.key_id, now=t1, min_interval_s=60) is False
    assert store.get_key(created.key.key_id).last_used_at == t0.isoformat()
    # After throttle window — updates.
    t2 = t0 + timedelta(seconds=61)
    assert store.touch_last_used(created.key.key_id, now=t2, min_interval_s=60) is True
    assert store.get_key(created.key.key_id).last_used_at == t2.isoformat()


def test_filter_status_and_idle_days(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    active = store.create("active")
    store.create("expired", expires_at="2020-01-01T00:00:00+00:00")
    revoked = store.create("revoked")
    store.revoke(revoked.key.key_id)
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    store.touch_last_used(active.key.key_id, now=now - timedelta(days=10), min_interval_s=0)
    store.create("never")
    keys = store.list()
    by_status = {k.name: k.status(now) for k in keys}
    assert by_status["active"] == "active"
    assert by_status["expired"] == "expired"
    assert by_status["revoked"] == "revoked"

    only_active = filter_virtual_keys(keys, status="active", now=now)
    assert {k.name for k in only_active} == {"active", "never"}

    idle = filter_virtual_keys(keys, idle_days=7, now=now)
    names = {k.name for k in idle}
    assert "active" in names  # 10 days idle
    assert "never" in names  # never used
    assert "expired" in names  # never used
    fresh = filter_virtual_keys(
        [
            store.get_key(active.key.key_id),
        ],
        idle_days=30,
        now=now,
    )
    assert fresh == []  # only 10 days idle


def test_postgres_memory_backend_filters(tmp_path):
    store = PostgresVirtualKeyStore("memory:last-used-test")
    assert store.enabled
    a = store.create("a")
    store.create("b", expires_at="2020-01-01T00:00:00+00:00")
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    store.touch_last_used(a.key.key_id, now=now - timedelta(days=100), min_interval_s=0)
    keys = store.list()
    expired = filter_virtual_keys(keys, status="expired", now=now)
    assert {k.name for k in expired} == {"b"}
    idle = filter_virtual_keys(keys, idle_days=90, now=now)
    assert {k.name for k in idle} >= {"a", "b"}


@pytest.mark.asyncio
async def test_auth_updates_last_used_and_admin_filters(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("alice", client_id="alice")
    stale = store.create("stale", client_id="stale")
    old = datetime.now(timezone.utc) - timedelta(days=120)
    store.touch_last_used(stale.key.key_id, now=old, min_interval_s=0)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # /health is open; hit a gated path so auth middleware runs.
        models = await client.get(
            "/v1/models", headers={"Authorization": f"Bearer {created.plaintext}"}
        )
        assert models.status_code == 200
        listed = store.get_key(created.key.key_id)
        assert listed is not None
        assert listed.last_used_at is not None

        all_keys = await client.get("/v1/daari/keys", headers={"Authorization": "Bearer master"})
        assert all_keys.status_code == 200
        assert len(all_keys.json()["keys"]) == 2
        assert all("last_used_at" in row for row in all_keys.json()["keys"])

        idle = await client.get(
            "/v1/daari/keys",
            params={"idle_days": 90},
            headers={"Authorization": "Bearer master"},
        )
        assert idle.status_code == 200
        idle_ids = {row["key_id"] for row in idle.json()["keys"]}
        assert stale.key.key_id in idle_ids
        assert created.key.key_id not in idle_ids

        active = await client.get(
            "/v1/daari/keys",
            params={"status": "active"},
            headers={"Authorization": "Bearer master"},
        )
        assert active.status_code == 200
        assert len(active.json()["keys"]) == 2


def test_cli_list_status_and_show_last_used(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("alice")
    store.touch_last_used(
        created.key.key_id,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        min_interval_s=0,
    )
    runner = CliRunner()
    listed = runner.invoke(cli_app, ["keys", "list", "--status", "active"])
    assert listed.exit_code == 0, listed.output
    assert "alice" in listed.output
    assert "last_used" in listed.output.lower() or "2026-01-01" in listed.output
    shown = runner.invoke(cli_app, ["keys", "show", created.key.key_id])
    assert shown.exit_code == 0, shown.output
    assert "last_used" in shown.output
    assert "2026-01-01" in shown.output
