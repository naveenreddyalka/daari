"""Team-level aggregate RPM/TPM rate limits (issue #546)."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import (
    MemoryCounterBackend,
    RATELIMIT_WARNING_HEADER,
    RateLimiter,
)
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _app_with_keys(settings, tmp_path, *, limiter: RateLimiter | None = None):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    if limiter is not None:
        app.state.rate_limiter = limiter

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    return app, store


class TestTeamRateLimiterUnit:
    def test_two_keys_jointly_exhaust_team_rpm(self):
        limiter = RateLimiter(MemoryCounterBackend())
        team_id = "team-eng"
        a1 = limiter.check(
            key_id="alice", model="daari", tokens=1, team_id=team_id, team_rpm=2
        )
        b1 = limiter.check(
            key_id="bob", model="daari", tokens=1, team_id=team_id, team_rpm=2
        )
        a2 = limiter.check(
            key_id="alice", model="daari", tokens=1, team_id=team_id, team_rpm=2
        )
        assert a1.allowed and b1.allowed
        assert not a2.allowed
        assert a2.scope == "rpm"
        assert a2.bucket == "team"
        assert a2.headers()["X-RateLimit-Scope"] == "team"
        assert a2.retry_after is not None
        assert "Retry-After" in a2.headers()

    def test_team_rpm_soft_band_before_hard_deny(self):
        limiter = RateLimiter(MemoryCounterBackend())
        soft_ratio = 0.8
        decisions = [
            limiter.check(
                key_id=f"k{i}", model="daari", tokens=1, team_id="t1", team_rpm=5
            )
            for i in range(5)
        ]
        assert all(d.allowed for d in decisions)
        assert [d.in_soft_band(soft_ratio) for d in decisions] == [
            False,
            False,
            False,
            True,
            True,
        ]
        hard = limiter.check(
            key_id="k5", model="daari", tokens=1, team_id="t1", team_rpm=5
        )
        assert not hard.allowed
        assert hard.scope == "rpm"
        assert RATELIMIT_WARNING_HEADER not in hard.headers()
        assert decisions[3].headers(soft=True)[RATELIMIT_WARNING_HEADER] == "soft"

    def test_team_unlimited_default_keeps_existing_behavior(self):
        limiter = RateLimiter(MemoryCounterBackend(), default_rpm=2)
        # team_rpm=0 / omitted must not invent a team ceiling.
        for _ in range(2):
            assert limiter.check(
                key_id="alice", model="daari", tokens=1, team_id="t", team_rpm=0
            ).allowed
        deny = limiter.check(
            key_id="alice", model="daari", tokens=1, team_id="t", team_rpm=0
        )
        assert not deny.allowed  # per-key default_rpm still applies
        # Other key in same team still free under team unlimited.
        assert limiter.check(
            key_id="bob", model="daari", tokens=1, team_id="t", team_rpm=0
        ).allowed


class TestTeamStoreAndReport:
    def test_create_team_persists_rpm_tpm(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        team = store.create_team("eng", rpm=30, tpm=10_000)
        assert team.rpm == 30
        assert team.tpm == 10_000
        loaded = store.get_team(team.team_id)
        assert loaded is not None
        assert loaded.rpm == 30
        assert loaded.tpm == 10_000

    def test_update_team_rpm_tpm(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        team = store.create_team("eng", rpm=10, tpm=100)
        updated = store.update_team(team.team_id, rpm=20, tpm=200)
        assert updated.rpm == 20
        assert updated.tpm == 200

    def test_team_rpm_tpm_default_unlimited(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        team = store.create_team("eng")
        assert team.rpm == 0
        assert team.tpm == 0

    def test_migrate_adds_team_rpm_tpm_columns(self, tmp_path):
        import sqlite3

        path = tmp_path / "legacy.sqlite3"
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE teams ("
            " team_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,"
            " budget_windows_json TEXT NOT NULL DEFAULT '[]',"
            " created_at TEXT NOT NULL, region_pin TEXT)"
        )
        conn.execute(
            "INSERT INTO teams VALUES (?,?,?,?,?)",
            ("t1", "eng", "[]", "2026-01-01", None),
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
        assert team is not None
        assert team.rpm == 0
        assert team.tpm == 0

    def test_report_by_team_includes_configured_limits(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        store.create_team("eng", rpm=40, tpm=8000)
        store.create("a", client_id="key-a", team="eng")
        rows = store.report_by_team(
            [
                {
                    "client_id": "key-a",
                    "requests": 3,
                    "cache_hits": 1,
                    "local_requests": 2,
                    "frontier_requests": 1,
                    "estimated_saved_usd": 0.1,
                }
            ]
        )
        assert rows[0]["team"] == "eng"
        assert rows[0]["rpm"] == 40
        assert rows[0]["tpm"] == 8000


def test_cli_team_create_update_rpm_tpm(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    created = runner.invoke(
        cli_app, ["keys", "team-create", "eng", "--rpm", "15", "--tpm", "5000"]
    )
    assert created.exit_code == 0, created.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.get_team(name="eng")
    assert team is not None
    assert team.rpm == 15
    assert team.tpm == 5000

    updated = runner.invoke(
        cli_app,
        ["keys", "team-update", team.team_id, "--rpm", "25", "--tpm", "9000"],
    )
    assert updated.exit_code == 0, updated.output
    team = store.get_team(team.team_id)
    assert team is not None
    assert team.rpm == 25
    assert team.tpm == 9000


@pytest.mark.asyncio
async def test_two_keys_jointly_exhaust_team_rpm_via_gateway(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    limiter = RateLimiter(MemoryCounterBackend())
    app, store = _app_with_keys(settings, tmp_path, limiter=limiter)
    store.create_team("eng", rpm=2)
    key_a = store.create("a", client_id="key-a", team="eng")
    key_b = store.create("b", client_id="key-b", team="eng")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_a.plaintext}", "X-Daari-No-Cache": "true"},
        )
        r2 = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_b.plaintext}", "X-Daari-No-Cache": "true"},
        )
        r3 = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_a.plaintext}", "X-Daari-No-Cache": "true"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    assert r3.headers.get("X-RateLimit-Scope") == "team"
    assert r3.json()["error"]["type"] == "rate_limit_error"


@pytest.mark.asyncio
async def test_team_rpm_soft_warn_then_hard_429(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    settings.frontier.soft_budget_ratio = 0.8
    limiter = RateLimiter(MemoryCounterBackend())
    app, store = _app_with_keys(settings, tmp_path, limiter=limiter)
    store.create_team("eng", rpm=5)
    key = store.create("a", client_id="key-a", team="eng")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(5):
            response = await client.post(
                "/v1/chat/completions",
                json=CHAT,
                headers={
                    "Authorization": f"Bearer {key.plaintext}",
                    "X-Daari-Meta": "true",
                    "X-Daari-No-Cache": "true",
                },
            )
            assert response.status_code == 200, response.text
            if i < 3:
                assert RATELIMIT_WARNING_HEADER not in response.headers
            else:
                assert response.headers[RATELIMIT_WARNING_HEADER] == "soft"
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert hard.status_code == 429
    assert "Retry-After" in hard.headers
    assert hard.headers.get("X-RateLimit-Scope") == "team"
    assert RATELIMIT_WARNING_HEADER not in hard.headers


@pytest.mark.asyncio
async def test_team_unlimited_default_via_gateway(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    # No default rpm on limiter; team rpm=0 must not 429.
    limiter = RateLimiter(MemoryCounterBackend())
    app, store = _app_with_keys(settings, tmp_path, limiter=limiter)
    store.create_team("eng")  # rpm/tpm default 0
    key = store.create("a", client_id="key-a", team="eng", rpm=0, tpm=0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            response = await client.post(
                "/v1/chat/completions",
                json=CHAT,
                headers={
                    "Authorization": f"Bearer {key.plaintext}",
                    "X-Daari-No-Cache": "true",
                },
            )
            assert response.status_code == 200, response.text
