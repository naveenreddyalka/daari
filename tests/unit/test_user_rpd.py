"""Per-end-user requests-per-day (user_rpd) alongside user_daily_usd_cap (#1911)."""

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
from daari.setup.doctor import _check_unbounded_rpd, _check_user_rpd

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


def test_virtual_key_persists_user_rpd(tmp_path: Path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("agent", client_id="key-a", user_rpd=12)
    assert created.key.user_rpd == 12
    resolved = store.resolve(created.plaintext)
    assert resolved is not None
    assert resolved.user_rpd == 12
    listed = store.list()
    assert listed[0].user_rpd == 12
    payload = store.to_dict(listed[0])
    assert payload["user_rpd"] == 12
    assert store.update_user_rpd(created.key.key_id, 3)
    assert store.resolve(created.plaintext).user_rpd == 3  # type: ignore[union-attr]


def test_old_virtual_key_db_migrates_user_rpd_column(tmp_path: Path):
    """Pre-#1911 stores lack user_rpd; ALTER adds it with default 0."""
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
            tier_cap TEXT,
            client_id TEXT,
            team_id TEXT,
            budget_windows_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            user_daily_usd_cap REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE teams (team_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            budget_windows_json TEXT NOT NULL DEFAULT '[]');
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
    assert keys[0].user_rpd == 0


def test_user_rpd_limiter_isolates_end_users(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    a1 = limiter.check(
        key_id="shared", model="m", tokens=1, user_id="alice", user_rpd=1
    )
    b1 = limiter.check(key_id="shared", model="m", tokens=1, user_id="bob", user_rpd=1)
    a2 = limiter.check(
        key_id="shared", model="m", tokens=1, user_id="alice", user_rpd=1
    )
    assert a1.allowed and b1.allowed
    assert not a2.allowed
    assert a2.scope == "rpd"
    assert a2.bucket == "user"
    anon = limiter.check(key_id="shared", model="m", tokens=1, user_id=None, user_rpd=1)
    assert anon.allowed  # no named user → no per-user fence


def test_user_rpd_zero_is_unlimited(monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    limiter = RateLimiter(MemoryCounterBackend())
    for _ in range(5):
        decision = limiter.check(
            key_id="open", model="m", tokens=1, user_id="alice", user_rpd=0
        )
        assert decision.allowed


def test_doctor_surfaces_keys_with_user_rpd(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("shared", user_rpd=50)
    store.create("open", user_rpd=0)
    result = _check_user_rpd(settings)
    assert result.ok is True
    assert result.optional is True
    assert "shared" in result.detail
    assert "user_rpd" in result.detail or "end-user" in result.detail.lower()


def test_unbounded_rpd_ignores_user_rpd_for_key_level(settings, tmp_path):
    """user_rpd does not satisfy key-level rpd; rpm+rpd=0 still warns (#1911)."""
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    VirtualKeyStore(settings.virtual_keys_path).create(
        "burst", rpm=60, rpd=0, user_rpd=100
    )
    result = _check_unbounded_rpd(settings)
    assert result.ok is False
    assert "burst" in result.detail


@pytest.mark.asyncio
async def test_gateway_user_rpd_429_isolates_users(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("shared", user_rpd=1)
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
        no_user = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers=headers,
        )
    assert alice_ok.status_code == 200
    assert alice_denied.status_code == 429
    err = alice_denied.json()["error"]
    assert err["type"] == "rate_limit_error"
    assert "rpd" in err["message"]
    assert alice_denied.headers.get("x-ratelimit-scope") == "user"
    assert bob_ok.status_code == 200
    assert no_user.status_code == 200


@pytest.mark.asyncio
async def test_decisions_user_rpd_429(settings, tmp_path, monkeypatch):
    """Decisions middleware honors user_rpd with the same 429 shape (#1911)."""
    _freeze(monkeypatch, {"now": FROZEN})
    app, store = _app_with_keys(settings, tmp_path, limiter=RateLimiter(MemoryCounterBackend()))
    created = store.create("judge", user_rpd=1)
    body = {
        "model": "nimble",
        "input": "I was charged twice.",
        "user": "alice",
        "questions": [
            {
                "type": "choice",
                "name": "department",
                "instructions": "Which department?",
                "choices": [
                    {"value": "billing", "description": "Payments"},
                    {"value": "other", "description": "Else"},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/decisions", json=body, headers=headers)
        second = await client.post("/v1/decisions", json=body, headers=headers)
    # Middleware increments on every POST; second attributed call must 429.
    assert first.status_code != 429 or first.headers.get("x-ratelimit-scope") == "user"
    assert second.status_code == 429
    assert second.json()["error"]["type"] == "rate_limit_error"
    assert second.headers.get("x-ratelimit-scope") == "user"
