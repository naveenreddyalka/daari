"""rate_limited_by / X-Daari-Rate-Limited-By on gateway 429s (#2361)."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import (
    RATE_LIMITED_BY_HEADER,
    RATE_LIMITED_BY_HEADER_ALIAS,
    MemoryCounterBackend,
    RateLimitDecision,
    RateLimiter,
    rate_limited_by_label,
)
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


CHAT = {
    "model": "daari",
    "messages": [{"role": "user", "content": "hi"}],
}


def _mock_execute(app) -> None:
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=f"ok:{request.meta.client_id}:{request.meta.tier_cap}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier=request.meta.tier_cap or "L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    app.state.ctx.router.ollama.execute = fake


@pytest.mark.parametrize(
    ("bucket", "scope", "kind", "expected"),
    [
        ("key", "rpm", None, "key_rpm"),
        ("team", "tpm", None, "team_tpm"),
        ("model", "rpd", None, "model_rpd"),
        ("user", "rpd", None, "user_rpd"),
        ("mcp_server:alpha", "rpm", None, "mcp_server_rpm"),
        ("family:chat", "tpm", None, "family_tpm"),
        ("concurrency", "concurrency", None, "concurrency"),
        ("key_concurrency", "", None, "key_concurrency"),
        ("", "", "key_lockout", "key_lockout"),
        ("", "", "auth_throttled", "auth_throttled"),
        ("", "", "budget_usd", "budget_usd"),
    ],
)
def test_rate_limited_by_label(bucket, scope, kind, expected):
    assert rate_limited_by_label(bucket=bucket, scope=scope, kind=kind) == expected


def test_decision_headers_include_rate_limited_by_on_deny():
    denied = RateLimitDecision(
        allowed=False,
        limit=10,
        remaining=0,
        reset_epoch=1_700_000_060,
        retry_after=1,
        scope="rpm",
        bucket="key",
        backend="memory",
    )
    headers = denied.headers()
    assert headers[RATE_LIMITED_BY_HEADER] == "key_rpm"
    assert headers[RATE_LIMITED_BY_HEADER_ALIAS] == "key_rpm"
    assert headers["Retry-After"] == "1"
    assert headers["X-RateLimit-Scope"] == "key"

    allowed = RateLimitDecision(
        allowed=True,
        limit=10,
        remaining=9,
        reset_epoch=1_700_000_060,
        scope="rpm",
        bucket="key",
        backend="memory",
    )
    ok = allowed.headers()
    assert RATE_LIMITED_BY_HEADER not in ok
    assert RATE_LIMITED_BY_HEADER_ALIAS not in ok


@pytest.mark.asyncio
async def test_key_rpm_429_sets_rate_limited_by(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_030.0)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("burst", rpm=1)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = RateLimiter(MemoryCounterBackend())
    _mock_execute(app)
    headers = {"Authorization": f"Bearer {created.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        second = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers.get(RATE_LIMITED_BY_HEADER) == "key_rpm"
    assert second.headers.get(RATE_LIMITED_BY_HEADER_ALIAS) == "key_rpm"
    assert "Retry-After" in second.headers
    assert second.headers.get("X-RateLimit-Scope") == "key"


@pytest.mark.asyncio
async def test_team_rpm_429_sets_rate_limited_by(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    limiter = RateLimiter(MemoryCounterBackend())
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", rpm=2)
    key_a = store.create("a", client_id="key-a", team="eng")
    key_b = store.create("b", client_id="key-b", team="eng")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = limiter
    _mock_execute(app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_a.plaintext}", "X-Daari-No-Cache": "true"},
        )
        await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_b.plaintext}", "X-Daari-No-Cache": "true"},
        )
        denied = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_a.plaintext}", "X-Daari-No-Cache": "true"},
        )
    assert denied.status_code == 429
    assert denied.headers.get(RATE_LIMITED_BY_HEADER) == "team_rpm"
    assert denied.headers.get("X-RateLimit-Scope") == "team"


@pytest.mark.asyncio
async def test_key_lockout_429_sets_rate_limited_by(settings, tmp_path):
    settings.server.api_key = "master-secret"
    settings.auth.max_failures = 50
    settings.auth.exempt_loopback = False
    settings.auth.key_lockout.max_failures = 2
    settings.auth.key_lockout.lockout_seconds = 45
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    application.state.auth_throttle.exempt_loopback = False
    application.state.key_lockout.exempt_loopback = False

    transport = ASGITransport(app=application, client=("203.0.113.60", 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            bad = await client.get(
                "/v1/models", headers={"Authorization": "Bearer abcdefghijXXXX"}
            )
            assert bad.status_code == 401
        locked = await client.get(
            "/v1/models", headers={"Authorization": "Bearer abcdefghijYYYY"}
        )
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "auth_key_locked"
    assert locked.headers.get(RATE_LIMITED_BY_HEADER) == "key_lockout"
    assert locked.headers.get(RATE_LIMITED_BY_HEADER_ALIAS) == "key_lockout"
    assert locked.headers.get("Retry-After")
