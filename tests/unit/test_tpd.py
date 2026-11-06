"""Tokens-per-day (TPD) quota for keys, teams, and end-users (#2056)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_tpd

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


def test_virtual_key_persists_tpd_and_user_tpd(tmp_path: Path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("agent", client_id="key-a", tpd=500, user_tpd=100)
    assert created.key.tpd == 500
    assert created.key.user_tpd == 100
    resolved = store.resolve(created.plaintext)
    assert resolved is not None
    assert resolved.tpd == 500
    assert resolved.user_tpd == 100
    listed = store.list()
    assert listed[0].tpd == 500
    assert listed[0].user_tpd == 100
    payload = store.to_dict(listed[0])
    assert payload["tpd"] == 500
    assert payload["user_tpd"] == 100
    assert store.update_tpd(created.key.key_id, 50)
    assert store.update_user_tpd(created.key.key_id, 10)
    again = store.resolve(created.plaintext)
    assert again is not None
    assert again.tpd == 50
    assert again.user_tpd == 10


def test_team_persists_tpd(tmp_path: Path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng", tpd=900)
    assert team.tpd == 900
    loaded = store.get_team(team.team_id)
    assert loaded is not None
    assert loaded.tpd == 900
    updated = store.update_team(team.team_id, tpd=40)
    assert updated is not None
    assert updated.tpd == 40


def test_old_virtual_key_db_migrates_tpd_columns(tmp_path: Path):
    """Pre-#2056 stores lack tpd/user_tpd; ALTER adds them with default 0."""
    path = tmp_path / "vk.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE virtual_keys (
            key_hash TEXT PRIMARY KEY,
            key_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            prefix TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            expires_at TEXT,
            daily_budget_usd REAL NOT NULL DEFAULT 0,
            monthly_budget_usd REAL NOT NULL DEFAULT 0,
            rpm INTEGER NOT NULL DEFAULT 0,
            tpm INTEGER NOT NULL DEFAULT 0,
            rpd INTEGER NOT NULL DEFAULT 0,
            tier_cap TEXT,
            client_id TEXT,
            team_id TEXT,
            budget_windows_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            user_daily_usd_cap REAL NOT NULL DEFAULT 0,
            user_rpd INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE teams (
            team_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            budget_windows_json TEXT NOT NULL DEFAULT '[]',
            rpd INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE key_hits (key_id TEXT NOT NULL, ts REAL NOT NULL);
        """
    )
    conn.execute(
        "INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at,"
        " daily_budget_usd, monthly_budget_usd, rpm, tpm)"
        " VALUES ('h', 'kid', 'n', 'dk_x', '2026-01-01T00:00:00+00:00', 0, 0, 0, 0)"
    )
    conn.commit()
    conn.close()

    store = VirtualKeyStore(path)
    keys = store.list()
    assert len(keys) == 1
    assert keys[0].tpd == 0
    assert keys[0].user_tpd == 0


def test_tpd_limiter_denies_after_token_budget(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    first = limiter.check(key_id="k1", model="m", tokens=40, tpd=50)
    second = limiter.check(key_id="k1", model="m", tokens=20, tpd=50)
    assert first.allowed
    assert not second.allowed
    assert second.scope == "tpd"
    assert second.bucket == "key"
    assert second.headers().get("X-RateLimit-Limit") == "50"


def test_tpd_independent_of_rpd(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    # Exhaust RPD without touching TPD.
    for _ in range(2):
        assert limiter.check(key_id="k", model="m", tokens=1, rpd=2, tpd=1000).allowed
    denied_rpd = limiter.check(key_id="k", model="m", tokens=1, rpd=2, tpd=1000)
    assert not denied_rpd.allowed
    assert denied_rpd.scope == "rpd"
    # Fresh key: exhaust TPD while RPD stays open (20+20=40 under 50; +20 denies).
    for _ in range(2):
        assert limiter.check(key_id="k2", model="m", tokens=20, rpd=100, tpd=50).allowed
    denied_tpd = limiter.check(key_id="k2", model="m", tokens=20, rpd=100, tpd=50)
    assert not denied_tpd.allowed
    assert denied_tpd.scope == "tpd"


def test_user_tpd_isolates_end_users(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    a1 = limiter.check(
        key_id="shared", model="m", tokens=40, user_id="alice", user_tpd=50
    )
    b1 = limiter.check(
        key_id="shared", model="m", tokens=40, user_id="bob", user_tpd=50
    )
    a2 = limiter.check(
        key_id="shared", model="m", tokens=20, user_id="alice", user_tpd=50
    )
    assert a1.allowed and b1.allowed
    assert not a2.allowed
    assert a2.scope == "tpd"
    assert a2.bucket == "user"
    anon = limiter.check(
        key_id="shared", model="m", tokens=20, user_id=None, user_tpd=50
    )
    assert anon.allowed


def test_tpd_zero_is_unlimited(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    for _ in range(5):
        decision = limiter.check(key_id="open", model="m", tokens=100, tpd=0)
        assert decision.allowed


def test_team_tpd_aggregate(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    a = limiter.check(
        key_id="a", model="m", tokens=30, team_id="t1", team_tpd=50
    )
    b = limiter.check(
        key_id="b", model="m", tokens=30, team_id="t1", team_tpd=50
    )
    assert a.allowed
    assert not b.allowed
    assert b.scope == "tpd"
    assert b.bucket == "team"


def test_zero_token_request_does_not_debit_tpd(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    for _ in range(5):
        decision = limiter.check(key_id="k", model="m", tokens=0, tpd=10)
        assert decision.allowed
    gauges = limiter.key_rate_gauges(
        [type("K", (), {"key_id": "k", "name": "k", "tpd": 10, "rpd": 0})()]
    )
    tpd_row = next(row for row in gauges if row["kind"] == "tpd")
    assert tpd_row["remaining"] == 10


def test_key_and_team_tpd_gauges(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    limiter.check(key_id="kid", model="m", tokens=3, tpd=10, team_id="t1", team_tpd=20)
    key_rows = limiter.key_rate_gauges(
        [type("K", (), {"key_id": "kid", "name": "alice", "tpd": 10, "rpd": 0})()]
    )
    assert {"key": "alice", "kind": "tpd", "limit": 10, "remaining": 7} in key_rows
    team_rows = limiter.team_rate_gauges(
        [type("T", (), {"team_id": "t1", "name": "eng", "rpm": 0, "tpm": 0, "rpd": 0, "tpd": 20})()]
    )
    assert {"team": "eng", "kind": "tpd", "limit": 20, "remaining": 17} in team_rows


def test_doctor_surfaces_tpd_without_token_debit_path(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("capped", tpd=1000)
    store.create("open", tpd=0)
    result = _check_tpd(settings)
    assert result.optional is True
    assert "capped" in result.detail
    assert "tpd" in result.detail.lower() or "token" in result.detail.lower()


@pytest.mark.asyncio
async def test_gateway_tpd_429(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    # "hi" → estimate_request_tokens = max(1, 2//4) = 1; cap at 1 token/day.
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("capped", tpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        denied = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
    assert ok.status_code == 200
    assert denied.status_code == 429
    err = denied.json()["error"]
    assert "tpd" in err["message"]
    assert denied.headers.get("x-ratelimit-limit") == "1"


@pytest.mark.asyncio
async def test_gateway_user_tpd_isolates_users(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("shared", user_tpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alice_ok = await client.post(
            "/v1/chat/completions",
            json={**CHAT, "user": "alice"},
            headers=headers,
        )
        alice_denied = await client.post(
            "/v1/chat/completions",
            json={**CHAT, "user": "alice"},
            headers=headers,
        )
        bob_ok = await client.post(
            "/v1/chat/completions",
            json={**CHAT, "user": "bob"},
            headers=headers,
        )
    assert alice_ok.status_code == 200
    assert alice_denied.status_code == 429
    assert "tpd" in alice_denied.json()["error"]["message"]
    assert bob_ok.status_code == 200


def test_auth_and_keys_docs_mention_tpd() -> None:
    root = Path(__file__).resolve().parents[2]
    auth = (root / "docs/developer/guides/configuration/auth-and-keys.md").read_text(
        encoding="utf-8"
    )
    metrics = (root / "docs/developer/guides/observability/metrics-prometheus.md").read_text(
        encoding="utf-8"
    )
    compare = (root / "docs/developer/resources/compare-litellm.md").read_text(encoding="utf-8")
    assert "--tpd" in auth or "tpd" in auth
    assert "user_tpd" in auth or "--user-tpd" in auth
    assert 'kind="tpd"' in metrics or "tpd" in metrics
    assert "tpd" in compare.lower() or "tokens-per-day" in compare.lower()


@pytest.mark.asyncio
async def test_gateway_tpd_429_bumps_rate_limit_tpd_reject(settings, tmp_path, monkeypatch):
    """Hard TPD 429 increments scope-qualified reject kind (#2096)."""
    _freeze(monkeypatch, {"now": FROZEN})
    settings.observability.prometheus = True
    settings.frontier.soft_budget_ratio = 0.0
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("capped", tpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (
            await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        ).status_code == 200
        denied = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        assert denied.status_code == 429
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_rejects_total{kind="rate_limit_tpd"} 1' in metrics.text
    assert 'daari_rejects_total{kind="rate_limit"}' not in metrics.text
    assert 'daari_rejects_total{kind="concurrency"}' not in metrics.text


@pytest.mark.asyncio
async def test_gateway_rpd_429_bumps_rate_limit_rpd_reject(settings, tmp_path, monkeypatch):
    """Hard RPD 429 increments scope-qualified reject kind (#2096)."""
    _freeze(monkeypatch, {"now": FROZEN})
    settings.observability.prometheus = True
    settings.frontier.soft_budget_ratio = 0.0
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("capped", rpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (
            await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        ).status_code == 200
        denied = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        assert denied.status_code == 429
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_rejects_total{kind="rate_limit_rpd"} 1' in metrics.text
    assert 'daari_rejects_total{kind="rate_limit"}' not in metrics.text


@pytest.mark.asyncio
async def test_gateway_tpd_soft_bumps_rate_limit_tpd_warning(settings, tmp_path, monkeypatch):
    """TPD soft-band increments scope-qualified soft_warning kind (#2096)."""
    from daari.auth.rate_limit import RATELIMIT_WARNING_HEADER

    _freeze(monkeypatch, {"now": FROZEN})
    settings.observability.prometheus = True
    settings.frontier.soft_budget_ratio = 0.8
    # estimate_request_tokens("hi") = 1; soft at 80% of 2 → after 2nd allowed request.
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("soft", tpd=2)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        second = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.headers.get(RATELIMIT_WARNING_HEADER) == "soft"
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_soft_warnings_total{kind="rate_limit_tpd"} 1' in metrics.text
    assert 'daari_soft_warnings_total{kind="rate_limit"}' not in metrics.text
