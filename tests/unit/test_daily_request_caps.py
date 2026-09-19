"""Per-key and per-team calendar-day request caps beside rpm (issue #717)."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter, SqliteCounterBackend
from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}
FROZEN = 1_700_000_030.0


def _freeze(monkeypatch, clock: dict[str, float]) -> None:
    monkeypatch.setattr(time, "time", lambda: clock["now"])
    monkeypatch.setattr("daari.auth.rate_limit.time.time", lambda: clock["now"])


def _app_with_keys(settings, tmp_path, *, limiter: RateLimiter):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = limiter

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    return app, store


class TestRpdLimiter:
    def test_under_cap_allowed_and_cap_plus_one_denied(self, monkeypatch):
        _freeze(monkeypatch, {"now": FROZEN})
        limiter = RateLimiter(MemoryCounterBackend())
        first = limiter.check(key_id="k", model="daari", tokens=1, rpd=2)
        second = limiter.check(key_id="k", model="daari", tokens=1, rpd=2)
        third = limiter.check(key_id="k", model="daari", tokens=1, rpd=2)
        assert first.allowed and second.allowed
        assert not third.allowed
        assert third.scope == "rpd"
        assert third.bucket == "key"
        headers = third.headers()
        assert headers["X-RateLimit-Limit"] == "2"
        assert headers["X-RateLimit-Remaining"] == "0"
        assert int(headers["X-RateLimit-Reset"]) == (int(FROZEN // 86400) + 1) * 86400

    def test_window_rollover_allowed(self, monkeypatch):
        clock = {"now": FROZEN}
        _freeze(monkeypatch, clock)
        limiter = RateLimiter(MemoryCounterBackend())
        assert limiter.check(key_id="k", model="daari", tokens=1, rpd=1).allowed
        denied = limiter.check(key_id="k", model="daari", tokens=1, rpd=1)
        assert not denied.allowed
        clock["now"] = FROZEN + 86400
        assert limiter.check(key_id="k", model="daari", tokens=1, rpd=1).allowed

    def test_rpm_still_independent(self, monkeypatch):
        _freeze(monkeypatch, {"now": FROZEN})
        limiter = RateLimiter(MemoryCounterBackend())
        assert limiter.check(key_id="rpm-key", model="daari", tokens=1, rpm=1, rpd=10).allowed
        rpm_deny = limiter.check(key_id="rpm-key", model="daari", tokens=1, rpm=1, rpd=10)
        assert not rpm_deny.allowed
        assert rpm_deny.scope == "rpm"
        assert limiter.check(key_id="rpd-key", model="daari", tokens=1, rpm=10, rpd=1).allowed
        rpd_deny = limiter.check(key_id="rpd-key", model="daari", tokens=1, rpm=10, rpd=1)
        assert not rpd_deny.allowed
        assert rpd_deny.scope == "rpd"

    def test_unset_rpd_does_not_deny(self, monkeypatch):
        _freeze(monkeypatch, {"now": FROZEN})
        limiter = RateLimiter(MemoryCounterBackend())
        for _ in range(5):
            decision = limiter.check(key_id="open", model="daari", tokens=1, rpd=0)
            assert decision.allowed
            assert decision.scope != "rpd"

    def test_team_rpd_is_sum_and_tighter_wins(self, monkeypatch):
        _freeze(monkeypatch, {"now": FROZEN})
        limiter = RateLimiter(MemoryCounterBackend())
        a = limiter.check(key_id="alice", model="daari", tokens=1, rpd=5, team_id="eng", team_rpd=2)
        b = limiter.check(key_id="bob", model="daari", tokens=1, rpd=5, team_id="eng", team_rpd=2)
        c = limiter.check(key_id="alice", model="daari", tokens=1, rpd=5, team_id="eng", team_rpd=2)
        assert a.allowed and b.allowed
        assert not c.allowed
        assert c.scope == "rpd"
        assert c.bucket == "team"

    def test_sqlite_day_window_not_wiped_by_minute_counter(self, tmp_path, monkeypatch):
        _freeze(monkeypatch, {"now": FROZEN})
        backend = SqliteCounterBackend(tmp_path / "rl.sqlite3")
        assert backend.increment("rpd:k", 1, window_seconds=86400) == 1
        backend.increment("rpm:k", 1, window_seconds=60)
        assert backend.increment("rpd:k", 1, window_seconds=86400) == 2


def test_store_create_update_and_export_round_trip(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng", rpd=40)
    assert team.rpd == 40
    updated = store.update_team(team.team_id, rpd=25)
    assert updated.rpd == 25
    created = store.create("alice", rpm=3, rpd=9, team="eng")
    assert created.key.rpd == 9
    listed = next(item for item in store.list() if item.key_id == created.key.key_id)
    assert listed.rpd == 9
    resolved = store.resolve(created.plaintext)
    assert resolved is not None and resolved.rpd == 9
    assert store.update_rpd(created.key.key_id, 4)
    assert store.resolve(created.plaintext).rpd == 4  # type: ignore[union-attr]

    doc = store.export_document()
    assert doc["keys"][0]["rpd"] == 4
    assert doc["teams"][0]["rpd"] == 25
    dst = VirtualKeyStore(tmp_path / "dst.sqlite3")
    dst.import_document(doc)
    imported = dst.resolve(created.plaintext)
    assert imported is not None and imported.rpd == 4
    imported_team = dst.get_team(name="eng")
    assert imported_team is not None and imported_team.rpd == 25
    again = dst.import_document(doc)
    assert again["keys"]["skipped"] == 1
    assert again["teams"]["skipped"] == 1


def test_migrate_adds_rpd_columns(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE teams ("
        " team_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,"
        " budget_windows_json TEXT NOT NULL DEFAULT '[]',"
        " created_at TEXT NOT NULL, region_pin TEXT, rpm INTEGER, tpm INTEGER)"
    )
    conn.execute(
        "INSERT INTO teams (team_id, name, budget_windows_json, created_at) VALUES (?,?,?,?)",
        ("t1", "eng", "[]", "2026-01-01"),
    )
    conn.execute(
        "CREATE TABLE virtual_keys ("
        " key_hash TEXT PRIMARY KEY, key_id TEXT, name TEXT, prefix TEXT,"
        " created_at TEXT, revoked_at TEXT, daily_budget_usd REAL,"
        " monthly_budget_usd REAL, rpm INTEGER, tpm INTEGER, tier_cap TEXT,"
        " client_id TEXT, team_id TEXT, budget_windows_json TEXT,"
        " metadata_json TEXT)"
    )
    conn.commit()
    conn.close()
    store = VirtualKeyStore(path)
    team = store.get_team("t1")
    assert team is not None and team.rpd == 0


def test_cli_keys_and_teams_accept_rpd(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    created_team = runner.invoke(cli_app, ["keys", "team-create", "eng", "--rpd", "15"])
    assert created_team.exit_code == 0, created_team.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.get_team(name="eng")
    assert team is not None and team.rpd == 15
    updated = runner.invoke(cli_app, ["keys", "team-update", team.team_id, "--rpd", "30"])
    assert updated.exit_code == 0, updated.output
    assert store.get_team(team.team_id).rpd == 30  # type: ignore[union-attr]

    created = runner.invoke(cli_app, ["keys", "create", "demo", "--rpd", "8", "--team", "eng"])
    assert created.exit_code == 0, created.output
    key_id = next(item.key_id for item in store.list() if item.name == "demo")
    assert store.list()[0].rpd == 8 or any(item.rpd == 8 for item in store.list())
    changed = runner.invoke(cli_app, ["keys", "update", key_id, "--rpd", "2"])
    assert changed.exit_code == 0, changed.output
    assert any(item.rpd == 2 for item in store.list())


@pytest.mark.asyncio
async def test_gateway_rpd_429_names_rpd(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("burst", rpd=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {created.plaintext}", "X-Daari-No-Cache": "true"},
        )
        denied = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {created.plaintext}", "X-Daari-No-Cache": "true"},
        )
    assert ok.status_code == 200
    assert denied.status_code == 429
    body = denied.json()["error"]
    assert body["type"] == "rate_limit_error"
    assert "rpd" in body["message"]
    assert denied.headers["x-ratelimit-limit"] == "1"
    assert "x-ratelimit-remaining" in denied.headers
    assert "x-ratelimit-reset" in denied.headers


@pytest.mark.asyncio
async def test_gateway_unset_rpd_does_not_429(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("open", rpm=0, rpd=0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            response = await client.post(
                "/v1/chat/completions",
                json=CHAT,
                headers={
                    "Authorization": f"Bearer {created.plaintext}",
                    "X-Daari-No-Cache": "true",
                },
            )
            assert response.status_code == 200, response.text
